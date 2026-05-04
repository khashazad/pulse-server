from __future__ import annotations

from datetime import datetime as DateTimeValue
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from nutrition_server.models import FoodEntryCreate
from nutrition_server.quantity import parse_quantity, scale_macros
from nutrition_server.services.entries_service import create_entries_with_side_effects
from nutrition_server.usda import USDAClient


async def log_food_one_shot(
    *,
    session: AsyncSession,
    usda: USDAClient,
    user_key: str,
    fdc_id: int,
    quantity_text: str,
    display_name_override: str | None,
    now: DateTimeValue,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Resolve a USDA food, scale to quantity, and persist a single entry.

    Returns `(created_row, day_rows, confidence)`. `day_rows` are all rows for the entry's
    log date — used by callers to compute day totals.
    """
    food = await usda.get_food(fdc_id)
    parsed = parse_quantity(quantity_text)
    scaled, confidence = scale_macros(food, parsed)

    item = FoodEntryCreate(
        display_name=display_name_override or food["description"],
        quantity_text=quantity_text,
        normalized_quantity_value=parsed.value if not parsed.is_count or parsed.grams is None else parsed.value,
        normalized_quantity_unit=parsed.unit,
        usda_fdc_id=int(food["fdc_id"]),
        usda_description=food["description"],
        calories=scaled["calories"],
        protein_g=scaled["protein_g"],
        carbs_g=scaled["carbs_g"],
        fat_g=scaled["fat_g"],
    )

    created_rows, day_rows = await create_entries_with_side_effects(
        session=session,
        user_key=user_key,
        items=[item],
        now=now,
    )
    return created_rows[0], day_rows, confidence
