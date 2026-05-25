"""Behavioral tests for the MCP tool handlers registered by ``build_mcp``.

Each registered FastMCP tool exposes its underlying coroutine as ``.fn``;
these tests call those coroutines directly with the module-level
``get_session`` / ``transaction`` and the repository classes / service
functions patched out, so the tool bodies (argument validation, row→DTO
adaptation, error mapping to ``ToolError``) run without a database. This
covers the ``mcp/server.py`` surface that the schema-only tests in
``test_mcp_tools.py`` do not exercise.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastmcp.exceptions import ToolError
from sqlalchemy.exc import IntegrityError

from pulse_server.models import MacroTotals
from pulse_server.models.entries import FoodEntryResponse
from pulse_server.models.food_memory import ResolvedFood
from pulse_server.services.custom_foods_service import CrossTenantReferenceError


SERVER = "pulse_server.mcp.server"


def _dt() -> datetime:
    """Return a fixed aware UTC timestamp for deterministic row fixtures."""
    return datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)


async def _fns(usda: MagicMock | None = None) -> dict:
    """Build a fresh MCP server and return a ``name → handler coroutine`` map.

    **Inputs:**
    - usda (MagicMock | None): Object returned by the server's ``usda_getter``;
      defaults to a bare ``MagicMock`` when the test does not exercise search.

    **Outputs:**
    - dict: Mapping of tool name to the registered tool's ``.fn`` coroutine.
    """
    from pulse_server.mcp import build_mcp

    mcp = build_mcp(lambda: usda or MagicMock())
    tools = await mcp.list_tools()
    return {t.name: t.fn for t in tools}


@contextlib.contextmanager
def patched(**module_attrs):
    """Patch ``get_session`` / ``transaction`` plus any named module globals.

    **Inputs:**
    - module_attrs: ``name=value`` pairs patched onto ``pulse_server.mcp.server``
      (typically repository classes or service functions).

    **Outputs:**
    - MagicMock: The fake DB session yielded by the patched ``get_session``.
    """
    session = MagicMock()
    sess_cm = MagicMock()
    sess_cm.__aenter__ = AsyncMock(return_value=session)
    sess_cm.__aexit__ = AsyncMock(return_value=False)
    txn_cm = MagicMock()
    txn_cm.__aenter__ = AsyncMock(return_value=None)
    txn_cm.__aexit__ = AsyncMock(return_value=False)

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch(f"{SERVER}.get_session", return_value=sess_cm))
        stack.enter_context(patch(f"{SERVER}.transaction", return_value=txn_cm))
        for name, value in module_attrs.items():
            stack.enter_context(patch(f"{SERVER}.{name}", value))
        yield session


def repo(**methods):
    """Build a fake repository class whose instances carry the given methods.

    **Inputs:**
    - methods: ``method_name=return_value`` (wrapped in an ``AsyncMock``) or an
      explicit ``AsyncMock`` (used as-is, e.g. to set ``side_effect``).

    **Outputs:**
    - tuple: ``(class_mock, instance_mock)`` where ``class_mock(session)``
      returns ``instance_mock``.
    """
    inst = MagicMock()
    for name, value in methods.items():
        setattr(inst, name, value if isinstance(value, AsyncMock) else AsyncMock(return_value=value))
    return MagicMock(return_value=inst), inst


# ---- row fixtures -------------------------------------------------------------


def entry_row(**over) -> dict:
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
        "consumed_at": _dt(),
        "created_at": _dt(),
    }
    row.update(over)
    return row


def custom_food_row(**over) -> dict:
    """Build a ``custom_foods`` row dict matching ``CustomFoodResponse``."""
    row = {
        "id": uuid.uuid4(),
        "user_key": "khash",
        "name": "Protein Wrap",
        "normalized_name": "protein wrap",
        "basis": "per_serving",
        "serving_size": 1.0,
        "serving_size_unit": "wrap",
        "calories": 300,
        "protein_g": 25.0,
        "carbs_g": 30.0,
        "fat_g": 10.0,
        "source": "manual",
        "notes": None,
        "created_at": _dt(),
        "updated_at": _dt(),
    }
    row.update(over)
    return row


def container_row(**over) -> dict:
    """Build a ``containers`` row dict matching ``ContainerResponse``."""
    row = {
        "id": uuid.uuid4(),
        "user_key": "khash",
        "name": "Glass Bowl",
        "normalized_name": "glass bowl",
        "tare_weight_g": 250.0,
        "has_photo": False,
        "created_at": _dt(),
        "updated_at": _dt(),
    }
    row.update(over)
    return row


def memory_row(**over) -> dict:
    """Build a ``food_memory`` row dict matching ``FoodMemoryEntry``."""
    row = {
        "id": uuid.uuid4(),
        "user_key": "khash",
        "name": "oatmeal",
        "normalized_name": "oatmeal",
        "usda_fdc_id": 123,
        "usda_description": "Oats",
        "custom_food_id": None,
        "basis": "per_100g",
        "serving_size": None,
        "serving_size_unit": None,
        "calories": 150,
        "protein_g": 5.0,
        "carbs_g": 27.0,
        "fat_g": 3.0,
        "aliases": ["porridge"],
        "created_at": _dt(),
        "updated_at": _dt(),
    }
    row.update(over)
    return row


def meal_row(**over) -> dict:
    """Build a ``meals`` row dict matching the parent half of ``MealResponse``."""
    row = {
        "id": uuid.uuid4(),
        "user_key": "khash",
        "name": "Breakfast",
        "normalized_name": "breakfast",
        "notes": None,
        "aliases": [],
        "created_at": _dt(),
        "updated_at": _dt(),
    }
    row.update(over)
    return row


def meal_item_row(meal_id: uuid.UUID, **over) -> dict:
    """Build a ``meal_items`` row dict matching ``MealItemResponse``."""
    row = {
        "id": uuid.uuid4(),
        "meal_id": meal_id,
        "position": 0,
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
        "created_at": _dt(),
    }
    row.update(over)
    return row


def target_row(**over) -> dict:
    """Build a ``daily_target_profile`` row dict for the targets repository."""
    row = {
        "calories_target": 2000,
        "protein_g_target": 150.0,
        "carbs_g_target": 200.0,
        "fat_g_target": 60.0,
    }
    row.update(over)
    return row


# ---- search / resolve ---------------------------------------------------------


@pytest.mark.asyncio
async def test_search_food_maps_usda_results() -> None:
    """``search_food`` adapts USDA rows into ``FoodCandidate`` entries."""
    usda = MagicMock()
    usda.search = AsyncMock(
        return_value=[
            {
                "fdc_id": 1,
                "description": "Oats",
                "serving_size": 40,
                "serving_size_unit": "g",
                "calories": 150,
                "protein_g": 5,
                "carbs_g": 27,
                "fat_g": 3,
            }
        ]
    )
    fns = await _fns(usda)
    result = await fns["search_food"](description="oats", limit=3)
    assert result.query == "oats"
    assert len(result.candidates) == 1
    assert result.candidates[0].fdc_id == 1
    assert result.candidates[0].basis == "per_serving"


@pytest.mark.asyncio
async def test_resolve_food_delegates_to_service() -> None:
    """``resolve_food`` returns the service's ``ResolvedFood`` verbatim."""
    fns = await _fns()
    resolved = ResolvedFood(type="none")
    with patched(resolve_food_by_name=AsyncMock(return_value=resolved)):
        out = await fns["resolve_food"](name="mystery")
    assert out.type == "none"


