"""Unit tests for the service-layer orchestration logic.

Services compose repositories and other services; here the repository
classes and cross-service helpers are patched on each service module so the
orchestration logic (validation, error mapping, row adaptation, fan-out)
runs without a database. The compiled SQL these services build is covered by
the integration suite.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# asyncio_mode = "auto" (see pyproject) runs async tests without an explicit
# marker; sync helper tests in this module stay synchronous.


def _now() -> datetime:
    """Return a fixed aware UTC timestamp."""
    return datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)


def _repo(**methods):
    """Build a fake repository class whose instances carry the given methods.

    **Inputs:**
    - methods: ``method_name=return_value`` (wrapped in ``AsyncMock``) or an
      explicit ``AsyncMock`` (used as-is for ``side_effect`` cases).

    **Outputs:**
    - tuple: ``(class_mock, instance_mock)``.
    """
    inst = MagicMock()
    for name, value in methods.items():
        setattr(inst, name, value if isinstance(value, AsyncMock) else AsyncMock(return_value=value))
    return MagicMock(return_value=inst), inst


def _noop_txn(module_path: str):
    """Return a patch that replaces ``<module>.transaction`` with a no-op async ctx."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=False)
    return patch(f"{module_path}.transaction", return_value=cm)


def _entry_row(**over) -> dict:
    """Build a ``food_entries`` row dict matching ``FoodEntryResponse``."""
    row = {
        "id": uuid.uuid4(),
        "daily_log_id": uuid.uuid4(),
        "user_key": "khash",
        "entry_group_id": uuid.uuid4(),
        "display_name": "Oatmeal",
        "quantity_text": "1 cup",
        "normalized_quantity_value": 1.0,
        "normalized_quantity_unit": "cup",
        "usda_fdc_id": 123,
        "usda_description": "Oats",
        "custom_food_id": None,
        "calories": 150,
        "protein_g": 5.0,
        "carbs_g": 27.0,
        "fat_g": 3.0,
        "meal_id": None,
        "meal_name": None,
        "consumed_at": _now(),
        "created_at": _now(),
    }
    row.update(over)
    return row


def _usda_item(**over):
    """Build a USDA-backed ``MealItemCreate`` payload."""
    from pulse_server.models.meals import MealItemCreate

    base = dict(
        display_name="Oatmeal",
        quantity_text="1 cup",
        usda_fdc_id=123,
        usda_description="Oats",
        calories=150,
        protein_g=5.0,
        carbs_g=27.0,
        fat_g=3.0,
    )
    base.update(over)
    return MealItemCreate(**base)


