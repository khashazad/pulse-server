from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from nutrition_server.services.log_food_service import log_food_one_shot


@pytest.mark.asyncio
async def test_log_food_one_shot_scales_and_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    usda = MagicMock()
    usda.get_food = AsyncMock(
        return_value={
            "fdc_id": 9999,
            "description": "Chicken Breast, Roasted",
            "calories": 165,
            "protein_g": 31.0,
            "carbs_g": 0.0,
            "fat_g": 3.6,
            "serving_size": None,
            "serving_size_unit": None,
        }
    )

    captured: dict = {}

    async def fake_create_entries_with_side_effects(*, session, user_key, items, now):
        captured["items"] = items
        captured["user_key"] = user_key
        item = items[0]
        row = {
            "id": "00000000-0000-0000-0000-000000000001",
            "daily_log_id": "00000000-0000-0000-0000-000000000002",
            "user_key": user_key,
            "entry_group_id": "00000000-0000-0000-0000-000000000003",
            "display_name": item.display_name,
            "quantity_text": item.quantity_text,
            "normalized_quantity_value": item.normalized_quantity_value,
            "normalized_quantity_unit": item.normalized_quantity_unit,
            "usda_fdc_id": item.usda_fdc_id,
            "usda_description": item.usda_description,
            "calories": item.calories,
            "protein_g": item.protein_g,
            "carbs_g": item.carbs_g,
            "fat_g": item.fat_g,
            "consumed_at": now,
            "created_at": now,
        }
        return [row], [row]

    monkeypatch.setattr(
        "nutrition_server.services.log_food_service.create_entries_with_side_effects",
        fake_create_entries_with_side_effects,
    )

    now = datetime(2026, 5, 4, 13, 30, tzinfo=ZoneInfo("America/Toronto"))
    created, day_rows, confidence = await log_food_one_shot(
        session=MagicMock(),
        usda=usda,
        user_key="default",
        fdc_id=9999,
        quantity_text="200g",
        display_name_override=None,
        now=now,
    )

    assert confidence == "high"
    assert created["calories"] == 330  # 165 * 2
    assert created["protein_g"] == 62.0
    assert created["display_name"] == "Chicken Breast, Roasted"
    assert created["quantity_text"] == "200g"
    assert len(day_rows) == 1


@pytest.mark.asyncio
async def test_log_food_one_shot_uses_display_name_override(monkeypatch: pytest.MonkeyPatch) -> None:
    usda = MagicMock()
    usda.get_food = AsyncMock(
        return_value={
            "fdc_id": 1234,
            "description": "Wrap, Branded Whatever",
            "calories": 300,
            "protein_g": 15.0,
            "carbs_g": 30.0,
            "fat_g": 12.0,
            "serving_size": 1.0,
            "serving_size_unit": "wrap",
        }
    )

    async def fake_create(*, session, user_key, items, now):
        item = items[0]
        row = {
            "id": "00000000-0000-0000-0000-000000000001",
            "daily_log_id": "00000000-0000-0000-0000-000000000002",
            "user_key": user_key,
            "entry_group_id": "00000000-0000-0000-0000-000000000003",
            "display_name": item.display_name,
            "quantity_text": item.quantity_text,
            "normalized_quantity_value": item.normalized_quantity_value,
            "normalized_quantity_unit": item.normalized_quantity_unit,
            "usda_fdc_id": item.usda_fdc_id,
            "usda_description": item.usda_description,
            "calories": item.calories,
            "protein_g": item.protein_g,
            "carbs_g": item.carbs_g,
            "fat_g": item.fat_g,
            "consumed_at": now,
            "created_at": now,
        }
        return [row], [row]

    monkeypatch.setattr(
        "nutrition_server.services.log_food_service.create_entries_with_side_effects",
        fake_create,
    )

    now = datetime(2026, 5, 4, 13, 30, tzinfo=ZoneInfo("America/Toronto"))
    created, _, _ = await log_food_one_shot(
        session=MagicMock(),
        usda=usda,
        user_key="default",
        fdc_id=1234,
        quantity_text="1 wrap",
        display_name_override="Chicken Caesar Wrap",
        now=now,
    )
    assert created["display_name"] == "Chicken Caesar Wrap"
    assert created["usda_description"] == "Wrap, Branded Whatever"