# ---- log_food -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_food_happy_path_with_targets() -> None:
    """``log_food`` returns the created entry, totals, and remaining vs target."""
    fns = await _fns()
    created = [entry_row()]
    day = [entry_row()]
    targets_cls, _ = repo(get_target_profile=target_row())
    with patched(
        create_entries_with_side_effects=AsyncMock(return_value=(created, day)),
        TargetsRepository=targets_cls,
    ):
        out = await fns["log_food"](
            display_name="Oatmeal",
            quantity_text="1 cup",
            calories=150,
            protein_g=5.0,
            carbs_g=27.0,
            fat_g=3.0,
            fdc_id=123,
            usda_description="Oats",
        )
    assert out.entry.calories == 150
    assert out.target is not None
    assert out.remaining_vs_target is not None


@pytest.mark.asyncio
async def test_log_food_without_targets() -> None:
    """``log_food`` returns null target/remaining when no profile is set."""
    fns = await _fns()
    targets_cls, _ = repo(get_target_profile=None)
    with patched(
        create_entries_with_side_effects=AsyncMock(return_value=([entry_row()], [entry_row()])),
        TargetsRepository=targets_cls,
    ):
        out = await fns["log_food"](
            display_name="Oatmeal",
            quantity_text="1 cup",
            calories=150,
            protein_g=5.0,
            carbs_g=27.0,
            fat_g=3.0,
            fdc_id=123,
            usda_description="Oats",
        )
    assert out.target is None
    assert out.remaining_vs_target is None


@pytest.mark.asyncio
async def test_log_food_rejects_both_sources() -> None:
    """Passing both ``fdc_id`` and ``custom_food_id`` raises ``ToolError``."""
    fns = await _fns()
    with pytest.raises(ToolError):
        await fns["log_food"](
            display_name="x",
            quantity_text="1",
            calories=1,
            protein_g=0.0,
            carbs_g=0.0,
            fat_g=0.0,
            fdc_id=1,
            usda_description="d",
            custom_food_id=str(uuid.uuid4()),
        )


@pytest.mark.asyncio
async def test_log_food_requires_usda_description() -> None:
    """``fdc_id`` without ``usda_description`` raises ``ToolError``."""
    fns = await _fns()
    with pytest.raises(ToolError):
        await fns["log_food"](
            display_name="x",
            quantity_text="1",
            calories=1,
            protein_g=0.0,
            carbs_g=0.0,
            fat_g=0.0,
            fdc_id=1,
        )


@pytest.mark.asyncio
async def test_log_food_rejects_bad_custom_food_uuid() -> None:
    """A non-UUID ``custom_food_id`` raises ``ToolError``."""
    fns = await _fns()
    with pytest.raises(ToolError):
        await fns["log_food"](
            display_name="x",
            quantity_text="1",
            calories=1,
            protein_g=0.0,
            carbs_g=0.0,
            fat_g=0.0,
            custom_food_id="not-a-uuid",
        )


@pytest.mark.asyncio
async def test_log_food_maps_cross_tenant_error() -> None:
    """A ``CrossTenantReferenceError`` from the service maps to ``ToolError``."""
    fns = await _fns()
    with patched(
        create_entries_with_side_effects=AsyncMock(
            side_effect=CrossTenantReferenceError("nope")
        )
    ):
        with pytest.raises(ToolError):
            await fns["log_food"](
                display_name="x",
                quantity_text="1",
                calories=1,
                protein_g=0.0,
                carbs_g=0.0,
                fat_g=0.0,
                custom_food_id=str(uuid.uuid4()),
            )


# ---- get_day ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_day_returns_summary() -> None:
    """``get_day`` adapts the service summary into a ``DaySummary``."""
    fns = await _fns()
    summary = SimpleNamespace(
        date=_dt().date(),
        target=None,
        consumed=MacroTotals(calories=150, protein_g=5.0, carbs_g=27.0, fat_g=3.0),
        remaining=None,
        entries=[FoodEntryResponse(**entry_row())],
    )
    with patched(build_daily_summary=AsyncMock(return_value=summary)):
        out = await fns["get_day"](date="2026-05-20")
    assert out.consumed.calories == 150
    assert len(out.entries) == 1