def _result(scalar_one_or_none=None, rows=None):
    """Build a stub ``execute`` result for the in-module alias/calorie queries."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.mappings.return_value = rows or []
    return result


# ---- meals_service ------------------------------------------------------------

MEALS = "pulse_server.services.meals_service"


async def test_create_meal_with_items_happy() -> None:
    """``create_meal_with_items`` inserts the meal and each item in order."""
    from pulse_server.services.meals_service import create_meal_with_items
    from pulse_server.models.meals import MealCreate

    meal = {"id": uuid.uuid4()}
    meals_cls, inst = _repo(create_meal=meal, add_meal_item={"id": uuid.uuid4()})
    with patch(f"{MEALS}.MealsRepository", meals_cls), patch(
        f"{MEALS}.assert_custom_foods_owned", new=AsyncMock(return_value=None)
    ):
        meal_row, item_rows = await create_meal_with_items(
            session=MagicMock(),
            user_key="khash",
            payload=MealCreate(name="Breakfast", items=[_usda_item(), _usda_item()]),
            now=_now(),
        )
    assert meal_row is meal
    assert len(item_rows) == 2


async def test_create_meal_with_items_rejects_bad_source() -> None:
    """An item with neither food source raises 422."""
    from pulse_server.services.meals_service import create_meal_with_items
    from pulse_server.models.meals import MealCreate, MealItemCreate

    bad = MealItemCreate(
        display_name="x", quantity_text="1", calories=1, protein_g=0.0, carbs_g=0.0, fat_g=0.0
    )
    with pytest.raises(HTTPException) as exc:
        await create_meal_with_items(
            session=MagicMock(),
            user_key="khash",
            payload=MealCreate(name="m", items=[bad]),
            now=_now(),
        )
    assert exc.value.status_code == 422


async def test_create_meal_with_items_usda_missing_description() -> None:
    """A USDA item without a description raises 422."""
    from pulse_server.services.meals_service import create_meal_with_items
    from pulse_server.models.meals import MealCreate, MealItemCreate

    item = MealItemCreate(
        display_name="x", quantity_text="1", usda_fdc_id=1,
        calories=1, protein_g=0.0, carbs_g=0.0, fat_g=0.0,
    )
    with pytest.raises(HTTPException) as exc:
        await create_meal_with_items(
            session=MagicMock(),
            user_key="khash",
            payload=MealCreate(name="m", items=[item]),
            now=_now(),
        )
    assert exc.value.status_code == 422


async def test_create_meal_with_items_cross_tenant() -> None:
    """A cross-tenant custom-food reference maps to 422."""
    from pulse_server.services.meals_service import create_meal_with_items
    from pulse_server.services.custom_foods_service import CrossTenantReferenceError
    from pulse_server.models.meals import MealCreate

    item = _usda_item(usda_fdc_id=None, usda_description=None, custom_food_id=uuid.uuid4())
    with patch(
        f"{MEALS}.assert_custom_foods_owned",
        new=AsyncMock(side_effect=CrossTenantReferenceError("nope")),
    ):
        with pytest.raises(HTTPException) as exc:
            await create_meal_with_items(
                session=MagicMock(),
                user_key="khash",
                payload=MealCreate(name="m", items=[item]),
                now=_now(),
            )
    assert exc.value.status_code == 422


async def test_create_meal_with_items_alias_collision() -> None:
    """An alias colliding with an existing meal maps to 409."""
    from pulse_server.services.meals_service import create_meal_with_items
    from pulse_server.models.meals import MealCreate

    with patch(f"{MEALS}.assert_custom_foods_owned", new=AsyncMock(return_value=None)), patch(
        f"{MEALS}.assert_meal_alias_available", new=AsyncMock(side_effect=ValueError("taken"))
    ):
        with pytest.raises(HTTPException) as exc:
            await create_meal_with_items(
                session=MagicMock(),
                user_key="khash",
                payload=MealCreate(name="m", items=[_usda_item()], aliases=["other"]),
                now=_now(),
            )
    assert exc.value.status_code == 409


async def test_log_meal_happy() -> None:
    """``log_meal`` loads the meal, builds entries, and fans out to entry creation."""
    from pulse_server.services.meals_service import log_meal

    meal_id = uuid.uuid4()
    item = {
        "display_name": "Oatmeal",
        "quantity_text": "1 cup",
        "normalized_quantity_value": 1.0,
        "normalized_quantity_unit": "cup",
        "usda_fdc_id": 123,
        "usda_description": "Oats",
        "custom_food_id": None,
        "calories": 150,
        "protein_g": 5.0,
        "carbs_g": 27.0,
        "fat_g": 3.0,
    }
    meals_cls, _ = _repo(get_meal={"id": meal_id, "name": "Breakfast"}, list_items=[item])
    created = ([_entry_row()], [_entry_row()])
    with _noop_txn(MEALS), patch(f"{MEALS}.MealsRepository", meals_cls), patch(
        f"{MEALS}.create_entries_with_side_effects", new=AsyncMock(return_value=created)
    ) as svc:
        out = await log_meal(session=MagicMock(), user_key="khash", meal_id=meal_id, now=_now())
    assert out == created
    assert svc.await_args.kwargs["meal_name"] == "Breakfast"


async def test_log_meal_not_found() -> None:
    """``log_meal`` raises 404 when the meal is missing."""
    from pulse_server.services.meals_service import log_meal

    meals_cls, _ = _repo(get_meal=None)
    with _noop_txn(MEALS), patch(f"{MEALS}.MealsRepository", meals_cls):
        with pytest.raises(HTTPException) as exc:
            await log_meal(session=MagicMock(), user_key="khash", meal_id=uuid.uuid4(), now=_now())
    assert exc.value.status_code == 404


async def test_log_meal_no_items() -> None:
    """``log_meal`` raises 400 when the meal has no items."""
    from pulse_server.services.meals_service import log_meal

    meals_cls, _ = _repo(get_meal={"id": uuid.uuid4(), "name": "Empty"}, list_items=[])
    with _noop_txn(MEALS), patch(f"{MEALS}.MealsRepository", meals_cls):
        with pytest.raises(HTTPException) as exc:
            await log_meal(session=MagicMock(), user_key="khash", meal_id=uuid.uuid4(), now=_now())
    assert exc.value.status_code == 400


async def test_meals_assert_alias_available() -> None:
    """``assert_meal_alias_available`` raises only when a collision row exists."""
    from pulse_server.services.meals_service import assert_meal_alias_available

    session = MagicMock()
    session.execute = AsyncMock(return_value=_result(scalar_one_or_none=None))
    await assert_meal_alias_available(session=session, user_key="k", alias="a", exclude_meal_id=None)

    session.execute = AsyncMock(return_value=_result(scalar_one_or_none="breakfast"))
    with pytest.raises(ValueError):
        await assert_meal_alias_available(
            session=session, user_key="k", alias="a", exclude_meal_id=uuid.uuid4()
        )


def test_meals_normalize_alias_list() -> None:
    """``normalize_alias_list`` dedupes, drops empties and the canonical name."""
    from pulse_server.services.meals_service import normalize_alias_list

    out = normalize_alias_list(["AM Meal", "am meal", "", "breakfast"], "breakfast")
    assert out == ["am meal"]


# ---- entries_service ----------------------------------------------------------

ENTRIES = "pulse_server.services.entries_service"


async def test_create_entries_single_date() -> None:
    """A single-date batch returns the created rows plus the full daily log."""
    from pulse_server.services.entries_service import create_entries_with_side_effects
    from pulse_server.models import FoodEntryCreate

    entries_cls, inst = _repo(
        ensure_daily_log=None,
        create_food_entry=_entry_row(),
        list_entries_by_daily_log_id=[_entry_row(), _entry_row()],
    )
    item = FoodEntryCreate(
        display_name="Oats", quantity_text="1 cup", usda_fdc_id=1, usda_description="d",
        calories=150, protein_g=5.0, carbs_g=27.0, fat_g=3.0,
    )
    with _noop_txn(ENTRIES), patch(f"{ENTRIES}.EntriesRepository", entries_cls), patch(
        f"{ENTRIES}.assert_custom_foods_owned", new=AsyncMock(return_value=None)
    ):
        created, totals = await create_entries_with_side_effects(
            session=MagicMock(), user_key="khash", items=[item], now=_now()
        )
    assert len(created) == 1
    assert len(totals) == 2  # full daily log path
    inst.ensure_daily_log.assert_awaited()


async def test_create_entries_empty_batch() -> None:
    """An empty batch falls back to today's daily log for totals."""
    from pulse_server.services.entries_service import create_entries_with_side_effects

    entries_cls, _ = _repo(list_entries_by_daily_log_id=[_entry_row()])
    with _noop_txn(ENTRIES), patch(f"{ENTRIES}.EntriesRepository", entries_cls), patch(
        f"{ENTRIES}.assert_custom_foods_owned", new=AsyncMock(return_value=None)
    ):
        created, totals = await create_entries_with_side_effects(
            session=MagicMock(), user_key="khash", items=[], now=_now()
        )
    assert created == []
    assert len(totals) == 1


