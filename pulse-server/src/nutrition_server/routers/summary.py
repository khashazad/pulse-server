from __future__ import annotations

from datetime import date as DateValue

from fastapi import APIRouter, Depends, HTTPException, Query

from nutrition_server.auth import require_api_key
from nutrition_server.config import get_settings
from nutrition_server.db import get_conn
from nutrition_server.models import DailySummaryResponse, FoodEntryResponse, MacroTargets, MacroTotals
from nutrition_server.routers.entries import _daily_log_id

settings = get_settings()
router = APIRouter(dependencies=[Depends(require_api_key)])


# Summary: Returns a daily nutrition summary combining targets, consumed totals, and remaining budget.
# Parameters:
# - summary_date (datetime.date): Date whose nutrition summary is requested.
# - user_key (str | None): Optional user identifier override.
# Returns:
# - DailySummaryResponse: Per-day targets, consumed totals, remaining totals, and raw entries.
# Raises/Throws:
# - fastapi.HTTPException: Raised with 404 when no target profile exists for the user.
# - RuntimeError: Raised when the database pool is not initialized.
# - psycopg.Error: Raised when SQL execution fails.
@router.get("/summary/{summary_date}", response_model=DailySummaryResponse)
async def daily_summary(
    summary_date: DateValue,
    user_key: str | None = Query(default=None),
) -> DailySummaryResponse:
    effective_user_key = user_key or settings.default_user_key
    daily_log_id = _daily_log_id(effective_user_key, summary_date)

    async with get_conn() as conn:
        target_cur = await conn.execute(
            "SELECT * FROM daily_target_profile WHERE user_key = %s LIMIT 1",
            (effective_user_key,),
        )
        target_row = await target_cur.fetchone()
        if target_row is None:
            raise HTTPException(status_code=404, detail=f"No target profile for user {effective_user_key}")

        entries_cur = await conn.execute(
            "SELECT * FROM food_entries WHERE daily_log_id = %s ORDER BY consumed_at",
            (daily_log_id,),
        )
        rows = await entries_cur.fetchall()

    target = MacroTargets(
        calories=int(target_row["calories_target"]),
        protein_g=float(target_row["protein_g_target"]),
        carbs_g=float(target_row["carbs_g_target"]),
        fat_g=float(target_row["fat_g_target"]),
    )
    entries = [FoodEntryResponse(**row) for row in rows]
    consumed = MacroTotals(
        calories=sum(entry.calories for entry in entries),
        protein_g=round(sum(entry.protein_g for entry in entries), 1),
        carbs_g=round(sum(entry.carbs_g for entry in entries), 1),
        fat_g=round(sum(entry.fat_g for entry in entries), 1),
    )
    remaining = MacroTotals(
        calories=target.calories - consumed.calories,
        protein_g=round(target.protein_g - consumed.protein_g, 1),
        carbs_g=round(target.carbs_g - consumed.carbs_g, 1),
        fat_g=round(target.fat_g - consumed.fat_g, 1),
    )
    return DailySummaryResponse(
        date=summary_date,
        target=target,
        consumed=consumed,
        remaining=remaining,
        entries=entries,
    )