@pytest.mark.asyncio
async def test_get_day_falls_back_on_404() -> None:
    """A 404 from the summary service falls back to a target-less day view."""
    fns = await _fns()
    entries_cls, _ = repo(list_entries_by_daily_log_id=[entry_row()])
    with patched(
        build_daily_summary=AsyncMock(side_effect=HTTPException(status_code=404)),
        EntriesRepository=entries_cls,
    ):
        out = await fns["get_day"](date="2026-05-20")
    assert out.target is None
    assert len(out.entries) == 1


@pytest.mark.asyncio
async def test_get_day_rejects_bad_date() -> None:
    """An unparseable date raises ``ToolError``."""
    fns = await _fns()
    with pytest.raises(ToolError):
        await fns["get_day"](date="20-05-2026")


# ---- delete_entry / targets ---------------------------------------------------


@pytest.mark.asyncio
async def test_delete_entry_happy() -> None:
    """``delete_entry`` returns the repository's deletion flag."""
    fns = await _fns()
    entries_cls, _ = repo(delete_entry=True)
    with patched(EntriesRepository=entries_cls):
        out = await fns["delete_entry"](entry_id=str(uuid.uuid4()))
    assert out == {"deleted": True}


@pytest.mark.asyncio
async def test_delete_entry_rejects_bad_uuid() -> None:
    """A non-UUID ``entry_id`` raises ``ToolError``."""
    fns = await _fns()
    with pytest.raises(ToolError):
        await fns["delete_entry"](entry_id="nope")


@pytest.mark.asyncio
async def test_get_targets_returns_none_when_unset() -> None:
    """``get_targets`` returns ``None`` when no profile row exists."""
    fns = await _fns()
    targets_cls, _ = repo(get_target_profile=None)
    with patched(TargetsRepository=targets_cls):
        assert await fns["get_targets"]() is None


@pytest.mark.asyncio
async def test_get_targets_maps_row() -> None:
    """``get_targets`` adapts the profile row into ``MacroTargets``."""
    fns = await _fns()
    targets_cls, _ = repo(get_target_profile=target_row())
    with patched(TargetsRepository=targets_cls):
        out = await fns["get_targets"]()
    assert out.calories == 2000


@pytest.mark.asyncio
async def test_set_targets_upserts_and_echoes() -> None:
    """``set_targets`` upserts and echoes the provided targets."""
    fns = await _fns()
    targets_cls, inst = repo(upsert_targets=None)
    with patched(TargetsRepository=targets_cls):
        out = await fns["set_targets"](calories=2000, protein_g=150.0, carbs_g=200.0, fat_g=60.0)
    assert out.calories == 2000
    inst.upsert_targets.assert_awaited_once()


# ---- custom foods -------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_custom_food_happy() -> None:
    """``save_custom_food`` adapts the upserted row to ``CustomFoodResponse``."""
    fns = await _fns()
    with patched(upsert_custom_food_and_remember=AsyncMock(return_value=custom_food_row())):
        out = await fns["save_custom_food"](
            name="Protein Wrap",
            basis="per_serving",
            calories=300,
            protein_g=25.0,
            carbs_g=30.0,
            fat_g=10.0,
        )
    assert out.name == "Protein Wrap"


@pytest.mark.asyncio
async def test_update_custom_food_happy() -> None:
    """``update_custom_food`` forwards only provided fields and returns the row."""
    fns = await _fns()
    cf_cls, inst = repo(update_fields=custom_food_row(name="Renamed"))
    with patched(CustomFoodsRepository=cf_cls):
        out = await fns["update_custom_food"](custom_food_id=str(uuid.uuid4()), name="Renamed")
    assert out.name == "Renamed"
    # Only name (+ derived normalized_name) should be forwarded.
    forwarded = inst.update_fields.await_args.args[2]
    assert set(forwarded) == {"name", "normalized_name"}


@pytest.mark.asyncio
async def test_update_custom_food_not_found() -> None:
    """A ``None`` row from the repository raises ``ToolError``."""
    fns = await _fns()
    cf_cls, _ = repo(update_fields=None)
    with patched(CustomFoodsRepository=cf_cls):
        with pytest.raises(ToolError):
            await fns["update_custom_food"](custom_food_id=str(uuid.uuid4()), name="x")


@pytest.mark.asyncio
async def test_update_custom_food_duplicate_name() -> None:
    """An ``IntegrityError`` maps to a duplicate-name ``ToolError``."""
    fns = await _fns()
    cf_cls, _ = repo(update_fields=AsyncMock(side_effect=IntegrityError("x", {}, Exception())))
    with patched(CustomFoodsRepository=cf_cls):
        with pytest.raises(ToolError):
            await fns["update_custom_food"](custom_food_id=str(uuid.uuid4()), name="dupe")


@pytest.mark.asyncio
async def test_update_custom_food_bad_uuid() -> None:
    """A non-UUID id raises ``ToolError`` before touching the repository."""
    fns = await _fns()
    with pytest.raises(ToolError):
        await fns["update_custom_food"](custom_food_id="nope", name="x")