async def test_create_entries_multi_date_uses_created_rows() -> None:
    """A multi-date batch returns just the created rows for totals."""
    from pulse_server.services.entries_service import create_entries_with_side_effects
    from pulse_server.models import FoodEntryCreate

    entries_cls, _ = _repo(ensure_daily_log=None, create_food_entry=_entry_row())
    day1 = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
    items = [
        FoodEntryCreate(
            display_name="A", quantity_text="1", usda_fdc_id=1, usda_description="d",
            calories=1, protein_g=0.0, carbs_g=0.0, fat_g=0.0, consumed_at=day1,
        ),
        FoodEntryCreate(
            display_name="B", quantity_text="1", usda_fdc_id=1, usda_description="d",
            calories=1, protein_g=0.0, carbs_g=0.0, fat_g=0.0, consumed_at=day2,
        ),
    ]
    with patch(f"{ENTRIES}.EntriesRepository", entries_cls), patch(
        f"{ENTRIES}.assert_custom_foods_owned", new=AsyncMock(return_value=None)
    ):
        created, totals = await create_entries_with_side_effects(
            session=MagicMock(), user_key="khash", items=items, now=_now(), manage_transaction=False
        )
    assert len(created) == 2
    assert len(totals) == 2  # created rows, not a daily-log re-read


