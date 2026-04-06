from __future__ import annotations

from datetime import datetime as DateTimeValue
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from nutrition_server.auth import require_api_key
from nutrition_server.config import get_settings
from nutrition_server.db import get_conn
from nutrition_server.models import MacroTargets

settings = get_settings()
router = APIRouter(dependencies=[Depends(require_api_key)])
TZ = ZoneInfo(settings.timezone)


# Summary: Fetches the user's currently configured macro targets.
# Parameters:
# - user_key (str | None): Optional user identifier override.
# Returns:
# - MacroTargets: Active calorie/protein/carbs/fat targets for the user.
# Raises/Throws:
# - fastapi.HTTPException: Raised with 404 when no target profile exists for the user.
# - RuntimeError: Raised when the database pool is not initialized.
# - psycopg.Error: Raised when SQL execution fails.
@router.get("/targets", response_model=MacroTargets)
async def get_targets(user_key: str | None = Query(default=None)) -> MacroTargets:
    effective_user_key = user_key or settings.default_user_key
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM daily_target_profile WHERE user_key = %s LIMIT 1",
            (effective_user_key,),
        )
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"No target profile for user {effective_user_key}")

    return MacroTargets(
        calories=int(row["calories_target"]),
        protein_g=float(row["protein_g_target"]),
        carbs_g=float(row["carbs_g_target"]),
        fat_g=float(row["fat_g_target"]),
    )


# Summary: Creates or updates the user's macro target profile.
# Parameters:
# - body (MacroTargets): Requested macro target values.
# - user_key (str | None): Optional user identifier override.
# Returns:
# - MacroTargets: Persisted macro target values.
# Raises/Throws:
# - RuntimeError: Raised when the database pool is not initialized.
# - psycopg.Error: Raised when SQL execution fails.
@router.put("/targets", response_model=MacroTargets)
async def update_targets(
    body: MacroTargets,
    user_key: str | None = Query(default=None),
) -> MacroTargets:
    effective_user_key = user_key or settings.default_user_key
    now = DateTimeValue.now(tz=TZ)
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO daily_target_profile (
                   user_key, calories_target, protein_g_target, carbs_g_target, fat_g_target
               ) VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (user_key)
               DO UPDATE SET
                   calories_target = EXCLUDED.calories_target,
                   protein_g_target = EXCLUDED.protein_g_target,
                   carbs_g_target = EXCLUDED.carbs_g_target,
                   fat_g_target = EXCLUDED.fat_g_target,
                   updated_at = %s""",
            (
                effective_user_key,
                body.calories,
                body.protein_g,
                body.carbs_g,
                body.fat_g,
                now,
            ),
        )

    return body