@pytest.mark.asyncio
async def test_delete_custom_food_referenced_raises() -> None:
    """An ``IntegrityError`` maps to a referenced-food ``ToolError``."""
    fns = await _fns()
    cf_cls, _ = repo(delete=AsyncMock(side_effect=IntegrityError("x", {}, Exception())))
    with patched(CustomFoodsRepository=cf_cls):
        with pytest.raises(ToolError):
            await fns["delete_custom_food"](custom_food_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_delete_custom_food_happy() -> None:
    """``delete_custom_food`` returns the repository's deletion flag."""
    fns = await _fns()
    cf_cls, _ = repo(delete=True)
    with patched(CustomFoodsRepository=cf_cls):
        out = await fns["delete_custom_food"](custom_food_id=str(uuid.uuid4()))
    assert out == {"deleted": True}


@pytest.mark.asyncio
async def test_list_custom_foods() -> None:
    """``list_custom_foods`` adapts every repository row."""
    fns = await _fns()
    cf_cls, _ = repo(list_for_user=[custom_food_row(), custom_food_row(name="Second")])
    with patched(CustomFoodsRepository=cf_cls):
        out = await fns["list_custom_foods"]()
    assert len(out) == 2


# ---- containers ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_containers() -> None:
    """``list_containers`` adapts every container row."""
    fns = await _fns()
    cont_cls, _ = repo(list_for_user=[container_row()])
    with patched(ContainersRepository=cont_cls):
        out = await fns["list_containers"]()
    assert out[0].tare_weight_g == 250.0


@pytest.mark.asyncio
async def test_save_container_happy() -> None:
    """``save_container`` returns the created container."""
    fns = await _fns()
    cont_cls, _ = repo(create=container_row())
    with patched(ContainersRepository=cont_cls):
        out = await fns["save_container"](name="Glass Bowl", tare_weight_g=250.0)
    assert out.name == "Glass Bowl"


@pytest.mark.asyncio
async def test_save_container_duplicate() -> None:
    """A duplicate container name maps to ``ToolError``."""
    fns = await _fns()
    cont_cls, _ = repo(create=AsyncMock(side_effect=IntegrityError("x", {}, Exception())))
    with patched(ContainersRepository=cont_cls):
        with pytest.raises(ToolError):
            await fns["save_container"](name="dupe", tare_weight_g=10.0)


@pytest.mark.asyncio
async def test_update_container_not_found() -> None:
    """``update_container`` raises ``ToolError`` when no row is updated."""
    fns = await _fns()
    cont_cls, _ = repo(update_fields=None)
    with patched(ContainersRepository=cont_cls):
        with pytest.raises(ToolError):
            await fns["update_container"](container_id=str(uuid.uuid4()), name="x")


@pytest.mark.asyncio
async def test_update_container_happy() -> None:
    """``update_container`` returns the updated row."""
    fns = await _fns()
    cont_cls, _ = repo(update_fields=container_row(name="Renamed"))
    with patched(ContainersRepository=cont_cls):
        out = await fns["update_container"](
            container_id=str(uuid.uuid4()), name="Renamed", tare_weight_g=99.0
        )
    assert out.name == "Renamed"


@pytest.mark.asyncio
async def test_update_container_bad_uuid() -> None:
    """A non-UUID container id raises ``ToolError``."""
    fns = await _fns()
    with pytest.raises(ToolError):
        await fns["update_container"](container_id="nope")


@pytest.mark.asyncio
async def test_delete_container_happy() -> None:
    """``delete_container`` returns the repository's deletion flag."""
    fns = await _fns()
    cont_cls, _ = repo(delete=True)
    with patched(ContainersRepository=cont_cls):
        out = await fns["delete_container"](container_id=str(uuid.uuid4()))
    assert out == {"deleted": True}


@pytest.mark.asyncio
async def test_delete_container_bad_uuid() -> None:
    """A non-UUID container id raises ``ToolError``."""
    fns = await _fns()
    with pytest.raises(ToolError):
        await fns["delete_container"](container_id="nope")


# ---- food memory --------------------------------------------------------------


@pytest.mark.asyncio
async def test_remember_food_with_aliases() -> None:
    """``remember_food`` validates aliases then upserts via the repository."""
    fns = await _fns()
    fm_cls, inst = repo(upsert_usda=memory_row())
    with patched(
        FoodMemoryRepository=fm_cls,
        normalize_alias_list=MagicMock(return_value=["porridge"]),
        assert_food_alias_available=AsyncMock(return_value=None),
    ):
        out = await fns["remember_food"](
            name="oatmeal",
            fdc_id=123,
            usda_description="Oats",
            basis="per_100g",
            calories=150,
            protein_g=5.0,
            carbs_g=27.0,
            fat_g=3.0,
            aliases=["porridge"],
        )
    assert out.name == "oatmeal"
    inst.upsert_usda.assert_awaited_once()


@pytest.mark.asyncio
async def test_forget_food() -> None:
    """``forget_food`` returns the repository's deletion flag."""
    fns = await _fns()
    fm_cls, _ = repo(delete_by_name=True)
    with patched(FoodMemoryRepository=fm_cls):
        out = await fns["forget_food"](name="oatmeal")
    assert out == {"deleted": True}


@pytest.mark.asyncio
async def test_list_remembered_foods() -> None:
    """``list_remembered_foods`` adapts every memory row."""
    fns = await _fns()
    fm_cls, _ = repo(list_for_user=[memory_row()])
    with patched(FoodMemoryRepository=fm_cls):
        out = await fns["list_remembered_foods"]()
    assert out[0].aliases == ["porridge"]


@pytest.mark.asyncio
async def test_add_food_alias_happy() -> None:
    """``add_food_alias`` appends a distinct alias and returns the entry."""
    fns = await _fns()
    fm_cls, inst = repo(add_alias=memory_row(aliases=["porridge", "gruel"]))
    with patched(
        FoodMemoryRepository=fm_cls,
        assert_food_alias_available=AsyncMock(return_value=None),
    ):
        out = await fns["add_food_alias"](name="oatmeal", alias="gruel")
    assert "gruel" in out.aliases
    inst.add_alias.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_food_alias_equal_to_name_returns_entry() -> None:
    """When alias normalizes to the canonical name, the existing entry is returned."""
    fns = await _fns()
    fm_cls, inst = repo(get_by_name=memory_row())
    with patched(FoodMemoryRepository=fm_cls):
        out = await fns["add_food_alias"](name="oatmeal", alias="oatmeal")
    assert out.name == "oatmeal"
    inst.get_by_name.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_food_alias_empty_alias() -> None:
    """An alias that is empty after normalization raises ``ToolError``."""
    fns = await _fns()
    with pytest.raises(ToolError):
        await fns["add_food_alias"](name="oatmeal", alias="   ")


@pytest.mark.asyncio
async def test_add_food_alias_conflict() -> None:
    """A conflicting alias (service ``ValueError``) maps to ``ToolError``."""
    fns = await _fns()
    fm_cls, _ = repo(add_alias=memory_row())
    with patched(
        FoodMemoryRepository=fm_cls,
        assert_food_alias_available=AsyncMock(side_effect=ValueError("taken")),
    ):
        with pytest.raises(ToolError):
            await fns["add_food_alias"](name="oatmeal", alias="gruel")


@pytest.mark.asyncio
async def test_remove_food_alias_not_found() -> None:
    """A missing memory entry raises ``ToolError``."""
    fns = await _fns()
    fm_cls, _ = repo(remove_alias=None)
    with patched(FoodMemoryRepository=fm_cls):
        with pytest.raises(ToolError):
            await fns["remove_food_alias"](name="ghost", alias="x")


@pytest.mark.asyncio
async def test_remove_food_alias_happy() -> None:
    """``remove_food_alias`` returns the updated entry."""
    fns = await _fns()
    fm_cls, _ = repo(remove_alias=memory_row(aliases=[]))
    with patched(FoodMemoryRepository=fm_cls):
        out = await fns["remove_food_alias"](name="oatmeal", alias="porridge")
    assert out.aliases == []


# ---- meals --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_meal_happy() -> None:
    """``create_meal`` adapts the created meal + items into ``MealResponse``."""
    from pulse_server.models.meals import MealItemCreate

    fns = await _fns()
    m = meal_row()
    items = [meal_item_row(m["id"])]
    with patched(create_meal_with_items=AsyncMock(return_value=(m, items))):
        out = await fns["create_meal"](
            name="Breakfast",
            items=[
                MealItemCreate(
                    display_name="Oatmeal",
                    quantity_text="1 cup",
                    usda_fdc_id=123,
                    usda_description="Oats",
                    calories=150,
                    protein_g=5.0,
                    carbs_g=27.0,
                    fat_g=3.0,
                )
            ],
        )
    assert out.name == "Breakfast"
    assert len(out.items) == 1


@pytest.mark.asyncio
async def test_create_meal_duplicate_name() -> None:
    """A duplicate meal name maps to ``ToolError``."""
    fns = await _fns()
    with patched(
        create_meal_with_items=AsyncMock(side_effect=IntegrityError("x", {}, Exception()))
    ):
        with pytest.raises(ToolError):
            await fns["create_meal"](name="dupe", items=[])


@pytest.mark.asyncio
async def test_create_meal_http_error_maps() -> None:
    """An ``HTTPException`` from the service maps to ``ToolError``."""
    fns = await _fns()
    with patched(
        create_meal_with_items=AsyncMock(side_effect=HTTPException(status_code=400, detail="bad"))
    ):
        with pytest.raises(ToolError):
            await fns["create_meal"](name="x", items=[])


@pytest.mark.asyncio
async def test_list_meals() -> None:
    """``list_meals`` adapts repository rows into ``MealSummary`` entries."""
    fns = await _fns()
    rows = [
        {
            "id": uuid.uuid4(),
            "name": "Breakfast",
            "normalized_name": "breakfast",
            "notes": None,
            "aliases": ["am meal"],
            "item_count": 2,
            "total_calories": 400,
            "total_protein_g": 20.0,
            "total_carbs_g": 50.0,
            "total_fat_g": 12.0,
        }
    ]
    meals_cls, _ = repo(list_meals=rows)
    with patched(MealsRepository=meals_cls):
        out = await fns["list_meals"]()
    assert out[0].item_count == 2
    assert out[0].aliases == ["am meal"]


@pytest.mark.asyncio
async def test_get_meal_by_id() -> None:
    """``get_meal`` fetches by id and returns the full meal."""
    fns = await _fns()
    m = meal_row()
    meals_cls, _ = repo(get_meal=m, list_items=[meal_item_row(m["id"])])
    with patched(MealsRepository=meals_cls):
        out = await fns["get_meal"](meal_id=str(m["id"]))
    assert out.id == m["id"]


@pytest.mark.asyncio
async def test_get_meal_by_name() -> None:
    """``get_meal`` fetches by name when no id is given."""
    fns = await _fns()
    m = meal_row()
    meals_cls, _ = repo(get_meal_by_name=m, list_items=[])
    with patched(MealsRepository=meals_cls):
        out = await fns["get_meal"](name="Breakfast")
    assert out.name == "Breakfast"


@pytest.mark.asyncio
async def test_get_meal_requires_exactly_one_selector() -> None:
    """Providing neither id nor name raises ``ToolError``."""
    fns = await _fns()
    with pytest.raises(ToolError):
        await fns["get_meal"]()


@pytest.mark.asyncio
async def test_get_meal_not_found() -> None:
    """A missing meal raises ``ToolError``."""
    fns = await _fns()
    meals_cls, _ = repo(get_meal=None)
    with patched(MealsRepository=meals_cls):
        with pytest.raises(ToolError):
            await fns["get_meal"](meal_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_update_meal_happy() -> None:
    """``update_meal`` returns the updated meal with its items."""
    fns = await _fns()
    m = meal_row(name="Renamed")
    meals_cls, _ = repo(update_meal=m, list_items=[])
    with patched(MealsRepository=meals_cls):
        out = await fns["update_meal"](meal_id=str(m["id"]), name="Renamed")
    assert out.name == "Renamed"


@pytest.mark.asyncio
async def test_update_meal_not_found() -> None:
    """A missing meal on update raises ``ToolError``."""
    fns = await _fns()
    meals_cls, _ = repo(update_meal=None)
    with patched(MealsRepository=meals_cls):
        with pytest.raises(ToolError):
            await fns["update_meal"](meal_id=str(uuid.uuid4()), name="x")


@pytest.mark.asyncio
async def test_update_meal_duplicate_name() -> None:
    """An ``IntegrityError`` on update maps to a duplicate-name ``ToolError``."""
    fns = await _fns()
    meals_cls, _ = repo(update_meal=AsyncMock(side_effect=IntegrityError("x", {}, Exception())))
    with patched(MealsRepository=meals_cls):
        with pytest.raises(ToolError):
            await fns["update_meal"](meal_id=str(uuid.uuid4()), name="dupe")


@pytest.mark.asyncio
async def test_update_meal_item_all_fields() -> None:
    """``update_meal_item`` forwards every mutable field that is provided."""
    fns = await _fns()
    m = meal_row()
    meals_cls, inst = repo(get_meal=m, update_meal_item=meal_item_row(m["id"]))
    with patched(MealsRepository=meals_cls):
        await fns["update_meal_item"](
            meal_id=str(m["id"]),
            meal_item_id=str(uuid.uuid4()),
            display_name="New",
            quantity_text="2 cups",
            normalized_quantity_value=2.0,
            normalized_quantity_unit="cup",
            calories=300,
            protein_g=10.0,
            carbs_g=54.0,
            fat_g=6.0,
        )
    forwarded = inst.update_meal_item.await_args.args[2]
    assert set(forwarded) == {
        "display_name", "quantity_text", "normalized_quantity_value",
        "normalized_quantity_unit", "calories", "protein_g", "carbs_g", "fat_g",
    }


@pytest.mark.asyncio
async def test_delete_meal_happy() -> None:
    """``delete_meal`` returns the repository's deletion flag."""
    fns = await _fns()
    meals_cls, _ = repo(delete_meal=True)
    with patched(MealsRepository=meals_cls):
        out = await fns["delete_meal"](meal_id=str(uuid.uuid4()))
    assert out == {"deleted": True}


@pytest.mark.asyncio
async def test_add_meal_item_with_usda() -> None:
    """``add_meal_item`` appends a USDA-backed item to an existing meal."""
    from pulse_server.models.meals import MealItemCreate

    fns = await _fns()
    m = meal_row()
    meals_cls, _ = repo(
        get_meal=m,
        next_position=1,
        add_meal_item=meal_item_row(m["id"], position=1),
    )
    with patched(MealsRepository=meals_cls):
        out = await fns["add_meal_item"](
            meal_id=str(m["id"]),
            item=MealItemCreate(
                display_name="Banana",
                quantity_text="1",
                usda_fdc_id=999,
                usda_description="Banana",
                calories=100,
                protein_g=1.0,
                carbs_g=27.0,
                fat_g=0.3,
            ),
        )
    assert out.position == 1


@pytest.mark.asyncio
async def test_add_meal_item_meal_not_found() -> None:
    """Appending to a missing meal raises ``ToolError``."""
    from pulse_server.models.meals import MealItemCreate

    fns = await _fns()
    meals_cls, _ = repo(get_meal=None)
    with patched(MealsRepository=meals_cls):
        with pytest.raises(ToolError):
            await fns["add_meal_item"](
                meal_id=str(uuid.uuid4()),
                item=MealItemCreate(
                    display_name="x",
                    quantity_text="1",
                    usda_fdc_id=1,
                    usda_description="d",
                    calories=1,
                    protein_g=0.0,
                    carbs_g=0.0,
                    fat_g=0.0,
                ),
            )


@pytest.mark.asyncio
async def test_add_meal_item_rejects_both_sources() -> None:
    """An item with both USDA and custom sources raises ``ToolError``."""
    from pulse_server.models.meals import MealItemCreate

    fns = await _fns()
    item = MealItemCreate(
        display_name="x",
        quantity_text="1",
        usda_fdc_id=1,
        usda_description="d",
        custom_food_id=uuid.uuid4(),
        calories=1,
        protein_g=0.0,
        carbs_g=0.0,
        fat_g=0.0,
    )
    with pytest.raises(ToolError):
        await fns["add_meal_item"](meal_id=str(uuid.uuid4()), item=item)


@pytest.mark.asyncio
async def test_add_meal_item_custom_food_cross_tenant() -> None:
    """A cross-tenant custom food reference maps to ``ToolError``."""
    from pulse_server.models.meals import MealItemCreate

    fns = await _fns()
    m = meal_row()
    meals_cls, _ = repo(get_meal=m)
    with patched(
        MealsRepository=meals_cls,
        assert_custom_foods_owned=AsyncMock(side_effect=CrossTenantReferenceError("nope")),
    ):
        with pytest.raises(ToolError):
            await fns["add_meal_item"](
                meal_id=str(m["id"]),
                item=MealItemCreate(
                    display_name="x",
                    quantity_text="1",
                    custom_food_id=uuid.uuid4(),
                    calories=1,
                    protein_g=0.0,
                    carbs_g=0.0,
                    fat_g=0.0,
                ),
            )


@pytest.mark.asyncio
async def test_update_meal_item_happy() -> None:
    """``update_meal_item`` updates mutable fields on an existing item."""
    fns = await _fns()
    m = meal_row()
    meals_cls, _ = repo(get_meal=m, update_meal_item=meal_item_row(m["id"], display_name="New"))
    with patched(MealsRepository=meals_cls):
        out = await fns["update_meal_item"](
            meal_id=str(m["id"]),
            meal_item_id=str(uuid.uuid4()),
            display_name="New",
            calories=200,
        )
    assert out.display_name == "New"


@pytest.mark.asyncio
async def test_update_meal_item_meal_not_found() -> None:
    """Updating an item on a missing meal raises ``ToolError``."""
    fns = await _fns()
    meals_cls, _ = repo(get_meal=None)
    with patched(MealsRepository=meals_cls):
        with pytest.raises(ToolError):
            await fns["update_meal_item"](
                meal_id=str(uuid.uuid4()),
                meal_item_id=str(uuid.uuid4()),
                display_name="x",
            )


@pytest.mark.asyncio
async def test_update_meal_item_item_not_found() -> None:
    """A missing item (repository returns ``None``) raises ``ToolError``."""
    fns = await _fns()
    m = meal_row()
    meals_cls, _ = repo(get_meal=m, update_meal_item=None)
    with patched(MealsRepository=meals_cls):
        with pytest.raises(ToolError):
            await fns["update_meal_item"](
                meal_id=str(m["id"]),
                meal_item_id=str(uuid.uuid4()),
                display_name="x",
            )


@pytest.mark.asyncio
async def test_update_meal_item_bad_uuid() -> None:
    """Non-UUID identifiers raise ``ToolError``."""
    fns = await _fns()
    with pytest.raises(ToolError):
        await fns["update_meal_item"](meal_id="nope", meal_item_id="nope")


@pytest.mark.asyncio
async def test_delete_meal_item_happy() -> None:
    """``delete_meal_item`` removes an item from an existing meal."""
    fns = await _fns()
    m = meal_row()
    meals_cls, _ = repo(get_meal=m, delete_meal_item=True)
    with patched(MealsRepository=meals_cls):
        out = await fns["delete_meal_item"](meal_id=str(m["id"]), meal_item_id=str(uuid.uuid4()))
    assert out == {"deleted": True}


@pytest.mark.asyncio
async def test_delete_meal_item_meal_not_found() -> None:
    """Deleting an item on a missing meal raises ``ToolError``."""
    fns = await _fns()
    meals_cls, _ = repo(get_meal=None)
    with patched(MealsRepository=meals_cls):
        with pytest.raises(ToolError):
            await fns["delete_meal_item"](meal_id=str(uuid.uuid4()), meal_item_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_add_meal_alias_happy() -> None:
    """``add_meal_alias`` appends a distinct alias and returns the meal."""
    fns = await _fns()
    m = meal_row()
    updated = meal_row(id=m["id"], aliases=["am meal"])
    meals_cls, inst = repo(get_meal=m, add_alias=updated, list_items=[])
    with patched(
        MealsRepository=meals_cls,
        assert_meal_alias_available=AsyncMock(return_value=None),
    ):
        out = await fns["add_meal_alias"](meal_id=str(m["id"]), alias="am meal")
    assert out.aliases == ["am meal"]
    inst.add_alias.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_meal_alias_equal_to_name() -> None:
    """An alias equal to the meal's normalized name short-circuits to the meal."""
    fns = await _fns()
    m = meal_row(normalized_name="breakfast")
    meals_cls, inst = repo(get_meal=m, list_items=[])
    with patched(MealsRepository=meals_cls):
        out = await fns["add_meal_alias"](meal_id=str(m["id"]), alias="Breakfast")
    assert out.name == "Breakfast"
    inst.add_alias.assert_not_called()


@pytest.mark.asyncio
async def test_add_meal_alias_meal_not_found() -> None:
    """Aliasing a missing meal raises ``ToolError``."""
    fns = await _fns()
    meals_cls, _ = repo(get_meal=None)
    with patched(MealsRepository=meals_cls):
        with pytest.raises(ToolError):
            await fns["add_meal_alias"](meal_id=str(uuid.uuid4()), alias="x")


@pytest.mark.asyncio
async def test_add_meal_alias_conflict() -> None:
    """A conflicting alias maps the service ``ValueError`` to ``ToolError``."""
    fns = await _fns()
    m = meal_row()
    meals_cls, _ = repo(get_meal=m)
    with patched(
        MealsRepository=meals_cls,
        assert_meal_alias_available=AsyncMock(side_effect=ValueError("taken")),
    ):
        with pytest.raises(ToolError):
            await fns["add_meal_alias"](meal_id=str(m["id"]), alias="other")


@pytest.mark.asyncio
async def test_remove_meal_alias_happy() -> None:
    """``remove_meal_alias`` returns the updated meal."""
    fns = await _fns()
    m = meal_row()
    meals_cls, _ = repo(remove_alias=meal_row(id=m["id"], aliases=[]), list_items=[])
    with patched(MealsRepository=meals_cls):
        out = await fns["remove_meal_alias"](meal_id=str(m["id"]), alias="am meal")
    assert out.aliases == []


@pytest.mark.asyncio
async def test_remove_meal_alias_not_found() -> None:
    """Removing an alias from a missing meal raises ``ToolError``."""
    fns = await _fns()
    meals_cls, _ = repo(remove_alias=None)
    with patched(MealsRepository=meals_cls):
        with pytest.raises(ToolError):
            await fns["remove_meal_alias"](meal_id=str(uuid.uuid4()), alias="x")


@pytest.mark.asyncio
async def test_log_meal_happy() -> None:
    """``log_meal`` returns created entries, totals, and remaining vs target."""
    fns = await _fns()
    created = [entry_row(), entry_row()]
    day = [entry_row(), entry_row()]
    targets_cls, _ = repo(get_target_profile=target_row())
    with patched(
        log_meal_service=AsyncMock(return_value=(created, day)),
        TargetsRepository=targets_cls,
    ):
        out = await fns["log_meal"](meal_id=str(uuid.uuid4()))
    assert len(out.entries) == 2
    assert out.target is not None


@pytest.mark.asyncio
async def test_log_meal_http_error_maps() -> None:
    """An ``HTTPException`` from the service maps to ``ToolError``."""
    fns = await _fns()
    with patched(
        log_meal_service=AsyncMock(side_effect=HTTPException(status_code=404, detail="gone"))
    ):
        with pytest.raises(ToolError):
            await fns["log_meal"](meal_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_log_meal_bad_uuid() -> None:
    """A non-UUID meal id raises ``ToolError``."""
    fns = await _fns()
    with pytest.raises(ToolError):
        await fns["log_meal"](meal_id="nope")


# ---- additional bad-uuid / edge branches --------------------------------------


@pytest.mark.asyncio
async def test_get_day_defaults_to_today() -> None:
    """``get_day`` with no date defaults to today's summary."""
    fns = await _fns()
    summary = SimpleNamespace(
        date=_dt().date(),
        target=None,
        consumed=MacroTotals(calories=0, protein_g=0.0, carbs_g=0.0, fat_g=0.0),
        remaining=None,
        entries=[],
    )
    with patched(build_daily_summary=AsyncMock(return_value=summary)):
        out = await fns["get_day"]()
    assert out.consumed.calories == 0


@pytest.mark.asyncio
async def test_get_day_reraises_non_404() -> None:
    """A non-404 ``HTTPException`` from the summary service propagates."""
    fns = await _fns()
    with patched(build_daily_summary=AsyncMock(side_effect=HTTPException(status_code=500))):
        with pytest.raises(HTTPException):
            await fns["get_day"](date="2026-05-20")


@pytest.mark.asyncio
async def test_delete_custom_food_bad_uuid() -> None:
    """A non-UUID custom_food_id raises ``ToolError``."""
    fns = await _fns()
    with pytest.raises(ToolError):
        await fns["delete_custom_food"](custom_food_id="nope")


@pytest.mark.asyncio
async def test_update_container_duplicate_name() -> None:
    """An ``IntegrityError`` on update maps to a duplicate-name ``ToolError``."""
    fns = await _fns()
    cont_cls, _ = repo(update_fields=AsyncMock(side_effect=IntegrityError("x", {}, Exception())))
    with patched(ContainersRepository=cont_cls):
        with pytest.raises(ToolError):
            await fns["update_container"](container_id=str(uuid.uuid4()), name="dupe")


@pytest.mark.asyncio
async def test_remember_food_alias_conflict() -> None:
    """A conflicting alias during ``remember_food`` maps to ``ToolError``."""
    fns = await _fns()
    fm_cls, _ = repo(upsert_usda=memory_row())
    with patched(
        FoodMemoryRepository=fm_cls,
        normalize_alias_list=MagicMock(return_value=["porridge"]),
        assert_food_alias_available=AsyncMock(side_effect=ValueError("taken")),
    ):
        with pytest.raises(ToolError):
            await fns["remember_food"](
                name="oatmeal",
                fdc_id=123,
                usda_description="Oats",
                basis="per_100g",
                calories=150,
                protein_g=5.0,
                carbs_g=27.0,
                fat_g=3.0,
                aliases=["porridge"],
            )


@pytest.mark.asyncio
async def test_add_food_alias_equal_to_name_not_found() -> None:
    """alias==name with no existing entry raises ``ToolError``."""
    fns = await _fns()
    fm_cls, _ = repo(get_by_name=None)
    with patched(FoodMemoryRepository=fm_cls):
        with pytest.raises(ToolError):
            await fns["add_food_alias"](name="ghost", alias="ghost")


@pytest.mark.asyncio
async def test_add_food_alias_repo_returns_none() -> None:
    """A distinct alias whose ``add_alias`` returns ``None`` raises ``ToolError``."""
    fns = await _fns()
    fm_cls, _ = repo(add_alias=None)
    with patched(
        FoodMemoryRepository=fm_cls,
        assert_food_alias_available=AsyncMock(return_value=None),
    ):
        with pytest.raises(ToolError):
            await fns["add_food_alias"](name="oatmeal", alias="gruel")


@pytest.mark.asyncio
async def test_meal_tools_reject_bad_uuids() -> None:
    """Every meal tool that parses a UUID rejects a malformed id with ``ToolError``."""
    fns = await _fns()
    # get_meal parses the id inside the session context, so patch the session
    # for the whole batch; the others reject the id before touching the DB.
    with patched():
        for call in (
            lambda: fns["get_meal"](meal_id="nope"),
            lambda: fns["update_meal"](meal_id="nope", name="x"),
            lambda: fns["delete_meal"](meal_id="nope"),
            lambda: fns["delete_meal_item"](meal_id="nope", meal_item_id="nope"),
            lambda: fns["add_meal_alias"](meal_id="nope", alias="x"),
            lambda: fns["remove_meal_alias"](meal_id="nope", alias="x"),
        ):
            with pytest.raises(ToolError):
                await call()


@pytest.mark.asyncio
async def test_add_meal_item_bad_uuid_and_missing_desc() -> None:
    """``add_meal_item`` rejects a bad meal id and a USDA item missing its description."""
    from pulse_server.models.meals import MealItemCreate

    fns = await _fns()
    good = MealItemCreate(
        display_name="x", quantity_text="1", usda_fdc_id=1, usda_description="d",
        calories=1, protein_g=0.0, carbs_g=0.0, fat_g=0.0,
    )
    with pytest.raises(ToolError):
        await fns["add_meal_item"](meal_id="nope", item=good)

    no_desc = MealItemCreate(
        display_name="x", quantity_text="1", usda_fdc_id=1,
        calories=1, protein_g=0.0, carbs_g=0.0, fat_g=0.0,
    )
    with pytest.raises(ToolError):
        await fns["add_meal_item"](meal_id=str(uuid.uuid4()), item=no_desc)


@pytest.mark.asyncio
async def test_add_meal_alias_empty_alias() -> None:
    """An alias empty after normalization raises ``ToolError``."""
    fns = await _fns()
    m = meal_row()
    meals_cls, _ = repo(get_meal=m)
    with patched(MealsRepository=meals_cls):
        with pytest.raises(ToolError):
            await fns["add_meal_alias"](meal_id=str(m["id"]), alias="   ")


@pytest.mark.asyncio
async def test_add_meal_alias_update_returns_none() -> None:
    """``add_meal_alias`` raises ``ToolError`` when the alias update finds no row."""
    fns = await _fns()
    m = meal_row()
    meals_cls, _ = repo(get_meal=m, add_alias=None)
    with patched(
        MealsRepository=meals_cls,
        assert_meal_alias_available=AsyncMock(return_value=None),
    ):
        with pytest.raises(ToolError):
            await fns["add_meal_alias"](meal_id=str(m["id"]), alias="other")
