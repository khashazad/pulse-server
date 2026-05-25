"""HTTP tests for the meals, custom-foods, food-memory, and entries routers.

Drives each router through a ``TestClient`` whose DB pool and session-auth
middleware are mocked, then patches the repository classes / service
functions each route imports so the route bodies (status-code mapping,
row→DTO adaptation, 404/409/422 branches) run without a real database.
Complements the integration suite, which exercises the same routes against
PostgreSQL.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault("USDA_API_KEY", "test")

HEADERS = {"Authorization": "Bearer tok"}


def _now() -> datetime:
    """Return the current UTC timestamp (aware)."""
    return datetime.now(tz=timezone.utc)


def _dt() -> datetime:
    """Return a fixed aware UTC timestamp for deterministic row fixtures."""
    return datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def client() -> TestClient:
    """TestClient with DB pool, USDA client, and session auth mocked.

    **Outputs:**
    - TestClient: Client whose Bearer-authenticated requests resolve to the
      legacy ``user_key`` without touching a real database.
    """
    fut = _now() + timedelta(days=7)
    session_repo = AsyncMock()
    session_repo.get.return_value = {"email": "khashzd@gmail.com", "expires_at": fut}
    session_repo.slide.return_value = 1
    session_repo.delete.return_value = 1
    db_ctx = AsyncMock()
    db_ctx.__aenter__.return_value = AsyncMock()
    db_ctx.__aexit__.return_value = None

    with patch("pulse_server.db.init_pool", new_callable=AsyncMock), patch(
        "pulse_server.db.bootstrap_schema", new_callable=AsyncMock
    ), patch("pulse_server.db.close_pool", new_callable=AsyncMock), patch(
        "pulse_server.usda.USDAClient"
    ) as mock_usda_client, patch(
        "pulse_server.auth.middleware.get_session", return_value=db_ctx
    ), patch(
        "pulse_server.auth.middleware.SessionsRepository", return_value=session_repo
    ):
        mock_usda_client.return_value.close = AsyncMock()
        from pulse_server.app import app
        from pulse_server.db import get_session_dependency

        async def _fake_session_dep():
            """Yield a `MagicMock` DB session with a working async `begin()` ctx."""
            session = MagicMock()
            session.begin = MagicMock()
            session.begin.return_value.__aenter__ = AsyncMock(return_value=session)
            session.begin.return_value.__aexit__ = AsyncMock(return_value=False)
            yield session

        app.dependency_overrides[get_session_dependency] = _fake_session_dep
        try:
            with TestClient(app) as test_client:
                yield test_client
        finally:
            app.dependency_overrides.pop(get_session_dependency, None)


def _repo(**methods):
    """Build a fake repository class returning an instance with the given methods.

    **Inputs:**
    - methods: ``method_name=return_value`` (wrapped in ``AsyncMock``) or an
      explicit ``AsyncMock`` (used as-is for ``side_effect`` cases).

    **Outputs:**
    - MagicMock: A class mock whose call returns the configured instance.
    """
    inst = MagicMock()
    for name, value in methods.items():
        setattr(inst, name, value if isinstance(value, AsyncMock) else AsyncMock(return_value=value))
    return MagicMock(return_value=inst)


# ---- row fixtures -------------------------------------------------------------


def _meal_row(**over) -> dict:
    """Build a ``meals`` parent row dict."""
    row = {
        "id": uuid.uuid4(),
        "user_key": "khash",
        "name": "Breakfast",
        "normalized_name": "breakfast",
        "notes": None,
        "created_at": _dt(),
        "updated_at": _dt(),
    }
    row.update(over)
    return row


def _meal_item_row(meal_id: uuid.UUID, **over) -> dict:
    """Build a ``meal_items`` row dict."""
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


def _entry_row(**over) -> dict:
    """Build a ``food_entries`` row dict."""
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


def _custom_food_row(**over) -> dict:
    """Build a ``custom_foods`` row dict."""
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


def _memory_row(**over) -> dict:
    """Build a ``food_memory`` row dict."""
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
        "created_at": _dt(),
        "updated_at": _dt(),
    }
    row.update(over)
    return row


# ---- auth guard ---------------------------------------------------------------


def test_meals_requires_auth(client: TestClient) -> None:
    """Unauthenticated requests to a protected route return 401."""
    assert client.get("/meals").status_code == 401


def test_empty_bearer_token_rejected(client: TestClient) -> None:
    """An `Authorization: Bearer` header with no token returns 401."""
    resp = client.get("/meals", headers={"Authorization": "Bearer    "})
    assert resp.status_code == 401


# ---- meals --------------------------------------------------------------------


def test_list_meals(client: TestClient) -> None:
    """`GET /meals` projects repository summary rows into the list response."""
    rows = [
        {
            "id": uuid.uuid4(),
            "name": "Breakfast",
            "normalized_name": "breakfast",
            "notes": None,
            "item_count": 2,
            "total_calories": 400,
            "total_protein_g": 20.0,
            "total_carbs_g": 50.0,
            "total_fat_g": 12.0,
        }
    ]
    with patch("pulse_server.routers.meals.MealsRepository", _repo(list_meals=rows)):
        resp = client.get("/meals", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["meals"][0]["item_count"] == 2


def test_create_meal(client: TestClient) -> None:
    """`POST /meals` returns 201 with the created meal and items."""
    m = _meal_row()
    items = [_meal_item_row(m["id"])]
    with patch(
        "pulse_server.routers.meals.create_meal_with_items",
        new_callable=AsyncMock,
    ) as svc:
        svc.return_value = (m, items)
        resp = client.post(
            "/meals",
            headers=HEADERS,
            json={"name": "Breakfast", "items": []},
        )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Breakfast"
    assert len(resp.json()["items"]) == 1


def test_create_meal_duplicate_name(client: TestClient) -> None:
    """A duplicate meal name surfaces as 409."""
    with patch(
        "pulse_server.routers.meals.create_meal_with_items",
        new_callable=AsyncMock,
    ) as svc:
        svc.side_effect = IntegrityError("x", {}, Exception())
        resp = client.post("/meals", headers=HEADERS, json={"name": "dupe", "items": []})
    assert resp.status_code == 409


def test_get_meal_200(client: TestClient) -> None:
    """`GET /meals/{id}` returns the meal with its items."""
    m = _meal_row()
    repo = _repo(get_meal=m, list_items=[_meal_item_row(m["id"])])
    with patch("pulse_server.routers.meals.MealsRepository", repo):
        resp = client.get(f"/meals/{m['id']}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == str(m["id"])


def test_get_meal_404(client: TestClient) -> None:
    """`GET /meals/{id}` returns 404 when the meal is missing."""
    with patch("pulse_server.routers.meals.MealsRepository", _repo(get_meal=None)):
        resp = client.get(f"/meals/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404


def test_update_meal_200(client: TestClient) -> None:
    """`PATCH /meals/{id}` returns the updated meal."""
    m = _meal_row(name="Renamed")
    repo = _repo(update_meal=m, list_items=[])
    with patch("pulse_server.routers.meals.MealsRepository", repo):
        resp = client.patch(f"/meals/{m['id']}", headers=HEADERS, json={"name": "Renamed"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"


def test_update_meal_404(client: TestClient) -> None:
    """`PATCH /meals/{id}` returns 404 when no row is updated."""
    with patch("pulse_server.routers.meals.MealsRepository", _repo(update_meal=None)):
        resp = client.patch(f"/meals/{uuid.uuid4()}", headers=HEADERS, json={"name": "x"})
    assert resp.status_code == 404


def test_update_meal_conflict(client: TestClient) -> None:
    """`PATCH /meals/{id}` returns 409 on a name collision."""
    repo = _repo(update_meal=AsyncMock(side_effect=IntegrityError("x", {}, Exception())))
    with patch("pulse_server.routers.meals.MealsRepository", repo):
        resp = client.patch(f"/meals/{uuid.uuid4()}", headers=HEADERS, json={"name": "dupe"})
    assert resp.status_code == 409


def test_delete_meal_204(client: TestClient) -> None:
    """`DELETE /meals/{id}` returns 204 on success."""
    with patch("pulse_server.routers.meals.MealsRepository", _repo(delete_meal=True)):
        resp = client.delete(f"/meals/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 204


def test_delete_meal_404(client: TestClient) -> None:
    """`DELETE /meals/{id}` returns 404 when nothing was deleted."""
    with patch("pulse_server.routers.meals.MealsRepository", _repo(delete_meal=False)):
        resp = client.delete(f"/meals/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404


def test_add_meal_item_usda_201(client: TestClient) -> None:
    """`POST /meals/{id}/items` appends a USDA-backed item."""
    m = _meal_row()
    repo = _repo(get_meal=m, next_position=1, add_meal_item=_meal_item_row(m["id"], position=1))
    with patch("pulse_server.routers.meals.MealsRepository", repo):
        resp = client.post(
            f"/meals/{m['id']}/items",
            headers=HEADERS,
            json={
                "display_name": "Banana",
                "quantity_text": "1",
                "usda_fdc_id": 999,
                "usda_description": "Banana",
                "calories": 100,
                "protein_g": 1.0,
                "carbs_g": 27.0,
                "fat_g": 0.3,
            },
        )
    assert resp.status_code == 201
    assert resp.json()["position"] == 1


def test_add_meal_item_bad_cardinality_422(client: TestClient) -> None:
    """An item with both food sources returns 422."""
    with patch("pulse_server.routers.meals.MealsRepository", _repo()):
        resp = client.post(
            f"/meals/{uuid.uuid4()}/items",
            headers=HEADERS,
            json={
                "display_name": "x",
                "quantity_text": "1",
                "usda_fdc_id": 1,
                "usda_description": "d",
                "custom_food_id": str(uuid.uuid4()),
                "calories": 1,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            },
        )
    assert resp.status_code == 422


def test_add_meal_item_missing_usda_description_422(client: TestClient) -> None:
    """A USDA item without a description returns 422."""
    with patch("pulse_server.routers.meals.MealsRepository", _repo()):
        resp = client.post(
            f"/meals/{uuid.uuid4()}/items",
            headers=HEADERS,
            json={
                "display_name": "x",
                "quantity_text": "1",
                "usda_fdc_id": 1,
                "calories": 1,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            },
        )
    assert resp.status_code == 422


def test_add_meal_item_meal_not_found_404(client: TestClient) -> None:
    """Appending to a missing meal returns 404."""
    with patch("pulse_server.routers.meals.MealsRepository", _repo(get_meal=None)):
        resp = client.post(
            f"/meals/{uuid.uuid4()}/items",
            headers=HEADERS,
            json={
                "display_name": "x",
                "quantity_text": "1",
                "usda_fdc_id": 1,
                "usda_description": "d",
                "calories": 1,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            },
        )
    assert resp.status_code == 404


def test_add_meal_item_cross_tenant_422(client: TestClient) -> None:
    """A custom-food reference the user does not own returns 422."""
    from pulse_server.services.custom_foods_service import CrossTenantReferenceError

    m = _meal_row()
    repo = _repo(get_meal=m)
    with patch("pulse_server.routers.meals.MealsRepository", repo), patch(
        "pulse_server.routers.meals.assert_custom_foods_owned",
        new_callable=AsyncMock,
    ) as guard:
        guard.side_effect = CrossTenantReferenceError("nope")
        resp = client.post(
            f"/meals/{m['id']}/items",
            headers=HEADERS,
            json={
                "display_name": "x",
                "quantity_text": "1",
                "custom_food_id": str(uuid.uuid4()),
                "calories": 1,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            },
        )
    assert resp.status_code == 422


def test_delete_meal_item_204(client: TestClient) -> None:
    """`DELETE /meals/{id}/items/{item}` returns 204 on success."""
    m = _meal_row()
    repo = _repo(get_meal=m, delete_meal_item=True)
    with patch("pulse_server.routers.meals.MealsRepository", repo):
        resp = client.delete(f"/meals/{m['id']}/items/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 204


def test_delete_meal_item_meal_not_found_404(client: TestClient) -> None:
    """Deleting an item from a missing meal returns 404."""
    with patch("pulse_server.routers.meals.MealsRepository", _repo(get_meal=None)):
        resp = client.delete(f"/meals/{uuid.uuid4()}/items/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404


def test_delete_meal_item_item_not_found_404(client: TestClient) -> None:
    """Deleting a missing item returns 404."""
    m = _meal_row()
    repo = _repo(get_meal=m, delete_meal_item=False)
    with patch("pulse_server.routers.meals.MealsRepository", repo):
        resp = client.delete(f"/meals/{m['id']}/items/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404


def test_log_meal_endpoint(client: TestClient) -> None:
    """`POST /meals/{id}/log` returns created entries plus daily totals."""
    created = [_entry_row(), _entry_row()]
    day = [_entry_row(), _entry_row()]
    with patch("pulse_server.routers.meals.log_meal", new_callable=AsyncMock) as svc:
        svc.return_value = (created, day)
        resp = client.post(f"/meals/{uuid.uuid4()}/log", headers=HEADERS, json={})
    assert resp.status_code == 200
    assert len(resp.json()["entries"]) == 2


def test_log_meal_endpoint_with_consumed_at(client: TestClient) -> None:
    """`POST /meals/{id}/log` accepts a naive `consumed_at` and localizes it."""
    created = [_entry_row()]
    day = [_entry_row()]
    with patch("pulse_server.routers.meals.log_meal", new_callable=AsyncMock) as svc:
        svc.return_value = (created, day)
        resp = client.post(
            f"/meals/{uuid.uuid4()}/log",
            headers=HEADERS,
            json={"consumed_at": "2026-05-20T08:00:00"},
        )
    assert resp.status_code == 200
    # The naive timestamp should have been stamped with the server tz.
    assert svc.await_args.kwargs["consumed_at"].tzinfo is not None


# ---- custom foods -------------------------------------------------------------


def test_list_custom_foods(client: TestClient) -> None:
    """`GET /custom-foods` projects repository rows into the list response."""
    repo = _repo(list_for_user=[_custom_food_row()])
    with patch("pulse_server.routers.custom_foods.CustomFoodsRepository", repo):
        resp = client.get("/custom-foods", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["custom_foods"][0]["name"] == "Protein Wrap"


def test_create_custom_food(client: TestClient) -> None:
    """`POST /custom-foods` returns 201 with the upserted row."""
    with patch(
        "pulse_server.routers.custom_foods.upsert_custom_food_and_remember",
        new_callable=AsyncMock,
    ) as svc:
        svc.return_value = _custom_food_row()
        resp = client.post(
            "/custom-foods",
            headers=HEADERS,
            json={
                "name": "Protein Wrap",
                "basis": "per_serving",
                "calories": 300,
                "protein_g": 25.0,
                "carbs_g": 30.0,
                "fat_g": 10.0,
            },
        )
    assert resp.status_code == 201


def test_update_custom_food_200(client: TestClient) -> None:
    """`PATCH /custom-foods/{id}` returns the updated row."""
    repo = _repo(update_fields=_custom_food_row(name="Renamed"))
    with patch("pulse_server.routers.custom_foods.CustomFoodsRepository", repo):
        resp = client.patch(
            f"/custom-foods/{uuid.uuid4()}", headers=HEADERS, json={"name": "Renamed"}
        )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"


def test_update_custom_food_404(client: TestClient) -> None:
    """`PATCH /custom-foods/{id}` returns 404 when no row is updated."""
    with patch(
        "pulse_server.routers.custom_foods.CustomFoodsRepository", _repo(update_fields=None)
    ):
        resp = client.patch(f"/custom-foods/{uuid.uuid4()}", headers=HEADERS, json={"name": "x"})
    assert resp.status_code == 404


def test_update_custom_food_conflict(client: TestClient) -> None:
    """`PATCH /custom-foods/{id}` returns 409 on a name collision."""
    repo = _repo(update_fields=AsyncMock(side_effect=IntegrityError("x", {}, Exception())))
    with patch("pulse_server.routers.custom_foods.CustomFoodsRepository", repo):
        resp = client.patch(f"/custom-foods/{uuid.uuid4()}", headers=HEADERS, json={"name": "dupe"})
    assert resp.status_code == 409


def test_delete_custom_food_204(client: TestClient) -> None:
    """`DELETE /custom-foods/{id}` returns 204 on success."""
    with patch("pulse_server.routers.custom_foods.CustomFoodsRepository", _repo(delete=True)):
        resp = client.delete(f"/custom-foods/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 204


def test_delete_custom_food_404(client: TestClient) -> None:
    """`DELETE /custom-foods/{id}` returns 404 when nothing was deleted."""
    with patch("pulse_server.routers.custom_foods.CustomFoodsRepository", _repo(delete=False)):
        resp = client.delete(f"/custom-foods/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404


def test_delete_custom_food_referenced_409(client: TestClient) -> None:
    """`DELETE /custom-foods/{id}` returns 409 when the food is referenced."""
    repo = _repo(delete=AsyncMock(side_effect=IntegrityError("x", {}, Exception())))
    with patch("pulse_server.routers.custom_foods.CustomFoodsRepository", repo):
        resp = client.delete(f"/custom-foods/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 409


# ---- food memory --------------------------------------------------------------


def test_list_food_memory(client: TestClient) -> None:
    """`GET /food-memory` projects repository rows into the list response."""
    repo = _repo(list_for_user=[_memory_row()])
    with patch("pulse_server.routers.food_memory.FoodMemoryRepository", repo):
        resp = client.get("/food-memory", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["entries"][0]["name"] == "oatmeal"


def test_resolve_food(client: TestClient) -> None:
    """`GET /food-memory/resolve` returns the service's resolved payload."""
    from pulse_server.models.food_memory import ResolvedFood

    with patch(
        "pulse_server.routers.food_memory.resolve_food_by_name", new_callable=AsyncMock
    ) as svc:
        svc.return_value = ResolvedFood(type="none")
        resp = client.get("/food-memory/resolve?name=mystery", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["type"] == "none"


def test_remember_food_usda(client: TestClient) -> None:
    """`PUT /food-memory/usda` upserts and returns the memory entry."""
    repo = _repo(upsert_usda=_memory_row())
    with patch("pulse_server.routers.food_memory.FoodMemoryRepository", repo):
        resp = client.put(
            "/food-memory/usda",
            headers=HEADERS,
            json={
                "name": "oatmeal",
                "usda_fdc_id": 123,
                "usda_description": "Oats",
                "basis": "per_100g",
                "calories": 150,
                "protein_g": 5.0,
                "carbs_g": 27.0,
                "fat_g": 3.0,
            },
        )
    assert resp.status_code == 200
    assert resp.json()["name"] == "oatmeal"


def test_remember_food_custom_200(client: TestClient) -> None:
    """`PUT /food-memory/custom` upserts when the custom food exists."""
    cf_repo = _repo(get_by_id=_custom_food_row())
    fm_repo = _repo(upsert_custom=_memory_row(usda_fdc_id=None, custom_food_id=uuid.uuid4()))
    with patch("pulse_server.routers.food_memory.CustomFoodsRepository", cf_repo), patch(
        "pulse_server.routers.food_memory.FoodMemoryRepository", fm_repo
    ):
        resp = client.put(
            "/food-memory/custom",
            headers=HEADERS,
            json={"name": "wrap", "custom_food_id": str(uuid.uuid4())},
        )
    assert resp.status_code == 200


def test_remember_food_custom_404(client: TestClient) -> None:
    """`PUT /food-memory/custom` returns 404 when the custom food is missing."""
    cf_repo = _repo(get_by_id=None)
    with patch("pulse_server.routers.food_memory.CustomFoodsRepository", cf_repo):
        resp = client.put(
            "/food-memory/custom",
            headers=HEADERS,
            json={"name": "wrap", "custom_food_id": str(uuid.uuid4())},
        )
    assert resp.status_code == 404


def test_forget_food_204(client: TestClient) -> None:
    """`DELETE /food-memory` returns 204 when an entry is removed."""
    with patch(
        "pulse_server.routers.food_memory.FoodMemoryRepository", _repo(delete_by_name=True)
    ):
        resp = client.delete("/food-memory?name=oatmeal", headers=HEADERS)
    assert resp.status_code == 204


def test_forget_food_404(client: TestClient) -> None:
    """`DELETE /food-memory` returns 404 when nothing matches."""
    with patch(
        "pulse_server.routers.food_memory.FoodMemoryRepository", _repo(delete_by_name=False)
    ):
        resp = client.delete("/food-memory?name=ghost", headers=HEADERS)
    assert resp.status_code == 404


# ---- entries ------------------------------------------------------------------


def test_create_entries_201(client: TestClient) -> None:
    """`POST /entries` returns 201 with created rows and daily totals."""
    created = [_entry_row()]
    allrows = [_entry_row()]
    with patch(
        "pulse_server.routers.entries.create_entries_with_side_effects",
        new_callable=AsyncMock,
    ) as svc:
        svc.return_value = (created, allrows)
        resp = client.post(
            "/entries",
            headers=HEADERS,
            json={
                "items": [
                    {
                        "display_name": "Oatmeal",
                        "quantity_text": "1 cup",
                        "usda_fdc_id": 123,
                        "usda_description": "Oats",
                        "calories": 150,
                        "protein_g": 5.0,
                        "carbs_g": 27.0,
                        "fat_g": 3.0,
                    }
                ]
            },
        )
    assert resp.status_code == 201
    assert resp.json()["daily_totals"]["calories"] == 150


def test_create_entries_cross_tenant_422(client: TestClient) -> None:
    """`POST /entries` returns 422 when a custom food is not owned."""
    from pulse_server.services.custom_foods_service import CrossTenantReferenceError

    with patch(
        "pulse_server.routers.entries.create_entries_with_side_effects",
        new_callable=AsyncMock,
    ) as svc:
        svc.side_effect = CrossTenantReferenceError("nope")
        resp = client.post(
            "/entries",
            headers=HEADERS,
            json={
                "items": [
                    {
                        "display_name": "x",
                        "quantity_text": "1",
                        "custom_food_id": str(uuid.uuid4()),
                        "calories": 1,
                        "protein_g": 0.0,
                        "carbs_g": 0.0,
                        "fat_g": 0.0,
                    }
                ]
            },
        )
    assert resp.status_code == 422


def test_list_entries(client: TestClient) -> None:
    """`GET /entries?date=` lists the day's entries with totals."""
    repo = _repo(list_entries_by_daily_log_id=[_entry_row(), _entry_row()])
    with patch("pulse_server.routers.entries.EntriesRepository", repo):
        resp = client.get("/entries?date=2026-05-20", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["totals"]["calories"] == 300


def test_delete_entry_204(client: TestClient) -> None:
    """`DELETE /entries/{id}` returns 204 on success."""
    with patch("pulse_server.routers.entries.EntriesRepository", _repo(delete_entry=True)):
        resp = client.delete(f"/entries/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 204


def test_delete_entry_404(client: TestClient) -> None:
    """`DELETE /entries/{id}` returns 404 when nothing was deleted."""
    with patch("pulse_server.routers.entries.EntriesRepository", _repo(delete_entry=False)):
        resp = client.delete(f"/entries/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404


# ---- usda proxy ---------------------------------------------------------------


def test_usda_search_200(client: TestClient) -> None:
    """`GET /usda/search` proxies to the USDA client and returns normalized rows."""
    normalized = {
        "fdc_id": 1,
        "description": "Oats",
        "calories": 150,
        "protein_g": 5.0,
        "carbs_g": 27.0,
        "fat_g": 3.0,
        "serving_size": 40.0,
        "serving_size_unit": "g",
    }
    fake_client = MagicMock()
    fake_client.search = AsyncMock(return_value=[normalized])
    with patch("pulse_server.app.get_usda_client", return_value=fake_client):
        resp = client.get("/usda/search?q=oats&limit=5", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["results"][0]["fdc_id"] == 1


def test_usda_search_rate_limited(client: TestClient) -> None:
    """`GET /usda/search` returns 429 when the per-user limiter rejects the call."""
    with patch("pulse_server.routers.usda._usda_rate_limiter.allow", return_value=False):
        resp = client.get("/usda/search?q=oats", headers=HEADERS)
    assert resp.status_code == 429


# ---- logs ---------------------------------------------------------------------


def test_list_logs_200(client: TestClient) -> None:
    """`GET /logs` projects aggregate rows into the daily-log list response."""
    rows = [
        {
            "log_date": _dt().date(),
            "total_calories": 1800,
            "total_protein_g": 120.0,
            "total_carbs_g": 200.0,
            "total_fat_g": 55.0,
            "entry_count": 4,
        }
    ]
    with patch("pulse_server.routers.logs.LogsRepository", _repo(list_logs=rows)):
        resp = client.get("/logs?from=2026-05-01&to=2026-05-31", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["logs"][0]["entry_count"] == 4


def test_list_logs_inverted_range_400(client: TestClient) -> None:
    """`GET /logs` returns 400 when `from` is after `to`."""
    resp = client.get("/logs?from=2026-05-31&to=2026-05-01", headers=HEADERS)
    assert resp.status_code == 400


# ---- containers ---------------------------------------------------------------


def _container_row(**over) -> dict:
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


def test_get_container_200(client: TestClient) -> None:
    """`GET /containers/{id}` returns the container row."""
    with patch("pulse_server.routers.containers.ContainersRepository", _repo(get_by_id=_container_row())):
        resp = client.get(f"/containers/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["tare_weight_g"] == 250.0


def test_get_container_404(client: TestClient) -> None:
    """`GET /containers/{id}` returns 404 when missing."""
    with patch("pulse_server.routers.containers.ContainersRepository", _repo(get_by_id=None)):
        resp = client.get(f"/containers/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404


def test_update_container_conflict_409(client: TestClient) -> None:
    """`PATCH /containers/{id}` returns 409 on a name collision."""
    repo = _repo(update_fields=AsyncMock(side_effect=IntegrityError("x", {}, Exception())))
    with patch("pulse_server.routers.containers.ContainersRepository", repo):
        resp = client.patch(f"/containers/{uuid.uuid4()}", headers=HEADERS, json={"name": "dupe"})
    assert resp.status_code == 409


def test_update_container_404(client: TestClient) -> None:
    """`PATCH /containers/{id}` returns 404 when no row is updated."""
    with patch("pulse_server.routers.containers.ContainersRepository", _repo(update_fields=None)):
        resp = client.patch(f"/containers/{uuid.uuid4()}", headers=HEADERS, json={"name": "x"})
    assert resp.status_code == 404


def test_delete_container_404(client: TestClient) -> None:
    """`DELETE /containers/{id}` returns 404 when nothing was deleted."""
    with patch("pulse_server.routers.containers.ContainersRepository", _repo(delete=False)):
        resp = client.delete(f"/containers/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404


def test_upload_container_photo_too_large_413(client: TestClient) -> None:
    """`PUT /containers/{id}/photo` returns 413 when processing rejects an oversize image."""
    from pulse_server.services.image_processing import PhotoTooLargeError

    with patch(
        "pulse_server.routers.containers.process_container_photo",
        side_effect=PhotoTooLargeError("too big"),
    ):
        resp = client.put(
            f"/containers/{uuid.uuid4()}/photo",
            headers=HEADERS,
            files={"file": ("p.jpg", b"imgbytes", "image/jpeg")},
        )
    assert resp.status_code == 413


def test_upload_container_photo_404(client: TestClient) -> None:
    """`PUT /containers/{id}/photo` returns 404 when the container is missing."""
    repo = _repo(set_photo=False)
    with patch(
        "pulse_server.routers.containers.process_container_photo",
        return_value=(b"full", b"thumb", "image/jpeg"),
    ), patch("pulse_server.routers.containers.ContainersRepository", repo):
        resp = client.put(
            f"/containers/{uuid.uuid4()}/photo",
            headers=HEADERS,
            files={"file": ("p.jpg", b"imgbytes", "image/jpeg")},
        )
    assert resp.status_code == 404


def test_delete_container_photo_404(client: TestClient) -> None:
    """`DELETE /containers/{id}/photo` returns 404 when the container is missing."""
    with patch("pulse_server.routers.containers.ContainersRepository", _repo(clear_photo=False)):
        resp = client.delete(f"/containers/{uuid.uuid4()}/photo", headers=HEADERS)
    assert resp.status_code == 404


# ---- summary + targets --------------------------------------------------------


def test_daily_summary_200(client: TestClient) -> None:
    """`GET /summary/{date}` returns the service-built daily summary."""
    from pulse_server.models import DailySummaryResponse, MacroTargets, MacroTotals

    payload = DailySummaryResponse(
        date=_dt().date(),
        target=MacroTargets(calories=2000, protein_g=150.0, carbs_g=200.0, fat_g=60.0),
        consumed=MacroTotals(calories=150, protein_g=5.0, carbs_g=27.0, fat_g=3.0),
        remaining=MacroTotals(calories=1850, protein_g=145.0, carbs_g=173.0, fat_g=57.0),
        entries=[],
    )
    with patch("pulse_server.routers.summary.build_daily_summary", new_callable=AsyncMock) as svc:
        svc.return_value = payload
        resp = client.get("/summary/2026-05-20", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["target"]["calories"] == 2000


def test_get_targets_404(client: TestClient) -> None:
    """`GET /targets` returns 404 when no target profile exists."""
    with patch("pulse_server.routers.targets.TargetsRepository", _repo(get_target_profile=None)):
        resp = client.get("/targets", headers=HEADERS)
    assert resp.status_code == 404


# ---- upload rate limiting -----------------------------------------------------


def test_container_photo_upload_rate_limited_429(client: TestClient) -> None:
    """`PUT /containers/{id}/photo` returns 429 when the per-user limit is hit."""
    with patch(
        "pulse_server.routers.containers._photo_upload_rate_limiter.allow", return_value=False
    ):
        resp = client.put(
            f"/containers/{uuid.uuid4()}/photo",
            headers=HEADERS,
            files={"file": ("p.jpg", b"imgbytes", "image/jpeg")},
        )
    assert resp.status_code == 429


def test_progress_photo_upload_rate_limited_429(client: TestClient) -> None:
    """`POST /measures/photos` returns 429 when the per-user limit is hit."""
    with patch(
        "pulse_server.routers.measures_photos._photo_upload_rate_limiter.allow",
        return_value=False,
    ):
        resp = client.post(
            "/measures/photos",
            headers=HEADERS,
            data={"log_date": "2026-05-20", "tag_id": str(uuid.uuid4())},
            files={"file": ("p.jpg", b"imgbytes", "image/jpeg")},
        )
    assert resp.status_code == 429
