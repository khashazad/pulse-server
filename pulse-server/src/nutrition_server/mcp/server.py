from __future__ import annotations

from datetime import date as DateValue
from datetime import datetime as DateTimeValue
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from nutrition_server.config import get_settings
from nutrition_server.db import get_session, transaction
from nutrition_server.macro_aggregates import sum_food_entry_macros
from nutrition_server.mcp.auth import ApiKeyMiddleware
from nutrition_server.models import FoodEntryResponse, MacroTargets, MacroTotals
from nutrition_server.quantity import parse_quantity, scale_macros
from nutrition_server.repositories.entries import EntriesRepository
from nutrition_server.repositories.targets import TargetsRepository
from nutrition_server.services.log_food_service import log_food_one_shot
from nutrition_server.services.summary_service import build_daily_summary


class ParsedQuantityOut(BaseModel):
    value: float
    unit: str
    grams: float | None
    is_count: bool


class FoodCandidate(BaseModel):
    fdc_id: int
    description: str
    serving_size: float | None
    serving_size_unit: str | None
    per_basis: MacroTotals
    basis_label: str
    scaled_for_quantity: MacroTotals
    scaling_confidence: str
    recommended: bool


class SearchFoodResponse(BaseModel):
    query: str
    parsed_quantity: ParsedQuantityOut
    candidates: list[FoodCandidate]


class LogFoodResponse(BaseModel):
    entry: FoodEntryResponse
    scaling_confidence: str
    day_totals: MacroTotals
    remaining_vs_target: MacroTotals | None = None
    target: MacroTargets | None = None


class DaySummary(BaseModel):
    date: DateValue
    target: MacroTargets | None
    consumed: MacroTotals
    remaining: MacroTotals | None
    entries: list[FoodEntryResponse]


def _basis_label(food: dict[str, Any]) -> str:
    if food.get("serving_size") and food.get("serving_size_unit"):
        return f"per serving ({food['serving_size']} {food['serving_size_unit']})"
    return "per 100 g"


def _to_macro_totals(food: dict[str, Any]) -> MacroTotals:
    return MacroTotals(
        calories=int(food.get("calories") or 0),
        protein_g=float(food.get("protein_g") or 0.0),
        carbs_g=float(food.get("carbs_g") or 0.0),
        fat_g=float(food.get("fat_g") or 0.0),
    )