# ---- food_memory_service ------------------------------------------------------

FM = "pulse_server.services.food_memory_service"


async def test_resolve_food_none() -> None:
    """``resolve_food_by_name`` returns ``type=none`` on a miss."""
    from pulse_server.services.food_memory_service import resolve_food_by_name

    fm_cls, _ = _repo(get_by_name=None)
    with patch(f"{FM}.FoodMemoryRepository", fm_cls):
        out = await resolve_food_by_name(session=MagicMock(), user_key="k", name="ghost")
    assert out.type == "none"


async def test_resolve_food_usda() -> None:
    """A USDA-pointer row resolves to ``type=memory_usda``."""
    from pulse_server.services.food_memory_service import resolve_food_by_name

    row = {
        "name": "oatmeal", "custom_food_id": None, "usda_fdc_id": 123, "usda_description": "Oats",
        "basis": "per_100g", "serving_size": None, "serving_size_unit": None,
        "calories": 150, "protein_g": 5.0, "carbs_g": 27.0, "fat_g": 3.0,
    }
    fm_cls, _ = _repo(get_by_name=row)
    with patch(f"{FM}.FoodMemoryRepository", fm_cls):
        out = await resolve_food_by_name(session=MagicMock(), user_key="k", name="oatmeal")
    assert out.type == "memory_usda"
    assert out.usda_fdc_id == 123


async def test_resolve_food_custom() -> None:
    """A custom-food-pointer row resolves to ``type=custom_food`` with the joined food."""
    from pulse_server.services.food_memory_service import resolve_food_by_name

    cfid = uuid.uuid4()
    row = {
        "name": "wrap", "custom_food_id": cfid,
        "cf_basis": "per_serving", "cf_serving_size": 1.0, "cf_serving_size_unit": "wrap",
        "cf_calories": 300, "cf_protein_g": 25.0, "cf_carbs_g": 30.0, "cf_fat_g": 10.0,
        "cf_id": cfid, "cf_user_key": "k", "cf_name": "Wrap", "cf_normalized_name": "wrap",
        "cf_source": "manual", "cf_notes": None, "cf_created_at": _now(), "cf_updated_at": _now(),
    }
    fm_cls, _ = _repo(get_by_name=row)
    with patch(f"{FM}.FoodMemoryRepository", fm_cls):
        out = await resolve_food_by_name(session=MagicMock(), user_key="k", name="wrap")
    assert out.type == "custom_food"
    assert out.custom_food is not None
    assert out.custom_food.name == "Wrap"


async def test_assert_food_alias_available() -> None:
    """``assert_food_alias_available`` raises only on a collision row."""
    from pulse_server.services.food_memory_service import assert_food_alias_available

    session = MagicMock()
    session.execute = AsyncMock(return_value=_result(scalar_one_or_none=None))
    await assert_food_alias_available(
        session=session, user_key="k", alias="a", exclude_normalized_name="oatmeal"
    )
    session.execute = AsyncMock(return_value=_result(scalar_one_or_none="oatmeal"))
    with pytest.raises(ValueError):
        await assert_food_alias_available(
            session=session, user_key="k", alias="a", exclude_normalized_name=None
        )


