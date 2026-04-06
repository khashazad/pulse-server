from __future__ import annotations

from datetime import date as DateValue

from fastapi import APIRouter, Depends, Query

from nutrition_server.auth import require_api_key
from nutrition_server.config import get_settings
from nutrition_server.db import get_conn
from nutrition_server.models import DailyLogSummary, LogsListResponse

settings = get_settings()
router = APIRouter(dependencies=[Depends(require_api_key)])


# Summary: Lists historical daily logs for a user across a date range.
# Parameters:
# - from_date (datetime.date): Inclusive start date for returned logs.
# - to_date (datetime.date): Inclusive end date for returned logs.
# - user_key (str | None): Optional user identifier override.
# Returns:
# - LogsListResponse: Daily aggregate totals and entry counts ordered by date desc.
# Raises/Throws:
# - RuntimeError: Raised when the database pool is not initialized.
# - psycopg.Error: Raised when SQL execution fails.
@router.get("/logs", response_model=LogsListResponse)
async def list_logs(
    from_date: DateValue = Query(alias="from"),
    to_date: DateValue = Query(alias="to"),
    user_key: str | None = Query(default=None),
) -> LogsListResponse:
    effective_user_key = user_key or settings.default_user_key
    async with get_conn() as conn:
        cur = await conn.execute(
            """SELECT dl.log_date,
                      COALESCE(SUM(fe.calories), 0)::int AS total_calories,
                      COALESCE(SUM(fe.protein_g), 0)::numeric AS total_protein_g,
                      COALESCE(SUM(fe.carbs_g), 0)::numeric AS total_carbs_g,
                      COALESCE(SUM(fe.fat_g), 0)::numeric AS total_fat_g,
                      COUNT(fe.id)::int AS entry_count
               FROM daily_logs dl
               LEFT JOIN food_entries fe ON fe.daily_log_id = dl.id
               WHERE dl.user_key = %s AND dl.log_date >= %s AND dl.log_date <= %s
               GROUP BY dl.log_date
               ORDER BY dl.log_date DESC""",
            (effective_user_key, from_date, to_date),
        )
        rows = await cur.fetchall()

    return LogsListResponse(
        logs=[
            DailyLogSummary(
                date=row["log_date"],
                total_calories=int(row["total_calories"]),
                total_protein_g=float(row["total_protein_g"]),
                total_carbs_g=float(row["total_carbs_g"]),
                total_fat_g=float(row["total_fat_g"]),
                entry_count=int(row["entry_count"]),
            )
            for row in rows
        ]
    )
