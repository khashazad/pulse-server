"""Unit tests for the repository query layer with a mocked session.

Each repository method builds a SQLAlchemy statement and processes the
result of ``session.execute``. These tests stub ``session.execute`` so the
statement construction and result-adaptation code run without a database,
asserting the documented return contract (row dicts, booleans, counts,
``None`` misses). The compiled SQL itself is exercised against PostgreSQL by
the integration suite; here we cover the Python paths.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from pulse_server.repositories.auth_exchange_codes import AuthExchangeCodesRepository
from pulse_server.repositories.containers import ContainersRepository
from pulse_server.repositories.custom_foods import CustomFoodsRepository
from pulse_server.repositories.entries import EntriesRepository
from pulse_server.repositories.food_memory import FoodMemoryRepository
from pulse_server.repositories.logs import LogsRepository
from pulse_server.repositories.meals import MealsRepository
from pulse_server.repositories.progress_photo import ProgressPhotoRepository
from pulse_server.repositories.progress_photo_tag import ProgressPhotoTagRepository
from pulse_server.repositories.sessions import SessionsRepository
from pulse_server.repositories.targets import TargetsRepository
from pulse_server.repositories.weight import WeightRepository

pytestmark = pytest.mark.asyncio


def _now() -> datetime:
    """Return a fixed aware UTC timestamp for deterministic calls."""
    return datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)


class _Mappings(list):
    """List subclass mimicking a SQLAlchemy ``MappingResult``.

    Supports ``.one()`` / ``.first()`` / ``.all()`` and direct iteration so a
    single fixture serves every result-processing style in the repositories.
    """

    def one(self):
        """Return the first row (callers guarantee exactly one)."""
        return self[0]

    def first(self):
        """Return the first row or ``None`` when empty."""
        return self[0] if self else None

    def all(self):
        """Return all rows as a plain list."""
        return list(self)


def _session(
    *,
    rows: list | None = None,
    scalar_one=None,
    scalar_one_or_none=None,
    rowcount: int = 0,
    first=None,
):
    """Build a fake async session whose ``execute`` returns a stub result.

    **Inputs:**
    - rows (list | None): Rows exposed via ``result.mappings()``.
    - scalar_one: Value returned by ``result.scalar_one()``.
    - scalar_one_or_none: Value returned by ``result.scalar_one_or_none()``.
    - rowcount (int): Value of ``result.rowcount``.
    - first: Value returned by ``result.first()`` (row-tuple style).

    **Outputs:**
    - MagicMock: A session whose ``execute`` is an ``AsyncMock``.
    """
    result = MagicMock()
    result.mappings.return_value = _Mappings(rows or [])
    result.scalar_one.return_value = scalar_one
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.rowcount = rowcount
    result.first.return_value = first
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _row() -> dict:
    """Return a minimal row dict; repositories wrap rows in ``dict()`` unmodified."""
    return {"id": uuid.uuid4(), "name": "x"}


# ---- meals --------------------------------------------------------------------


async def test_meals_create_returns_row() -> None:
    """``create_meal`` returns the inserted row as a dict."""
    repo = MealsRepository(_session(rows=[_row()]))
    out = await repo.create_meal("khash", "Breakfast", "breakfast", None, _now(), aliases=["am"])
    assert "id" in out


async def test_meals_add_item_returns_row() -> None:
    """``add_meal_item`` returns the inserted item row."""
    repo = MealsRepository(_session(rows=[_row()]))
    out = await repo.add_meal_item(
        uuid.uuid4(), 0, "Oats", "1 cup", 1.0, "cup", 123, "Oats", None, 150, 5.0, 27.0, 3.0, _now()
    )
    assert "id" in out


async def test_meals_next_position() -> None:
    """``next_position`` returns the scalar position."""
    repo = MealsRepository(_session(scalar_one=5))
    assert await repo.next_position(uuid.uuid4()) == 5


async def test_meals_get_meal_found_and_missing() -> None:
    """``get_meal`` returns the row when present and ``None`` when absent."""
    assert await MealsRepository(_session(rows=[_row()])).get_meal(uuid.uuid4(), "k") is not None
    assert await MealsRepository(_session(rows=[])).get_meal(uuid.uuid4(), "k") is None


async def test_meals_get_by_name() -> None:
    """``get_meal_by_name`` matches canonical name or alias."""
    assert await MealsRepository(_session(rows=[_row()])).get_meal_by_name("k", "breakfast")


async def test_meals_list_and_items() -> None:
    """``list_meals`` and ``list_items`` return lists of row dicts."""
    assert len(await MealsRepository(_session(rows=[_row(), _row()])).list_meals("k")) == 2
    assert len(await MealsRepository(_session(rows=[_row()])).list_items(uuid.uuid4())) == 1


async def test_meals_update_with_and_without_fields() -> None:
    """``update_meal`` updates when fields given and re-fetches when empty."""
    assert await MealsRepository(_session(rows=[_row()])).update_meal(
        uuid.uuid4(), "k", {"name": "n"}, _now()
    )
    # Empty fields path delegates to get_meal (still one execute → one row).
    assert await MealsRepository(_session(rows=[_row()])).update_meal(uuid.uuid4(), "k", {}, _now())


async def test_meals_update_item_with_and_without_fields() -> None:
    """``update_meal_item`` covers both the update and re-fetch branches."""
    assert await MealsRepository(_session(rows=[_row()])).update_meal_item(
        uuid.uuid4(), uuid.uuid4(), {"calories": 1}
    )
    assert await MealsRepository(_session(rows=[_row()])).update_meal_item(
        uuid.uuid4(), uuid.uuid4(), {}
    )


async def test_meals_delete_paths() -> None:
    """``delete_meal`` / ``delete_meal_item`` map presence of a returned id to bool."""
    assert await MealsRepository(_session(scalar_one_or_none=uuid.uuid4())).delete_meal(
        uuid.uuid4(), "k"
    )
    assert not await MealsRepository(_session(scalar_one_or_none=None)).delete_meal(uuid.uuid4(), "k")
    assert await MealsRepository(_session(scalar_one_or_none=uuid.uuid4())).delete_meal_item(
        uuid.uuid4(), uuid.uuid4()
    )


async def test_meals_alias_mutation() -> None:
    """``add_alias`` / ``remove_alias`` return the updated row or ``None``."""
    assert await MealsRepository(_session(rows=[_row()])).add_alias(uuid.uuid4(), "k", "am", _now())
    assert await MealsRepository(_session(rows=[])).remove_alias(uuid.uuid4(), "k", "am", _now()) is None


# ---- food memory --------------------------------------------------------------


async def test_food_memory_upserts() -> None:
    """``upsert_usda`` / ``upsert_custom`` return the upserted row."""
    repo = FoodMemoryRepository(_session(rows=[_row()]))
    assert await repo.upsert_usda(
        user_key="k",
        name="oat",
        normalized_name="oat",
        usda_fdc_id=1,
        usda_description="Oats",
        basis="per_100g",
        serving_size=None,
        serving_size_unit=None,
        calories=150,
        protein_g=5.0,
        carbs_g=27.0,
        fat_g=3.0,
        now=_now(),
        aliases=["porridge"],
    )
    repo2 = FoodMemoryRepository(_session(rows=[_row()]))
    assert await repo2.upsert_custom(
        user_key="k", name="wrap", normalized_name="wrap", custom_food_id=uuid.uuid4(), now=_now()
    )


async def test_food_memory_lookups_and_delete() -> None:
    """``get_by_name`` / ``list_for_user`` / ``delete_by_name`` honor their contracts."""
    assert await FoodMemoryRepository(_session(rows=[_row()])).get_by_name(user_key="k", normalized_name="oat")
    assert await FoodMemoryRepository(_session(rows=[])).get_by_name(user_key="k", normalized_name="x") is None
    assert len(await FoodMemoryRepository(_session(rows=[_row()])).list_for_user("k")) == 1
    assert await FoodMemoryRepository(_session(scalar_one_or_none=uuid.uuid4())).delete_by_name("k", "oat")
    assert not await FoodMemoryRepository(_session(scalar_one_or_none=None)).delete_by_name("k", "x")


async def test_food_memory_alias_mutation() -> None:
    """``add_alias`` / ``remove_alias`` return the updated row or ``None``."""
    assert await FoodMemoryRepository(_session(rows=[_row()])).add_alias(
        user_key="k", normalized_name="oat", alias="gruel", now=_now()
    )
    assert await FoodMemoryRepository(_session(rows=[])).remove_alias(
        user_key="k", normalized_name="oat", alias="gruel", now=_now()
    ) is None


# ---- custom foods -------------------------------------------------------------


async def test_custom_foods_create_and_upsert() -> None:
    """``create`` / ``upsert`` return the persisted row."""
    args = dict(
        user_key="k",
        name="Wrap",
        normalized_name="wrap",
        basis="per_serving",
        serving_size=1.0,
        serving_size_unit="wrap",
        calories=300,
        protein_g=25.0,
        carbs_g=30.0,
        fat_g=10.0,
        source="manual",
        notes=None,
        now=_now(),
    )
    assert await CustomFoodsRepository(_session(rows=[_row()])).create(**args)
    assert await CustomFoodsRepository(_session(rows=[_row()])).upsert(**args)


async def test_custom_foods_lookups_update_delete() -> None:
    """``get_by_id`` / ``get_by_name`` / ``list_for_user`` / ``update_fields`` / ``delete``."""
    assert await CustomFoodsRepository(_session(rows=[_row()])).get_by_id(uuid.uuid4(), "k")
    assert await CustomFoodsRepository(_session(rows=[])).get_by_name("k", "wrap") is None
    assert len(await CustomFoodsRepository(_session(rows=[_row()])).list_for_user("k")) == 1
    assert await CustomFoodsRepository(_session(rows=[_row()])).update_fields(
        uuid.uuid4(), "k", {"name": "n"}, _now()
    )
    assert await CustomFoodsRepository(_session(scalar_one_or_none=uuid.uuid4())).delete(uuid.uuid4(), "k")


async def test_custom_foods_delete_reraises_integrity_error() -> None:
    """``delete`` re-raises ``IntegrityError`` so callers can map FK violations."""
    from sqlalchemy.exc import IntegrityError

    session = MagicMock()
    session.execute = AsyncMock(side_effect=IntegrityError("x", {}, Exception()))
    with pytest.raises(IntegrityError):
        await CustomFoodsRepository(session).delete(uuid.uuid4(), "k")


# ---- containers ---------------------------------------------------------------


async def test_containers_crud() -> None:
    """Container create / lookup / list / update / delete contracts."""
    assert await ContainersRepository(_session(rows=[_row()])).create(
        user_key="k", name="Bowl", normalized_name="bowl", tare_weight_g=250.0, now=_now()
    )
    assert await ContainersRepository(_session(rows=[_row()])).get_by_id(uuid.uuid4(), "k")
    assert len(await ContainersRepository(_session(rows=[_row()])).list_for_user("k")) == 1
    assert await ContainersRepository(_session(rows=[_row()])).update_fields(
        uuid.uuid4(), "k", {"name": "n"}, _now()
    )
    assert await ContainersRepository(_session(scalar_one_or_none=uuid.uuid4())).delete(uuid.uuid4(), "k")


async def test_containers_photo_ops() -> None:
    """``set_photo`` / ``clear_photo`` map a returned id to bool; ``get_photo`` decodes bytes."""
    assert await ContainersRepository(_session(scalar_one_or_none=uuid.uuid4())).set_photo(
        container_id=uuid.uuid4(), user_key="k", photo=b"p", photo_thumb=b"t", mime="image/jpeg", now=_now()
    )
    assert await ContainersRepository(_session(scalar_one_or_none=uuid.uuid4())).clear_photo(
        container_id=uuid.uuid4(), user_key="k", now=_now()
    )
    got = await ContainersRepository(_session(first=(b"img", "image/png"))).get_photo(uuid.uuid4(), "k", False)
    assert got == (b"img", "image/png")
    assert await ContainersRepository(_session(first=None)).get_photo(uuid.uuid4(), "k", True) is None
    assert await ContainersRepository(_session(first=(None, None))).get_photo(uuid.uuid4(), "k", False) is None


# ---- weight -------------------------------------------------------------------


async def test_weight_repo() -> None:
    """Weight upsert / range / by-date / delete contracts."""
    assert await WeightRepository(_session(rows=[_row()])).upsert(
        "k", date(2026, 5, 20), Decimal("180.5"), "lb", _now()
    )
    assert len(await WeightRepository(_session(rows=[_row(), _row()])).list_range(
        "k", date(2026, 5, 1), date(2026, 5, 31)
    )) == 2
    assert await WeightRepository(_session(rows=[_row()])).get_by_date("k", date(2026, 5, 20))
    assert await WeightRepository(_session(rows=[])).get_by_date("k", date(2026, 5, 20)) is None
    assert await WeightRepository(_session(rowcount=1)).delete("k", date(2026, 5, 20))
    assert not await WeightRepository(_session(rowcount=0)).delete("k", date(2026, 5, 20))


# ---- targets ------------------------------------------------------------------


async def test_targets_repo() -> None:
    """``get_target_profile`` returns a row or ``None``; ``upsert_targets`` executes."""
    assert await TargetsRepository(_session(rows=[_row()])).get_target_profile("k")
    assert await TargetsRepository(_session(rows=[])).get_target_profile("k") is None
    session = _session()
    await TargetsRepository(session).upsert_targets(
        user_key="k", calories=2000, protein_g=150.0, carbs_g=200.0, fat_g=60.0, updated_at=_now()
    )
    session.execute.assert_awaited()


# ---- sessions -----------------------------------------------------------------


async def test_sessions_repo() -> None:
    """Session create / get / slide / delete contracts."""
    session = _session()
    await SessionsRepository(session).create(
        token_hash=b"hash", email="a@b.c", now=_now(), expires_at=_now()
    )
    session.execute.assert_awaited()
    assert await SessionsRepository(_session(rows=[_row()])).get(b"hash")
    assert await SessionsRepository(_session(rows=[])).get(b"hash") is None
    assert await SessionsRepository(_session(rowcount=1)).slide(
        token_hash=b"hash", now=_now(), new_expires_at=_now()
    ) == 1
    assert await SessionsRepository(_session(rowcount=2)).delete(b"hash") == 2


# ---- logs ---------------------------------------------------------------------


async def test_logs_repo() -> None:
    """``list_logs`` returns a list of row dicts."""
    out = await LogsRepository(_session(rows=[_row()])).list_logs("k", date(2026, 5, 1), date(2026, 5, 31))
    assert len(out) == 1


# ---- empty-fields re-fetch branches -------------------------------------------


async def test_empty_field_updates_refetch() -> None:
    """``update_fields`` with no fields re-fetches the existing row instead of writing."""
    assert await CustomFoodsRepository(_session(rows=[_row()])).update_fields(
        uuid.uuid4(), "k", {}, _now()
    )
    assert await ContainersRepository(_session(rows=[_row()])).update_fields(
        uuid.uuid4(), "k", {}, _now()
    )
    assert await ProgressPhotoTagRepository(_session(rows=[_row()])).update_fields(
        tag_id=uuid.uuid4(), user_key="k", fields={}, now=_now()
    )


async def test_progress_photo_insert_idempotent() -> None:
    """``insert`` with an idempotency key takes the on-conflict-do-update path."""
    assert await ProgressPhotoRepository(_session(rows=[_row()])).insert(
        user_key="k",
        log_date=date(2026, 5, 20),
        tag_id=uuid.uuid4(),
        photo=b"p",
        photo_thumb=b"t",
        photo_mime="image/jpeg",
        bytes_=1,
        sha256="abc",
        now=_now(),
        idempotency_key=uuid.uuid4(),
    )


async def test_entries_daily_log_id_staticmethod() -> None:
    """``EntriesRepository.daily_log_id`` delegates to the canonical UUID5 helper."""
    from pulse_server.services.log_ids import daily_log_id

    out = EntriesRepository.daily_log_id("khash", date(2026, 5, 20))
    assert out == daily_log_id("khash", date(2026, 5, 20))


# ---- entries ------------------------------------------------------------------


async def test_entries_repo() -> None:
    """``ensure_daily_log`` / ``create_food_entry`` / ``list_...`` / ``delete_entry``."""
    session = _session()
    await EntriesRepository(session).ensure_daily_log(str(uuid.uuid4()), "k", date(2026, 5, 20))
    session.execute.assert_awaited()
    created = await EntriesRepository(_session(rows=[_row()])).create_food_entry(
        entry_id=uuid.uuid4(),
        daily_log_id=str(uuid.uuid4()),
        user_key="k",
        entry_group_id=uuid.uuid4(),
        display_name="Oats",
        quantity_text="1 cup",
        normalized_quantity_value=1.0,
        normalized_quantity_unit="cup",
        usda_fdc_id=123,
        usda_description="Oats",
        custom_food_id=None,
        calories=150,
        protein_g=5.0,
        carbs_g=27.0,
        fat_g=3.0,
        consumed_at=_now(),
    )
    assert "id" in created
    assert len(await EntriesRepository(_session(rows=[_row()])).list_entries_by_daily_log_id(str(uuid.uuid4()))) == 1
    assert await EntriesRepository(_session(scalar_one_or_none=uuid.uuid4())).delete_entry(uuid.uuid4(), "k")


# ---- auth exchange codes ------------------------------------------------------


async def test_auth_exchange_codes_repo() -> None:
    """Code create / consume / purge contracts."""
    session = _session()
    await AuthExchangeCodesRepository(session).create(
        code_hash=b"h", email="a@b.c", code_challenge="chal", now=_now(), expires_at=_now()
    )
    session.execute.assert_awaited()
    assert await AuthExchangeCodesRepository(_session(rows=[_row()])).consume(b"h")
    assert await AuthExchangeCodesRepository(_session(rows=[])).consume(b"h") is None
    assert await AuthExchangeCodesRepository(_session(rowcount=3)).purge_expired(_now()) == 3


# ---- progress photos ----------------------------------------------------------


async def test_progress_photo_repo() -> None:
    """Progress-photo insert / list / get / delete contracts."""
    assert await ProgressPhotoRepository(_session(rows=[_row()])).insert(
        user_key="k",
        log_date=date(2026, 5, 20),
        tag_id=uuid.uuid4(),
        photo=b"p",
        photo_thumb=b"t",
        photo_mime="image/jpeg",
        bytes_=1,
        sha256="abc",
        now=_now(),
    )
    assert len(await ProgressPhotoRepository(_session(rows=[_row()])).list_metadata(
        user_key="k", frm=date(2026, 5, 1), to=date(2026, 5, 31)
    )) == 1
    assert await ProgressPhotoRepository(_session(rows=[_row()])).get_photo(
        photo_id=uuid.uuid4(), user_key="k", thumb=False
    )
    assert await ProgressPhotoRepository(
        _session(scalar_one_or_none=uuid.uuid4())
    ).delete(photo_id=uuid.uuid4(), user_key="k")


async def test_progress_photo_tag_repo() -> None:
    """Progress-photo-tag list / get / create / update / seed / count contracts."""
    assert len(await ProgressPhotoTagRepository(_session(rows=[_row()])).list_for_user("k")) == 1
    assert await ProgressPhotoTagRepository(_session(rows=[_row()])).get_by_id(tag_id=uuid.uuid4(), user_key="k")
    assert await ProgressPhotoTagRepository(_session(rows=[_row()])).create(
        user_key="k", name="Front", normalized_name="front", sort_order=0, now=_now()
    )
    assert await ProgressPhotoTagRepository(_session(rows=[_row()])).update_fields(
        tag_id=uuid.uuid4(), user_key="k", fields={"name": "n"}, now=_now()
    )
    # Empty defaults short-circuits without executing.
    session = _session()
    await ProgressPhotoTagRepository(session).bulk_seed_if_empty(user_key="k", defaults=[], now=_now())
    session.execute.assert_not_awaited()
    # Non-empty defaults executes the insert.
    session2 = _session()
    await ProgressPhotoTagRepository(session2).bulk_seed_if_empty(
        user_key="k", defaults=[("Front", "front", 0)], now=_now()
    )
    session2.execute.assert_awaited()
    assert await ProgressPhotoTagRepository(_session(scalar_one=4)).photo_count(tag_id=uuid.uuid4(), user_key="k") == 4