def test_food_memory_normalize_alias_list() -> None:
    """``normalize_alias_list`` dedupes and drops the canonical name."""
    from pulse_server.services.food_memory_service import normalize_alias_list

    assert normalize_alias_list(["Porridge", "porridge", "oatmeal"], "oatmeal") == ["porridge"]


# ---- summary_service ----------------------------------------------------------

SUMMARY = "pulse_server.services.summary_service"


async def test_build_daily_summary_happy() -> None:
    """``build_daily_summary`` returns target/consumed/remaining plus entries."""
    from pulse_server.services.summary_service import build_daily_summary

    targets_cls, _ = _repo(get_target_profile={
        "calories_target": 2000, "protein_g_target": 150.0,
        "carbs_g_target": 200.0, "fat_g_target": 60.0,
    })
    entries_cls, _ = _repo(list_entries_by_daily_log_id=[_entry_row()])
    with patch(f"{SUMMARY}.TargetsRepository", targets_cls), patch(
        f"{SUMMARY}.EntriesRepository", entries_cls
    ):
        out = await build_daily_summary(session=MagicMock(), user_key="khash", summary_date=date(2026, 5, 20))
    assert out.target.calories == 2000
    assert out.consumed.calories == 150
    assert out.remaining.calories == 1850


async def test_build_daily_summary_404() -> None:
    """``build_daily_summary`` raises 404 when no target profile exists."""
    from pulse_server.services.summary_service import build_daily_summary

    targets_cls, _ = _repo(get_target_profile=None)
    with patch(f"{SUMMARY}.TargetsRepository", targets_cls):
        with pytest.raises(HTTPException) as exc:
            await build_daily_summary(session=MagicMock(), user_key="khash", summary_date=date(2026, 5, 20))
    assert exc.value.status_code == 404


async def test_daily_calorie_totals() -> None:
    """``daily_calorie_totals`` adapts grouped rows into ``CaloriesDailyRow``."""
    from pulse_server.services.summary_service import daily_calorie_totals

    session = MagicMock()
    session.execute = AsyncMock(
        return_value=_result(rows=[{"log_date": date(2026, 5, 20), "calories": 1800}])
    )
    out = await daily_calorie_totals(
        session=session, user_key="k", from_date=date(2026, 5, 1), to_date=date(2026, 5, 31)
    )
    assert out[0].calories == 1800


# ---- custom_foods_service -----------------------------------------------------

CF = "pulse_server.services.custom_foods_service"


async def test_assert_custom_foods_owned_paths() -> None:
    """Owned ids pass, ``None`` ids are skipped, unowned ids raise."""
    from pulse_server.services.custom_foods_service import (
        assert_custom_foods_owned,
        CrossTenantReferenceError,
    )

    owned_cls, _ = _repo(get_by_id={"id": uuid.uuid4()})
    with patch(f"{CF}.CustomFoodsRepository", owned_cls):
        await assert_custom_foods_owned(MagicMock(), "k", [uuid.uuid4(), None, None])

    missing_cls, _ = _repo(get_by_id=None)
    with patch(f"{CF}.CustomFoodsRepository", missing_cls):
        with pytest.raises(CrossTenantReferenceError):
            await assert_custom_foods_owned(MagicMock(), "k", [uuid.uuid4()])


async def test_upsert_custom_food_and_remember() -> None:
    """``upsert_custom_food_and_remember`` upserts the food then writes memory."""
    from pulse_server.services.custom_foods_service import upsert_custom_food_and_remember
    from pulse_server.models import CustomFoodCreate

    food = {"id": uuid.uuid4(), "name": "Wrap"}
    cf_cls, _ = _repo(upsert=food)
    fm_cls, fm_inst = _repo(upsert_custom={"id": uuid.uuid4()})
    with patch(f"{CF}.CustomFoodsRepository", cf_cls), patch(f"{CF}.FoodMemoryRepository", fm_cls):
        out = await upsert_custom_food_and_remember(
            session=MagicMock(),
            user_key="k",
            payload=CustomFoodCreate(
                name="Wrap", basis="per_serving", calories=300, protein_g=25.0, carbs_g=30.0, fat_g=10.0
            ),
            now=_now(),
        )
    assert out is food
    fm_inst.upsert_custom.assert_awaited_once()