def build_mcp(usda_getter) -> FastMCP:
    """Construct the FastMCP server. `usda_getter` is a callable returning the live USDAClient.

    Indirection lets callers bind to `app.get_usda_client` after lifespan startup without import cycles.
    """
    settings = get_settings()
    tz = ZoneInfo(settings.timezone)
    mcp = FastMCP(name="nutrition")
    mcp.add_middleware(ApiKeyMiddleware(settings.api_key))

    @mcp.tool
    async def search_food(
        description: str,
        quantity: str = "1 serving",
        limit: int = Field(default=3, ge=1, le=10),
    ) -> SearchFoodResponse:
        """Search USDA for foods matching `description`, scale macros to the parsed `quantity`.

        Returns the top matches (default 3) with a `recommended` flag on the first. Use the
        returned `fdc_id` with `log_food` to commit. Quantity accepts free text like "150g",
        "1 cup", "2 tbsp", "1 wrap"; when units are not gram-convertible, scaling falls back
        to count-of-serving with `scaling_confidence` set to "medium" or "low".
        """
        usda = usda_getter()
        results = await usda.search(description, page_size=max(limit, 5))
        parsed = parse_quantity(quantity)
        candidates: list[FoodCandidate] = []
        for idx, food in enumerate(results[:limit]):
            scaled, confidence = scale_macros(food, parsed)
            candidates.append(
                FoodCandidate(
                    fdc_id=int(food["fdc_id"]),
                    description=str(food["description"]),
                    serving_size=food.get("serving_size"),
                    serving_size_unit=food.get("serving_size_unit"),
                    per_basis=_to_macro_totals(food),
                    basis_label=_basis_label(food),
                    scaled_for_quantity=MacroTotals(**scaled),
                    scaling_confidence=confidence,
                    recommended=(idx == 0),
                )
            )
        return SearchFoodResponse(
            query=description,
            parsed_quantity=ParsedQuantityOut(
                value=parsed.value,
                unit=parsed.unit,
                grams=parsed.grams,
                is_count=parsed.is_count,
            ),
            candidates=candidates,
        )

    @mcp.tool
    async def log_food(
        fdc_id: int,
        quantity: str,
        display_name: str | None = None,
    ) -> LogFoodResponse:
        """Log a food entry for today (server timezone).

        Pass `fdc_id` from a prior `search_food` call. `quantity` is free text; the server
        parses it and scales macros server-side. `display_name` overrides the verbose USDA
        description with a friendlier label.
        """
        usda = usda_getter()
        now = DateTimeValue.now(tz=tz)
        async with get_session() as session:
            created_row, day_rows, confidence = await log_food_one_shot(
                session=session,
                usda=usda,
                user_key=settings.default_user_key,
                fdc_id=fdc_id,
                quantity_text=quantity,
                display_name_override=display_name,
                now=now,
            )

            day_totals = sum_food_entry_macros(
                [FoodEntryResponse(**row) for row in day_rows]
            )

            targets_repo = TargetsRepository(session)
            target_row = await targets_repo.get_target_profile(settings.default_user_key)

        target_obj: MacroTargets | None = None
        remaining: MacroTotals | None = None
        if target_row is not None:
            target_obj = MacroTargets(
                calories=int(target_row["calories_target"]),
                protein_g=float(target_row["protein_g_target"]),
                carbs_g=float(target_row["carbs_g_target"]),
                fat_g=float(target_row["fat_g_target"]),
            )
            remaining = MacroTotals(
                calories=target_obj.calories - day_totals.calories,
                protein_g=round(target_obj.protein_g - day_totals.protein_g, 1),
                carbs_g=round(target_obj.carbs_g - day_totals.carbs_g, 1),
                fat_g=round(target_obj.fat_g - day_totals.fat_g, 1),
            )

        return LogFoodResponse(
            entry=FoodEntryResponse(**created_row),
            scaling_confidence=confidence,
            day_totals=day_totals,
            remaining_vs_target=remaining,
            target=target_obj,
        )

    @mcp.tool
    async def get_day(date: str | None = None) -> DaySummary:
        """Return entries + totals for `date` (YYYY-MM-DD). Defaults to today in server timezone.

        Returns null target/remaining when no targets are configured (call `set_targets` first).
        """
        if date is None:
            day = DateTimeValue.now(tz=tz).date()
        else:
            try:
                day = DateValue.fromisoformat(date)
            except ValueError as exc:
                raise ToolError(f"Invalid date '{date}', expected YYYY-MM-DD") from exc

        async with get_session() as session:
            try:
                summary = await build_daily_summary(
                    session=session,
                    user_key=settings.default_user_key,
                    summary_date=day,
                )
                return DaySummary(
                    date=summary.date,
                    target=summary.target,
                    consumed=summary.consumed,
                    remaining=summary.remaining,
                    entries=summary.entries,
                )
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                # No targets — still return entries + consumed.
                from nutrition_server.services.log_ids import daily_log_id

                entries_repo = EntriesRepository(session)
                rows = await entries_repo.list_entries_by_daily_log_id(
                    daily_log_id(settings.default_user_key, day)
                )
                entries = [FoodEntryResponse(**row) for row in rows]
                return DaySummary(
                    date=day,
                    target=None,
                    consumed=sum_food_entry_macros(entries),
                    remaining=None,
                    entries=entries,
                )

    @mcp.tool
    async def delete_entry(entry_id: str) -> dict[str, bool]:
        """Delete a food entry by UUID. Returns {"deleted": true|false}."""
        try:
            entry_uuid = UUID(entry_id)
        except ValueError as exc:
            raise ToolError(f"Invalid entry_id '{entry_id}'") from exc

        async with get_session() as session:
            repo = EntriesRepository(session)
            async with transaction(session):
                deleted = await repo.delete_entry(entry_uuid)
        return {"deleted": deleted}

    @mcp.tool
    async def get_targets() -> MacroTargets | None:
        """Return the configured macro targets, or null if none are set."""
        async with get_session() as session:
            repo = TargetsRepository(session)
            row = await repo.get_target_profile(settings.default_user_key)
        if row is None:
            return None
        return MacroTargets(
            calories=int(row["calories_target"]),
            protein_g=float(row["protein_g_target"]),
            carbs_g=float(row["carbs_g_target"]),
            fat_g=float(row["fat_g_target"]),
        )

    @mcp.tool
    async def set_targets(
        calories: int = Field(gt=0),
        protein_g: float = Field(ge=0),
        carbs_g: float = Field(ge=0),
        fat_g: float = Field(ge=0),
    ) -> MacroTargets:
        """Upsert the macro targets profile. Targets seldom change; call when starting or revising."""
        now = DateTimeValue.now(tz=tz)
        async with get_session() as session:
            repo = TargetsRepository(session)
            async with transaction(session):
                await repo.upsert_targets(
                    user_key=settings.default_user_key,
                    calories=calories,
                    protein_g=protein_g,
                    carbs_g=carbs_g,
                    fat_g=fat_g,
                    updated_at=now,
                )
        return MacroTargets(calories=calories, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g)

    return mcp