# ---- weight_service -----------------------------------------------------------

WS = "pulse_server.services.weight_service"


def _weight_row(**over) -> dict:
    """Build a ``weight_entries`` row dict for ``WeightEntryResponse``."""
    row = {
        "id": uuid.uuid4(),
        "user_key": "khash",
        "log_date": date(2026, 5, 20),
        "weight_lb": Decimal("180.50"),
        "source_unit": "lb",
        "created_at": _now(),
        "updated_at": _now(),
    }
    row.update(over)
    return row


def test_validate_log_date_paths() -> None:
    """``validate_log_date`` rejects future dates and dates too far in the past."""
    from pulse_server.services.weight_service import validate_log_date

    validate_log_date(date(2026, 5, 19), date(2026, 5, 20))  # ok
    with pytest.raises(ValueError):
        validate_log_date(date(2026, 5, 21), date(2026, 5, 20))  # future
    with pytest.raises(ValueError):
        validate_log_date(date(2000, 1, 1), date(2026, 5, 20))  # too far past


async def test_upsert_weight() -> None:
    """``upsert_weight`` normalizes the unit and returns the upserted entry."""
    from pulse_server.services.weight_service import upsert_weight

    w_cls, inst = _repo(upsert=_weight_row())
    with patch(f"{WS}.WeightRepository", w_cls):
        out = await upsert_weight(
            session=MagicMock(), user_key="khash", log_date=date(2026, 5, 20),
            weight=Decimal("70"), unit="kg", now=_now(),
        )
    assert out.source_unit == "lb"  # row fixture; conversion happens before the repo call
    # kg input is normalized to lb before the repository sees it.
    assert inst.upsert.await_args.kwargs["weight_lb"] == Decimal("154.32")


async def test_list_weight_range() -> None:
    """``list_weight_range`` validates the range then maps rows to responses."""
    from pulse_server.services.weight_service import list_weight_range

    w_cls, _ = _repo(list_range=[_weight_row(), _weight_row()])
    with patch(f"{WS}.WeightRepository", w_cls):
        out = await list_weight_range(
            session=MagicMock(), user_key="khash", from_date=date(2026, 5, 1), to_date=date(2026, 5, 31)
        )
    assert len(out) == 2


async def test_list_weight_range_invalid() -> None:
    """``list_weight_range`` propagates the range validation error."""
    from pulse_server.services.weight_service import list_weight_range

    with pytest.raises(ValueError):
        await list_weight_range(
            session=MagicMock(), user_key="khash", from_date=date(2026, 5, 31), to_date=date(2026, 5, 1)
        )


async def test_get_weight_some_and_none() -> None:
    """``get_weight`` returns a response when present and ``None`` when absent."""
    from pulse_server.services.weight_service import get_weight

    some_cls, _ = _repo(get_by_date=_weight_row())
    with patch(f"{WS}.WeightRepository", some_cls):
        assert await get_weight(session=MagicMock(), user_key="k", log_date=date(2026, 5, 20)) is not None
    none_cls, _ = _repo(get_by_date=None)
    with patch(f"{WS}.WeightRepository", none_cls):
        assert await get_weight(session=MagicMock(), user_key="k", log_date=date(2026, 5, 20)) is None


async def test_delete_weight() -> None:
    """``delete_weight`` forwards the repository's boolean result."""
    from pulse_server.services.weight_service import delete_weight

    w_cls, _ = _repo(delete=True)
    with patch(f"{WS}.WeightRepository", w_cls):
        assert await delete_weight(session=MagicMock(), user_key="k", log_date=date(2026, 5, 20)) is True
