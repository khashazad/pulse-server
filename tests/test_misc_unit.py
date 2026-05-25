"""Unit tests for assorted leaf modules.

Covers the USDA client/normalizer (``usda.py``), the MCP GitHub-allowlist
middleware (``mcp/auth.py``), the progress-photo-tag service branches, and
the ``close_pool`` teardown in ``db.py`` — small modules whose paths are not
reached by the router/repository/service suites.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastmcp.exceptions import ToolError
from sqlalchemy.exc import IntegrityError

from pulse_server import db, usda
from pulse_server.mcp.auth import GitHubAllowlistMiddleware


def _now() -> datetime:
    """Return a fixed aware UTC timestamp."""
    return datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)


# ---- usda.normalize_food_nutrients --------------------------------------------


def test_normalize_matches_by_nutrient_id() -> None:
    """Nutrients matched by FDC id populate the macro schema."""
    raw = {
        "fdcId": 1,
        "description": "Oats",
        "servingSize": 40,
        "servingSizeUnit": "g",
        "foodNutrients": [
            {"nutrientId": 1008, "value": 150},
            {"nutrientId": 1003, "value": 5.0},
            {"nutrientId": 1005, "value": 27.0},
            {"nutrientId": 1004, "value": 3.0},
        ],
    }
    out = usda.normalize_food_nutrients(raw)
    assert out["calories"] == 150
    assert out["protein_g"] == 5.0
    assert out["carbs_g"] == 27.0
    assert out["fat_g"] == 3.0


def test_normalize_matches_by_name_and_skips_null_values() -> None:
    """Name heuristics map macros; nutrients with no value are skipped."""
    raw = {
        "fdcId": 2,
        "description": "Thing",
        "foodNutrients": [
            {"nutrient": {"id": None, "name": "Energy"}, "amount": 200},
            {"nutrient": {"name": "Protein"}, "value": None, "amount": None},  # skipped
            {"nutrient": {"name": "Carbohydrate, by difference"}, "amount": 10},
            {"nutrient": {"name": "Total lipid (fat)"}, "amount": 4},
        ],
    }
    out = usda.normalize_food_nutrients(raw)
    assert out["calories"] == 200
    assert out["protein_g"] == 0.0  # skipped → default
    assert out["carbs_g"] == 10.0
    assert out["fat_g"] == 4.0


def test_normalize_defaults_description() -> None:
    """A payload with no description falls back to the placeholder label."""
    out = usda.normalize_food_nutrients({"fdcId": 3})
    assert out["description"] == "Unknown food"


# ---- usda.USDAClient ----------------------------------------------------------


@pytest.mark.asyncio
async def test_usda_client_search_get_close() -> None:
    """``USDAClient`` search/get_food normalize responses and close shuts down the client."""
    fake_http = MagicMock()
    search_resp = MagicMock()
    search_resp.raise_for_status = MagicMock()
    search_resp.json = MagicMock(return_value={"foods": [{"fdcId": 1, "description": "Oats"}]})
    food_resp = MagicMock()
    food_resp.raise_for_status = MagicMock()
    food_resp.json = MagicMock(return_value={"fdcId": 9, "description": "Banana"})
    fake_http.post = AsyncMock(return_value=search_resp)
    fake_http.get = AsyncMock(return_value=food_resp)
    fake_http.aclose = AsyncMock()

    with patch("pulse_server.usda.httpx.AsyncClient", return_value=fake_http):
        client = usda.USDAClient("key")
        results = await client.search("oats", page_size=3)
        assert results[0]["fdc_id"] == 1
        food = await client.get_food(9)
        assert food["description"] == "Banana"
        await client.close()
    fake_http.aclose.assert_awaited_once()


# ---- mcp/auth.GitHubAllowlistMiddleware ---------------------------------------


@pytest.mark.asyncio
async def test_allowlist_open_mode_passes_through() -> None:
    """An empty allowlist lets every call through (open mode)."""
    mw = GitHubAllowlistMiddleware(set())
    call_next = AsyncMock(return_value="ok")
    assert await mw.on_call_tool(MagicMock(), call_next) == "ok"


@pytest.mark.asyncio
async def test_allowlist_rejects_missing_token() -> None:
    """A non-empty allowlist with no access token raises ``ToolError``."""
    mw = GitHubAllowlistMiddleware({"khash"})
    with patch("pulse_server.mcp.auth.get_access_token", return_value=None):
        with pytest.raises(ToolError):
            await mw.on_call_tool(MagicMock(), AsyncMock())


@pytest.mark.asyncio
async def test_allowlist_allows_listed_login() -> None:
    """A token whose ``login`` is allowlisted proceeds to the tool."""
    mw = GitHubAllowlistMiddleware({"khash"})
    token = MagicMock()
    token.claims = {"login": "Khash"}  # case-insensitive
    call_next = AsyncMock(return_value="ok")
    with patch("pulse_server.mcp.auth.get_access_token", return_value=token):
        assert await mw.on_call_tool(MagicMock(), call_next) == "ok"


@pytest.mark.asyncio
async def test_allowlist_rejects_unlisted_login() -> None:
    """A token whose ``login`` is not allowlisted raises ``ToolError``."""
    mw = GitHubAllowlistMiddleware({"khash"})
    token = MagicMock()
    token.claims = {"login": "stranger"}
    with patch("pulse_server.mcp.auth.get_access_token", return_value=token):
        with pytest.raises(ToolError):
            await mw.on_call_tool(MagicMock(), AsyncMock())


# ---- progress_photo_tag_service branches --------------------------------------


def _tag_repo(**methods):
    """Build a fake tag repository instance with the given async methods."""
    inst = MagicMock()
    for name, value in methods.items():
        setattr(inst, name, value if isinstance(value, AsyncMock) else AsyncMock(return_value=value))
    return inst


@pytest.mark.asyncio
async def test_list_tags_seeds_when_empty() -> None:
    """``list_tags`` seeds defaults when the user has no tags yet."""
    from pulse_server.services.progress_photo_tag_service import list_tags

    seeded = [{"id": uuid.uuid4(), "name": "front"}]
    repo = _tag_repo(
        list_for_user=AsyncMock(side_effect=[[], seeded]),
        bulk_seed_if_empty=None,
    )
    out = await list_tags(repo=repo, user_key="k")
    assert out == seeded
    repo.bulk_seed_if_empty.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_tag_blank_400() -> None:
    """``create_tag`` rejects a blank name with 400."""
    from pulse_server.services.progress_photo_tag_service import create_tag

    with pytest.raises(HTTPException) as exc:
        await create_tag(repo=_tag_repo(), user_key="k", name="   ")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_tag_duplicate_409() -> None:
    """``create_tag`` maps an IntegrityError to 409."""
    from pulse_server.services.progress_photo_tag_service import create_tag

    repo = _tag_repo(
        list_for_user=[{"sort_order": 0}],
        create=AsyncMock(side_effect=IntegrityError("x", {}, Exception())),
    )
    with pytest.raises(HTTPException) as exc:
        await create_tag(repo=repo, user_key="k", name="Front")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_create_tag_happy() -> None:
    """``create_tag`` assigns the next sort order and returns the created row."""
    from pulse_server.services.progress_photo_tag_service import create_tag

    row = {"id": uuid.uuid4(), "name": "Front"}
    repo = _tag_repo(list_for_user=[{"sort_order": 2}], create=row)
    out = await create_tag(repo=repo, user_key="k", name="Front")
    assert out is row
    assert repo.create.await_args.kwargs["sort_order"] == 3


@pytest.mark.asyncio
async def test_update_tag_blank_name_400() -> None:
    """``update_tag`` rejects a blank rename with 400."""
    from pulse_server.services.progress_photo_tag_service import update_tag

    with pytest.raises(HTTPException) as exc:
        await update_tag(repo=_tag_repo(), user_key="k", tag_id=uuid.uuid4(), name="  ", sort_order=None)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_tag_happy_name_and_order() -> None:
    """``update_tag`` forwards name + sort_order and returns the updated row."""
    from pulse_server.services.progress_photo_tag_service import update_tag

    row = {"id": uuid.uuid4(), "name": "Side"}
    repo = _tag_repo(update_fields=row)
    out = await update_tag(repo=repo, user_key="k", tag_id=uuid.uuid4(), name="Side", sort_order=5)
    assert out is row
    fields = repo.update_fields.await_args.kwargs["fields"]
    assert fields["normalized_name"] == "side"
    assert fields["sort_order"] == 5


@pytest.mark.asyncio
async def test_update_tag_duplicate_409() -> None:
    """``update_tag`` maps an IntegrityError to 409."""
    from pulse_server.services.progress_photo_tag_service import update_tag

    repo = _tag_repo(update_fields=AsyncMock(side_effect=IntegrityError("x", {}, Exception())))
    with pytest.raises(HTTPException) as exc:
        await update_tag(repo=repo, user_key="k", tag_id=uuid.uuid4(), name="Dup", sort_order=None)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_tag_not_found_404() -> None:
    """``update_tag`` raises 404 when the repository returns no row."""
    from pulse_server.services.progress_photo_tag_service import update_tag

    repo = _tag_repo(update_fields=None)
    with pytest.raises(HTTPException) as exc:
        await update_tag(repo=repo, user_key="k", tag_id=uuid.uuid4(), name=None, sort_order=1)
    assert exc.value.status_code == 404


# ---- db.close_pool ------------------------------------------------------------


def test_rate_limiter_reset_restores_quota() -> None:
    """``reset`` clears recorded hits so an exhausted key is allowed again."""
    from pulse_server.services.rate_limit import SlidingWindowRateLimiter

    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60.0)
    assert limiter.allow("k") is True
    assert limiter.allow("k") is False  # exhausted
    limiter.reset()
    assert limiter.allow("k") is True  # quota restored


@pytest.mark.asyncio
async def test_security_headers_middleware_stamps_headers() -> None:
    """``SecurityHeadersMiddleware`` adds baseline headers and HSTS only on TLS."""
    from starlette.responses import PlainTextResponse

    from pulse_server.auth.middleware import SecurityHeadersMiddleware

    mw = SecurityHeadersMiddleware(app=MagicMock())

    async def _call_next(_request):
        return PlainTextResponse("ok")

    # Plain HTTP: baseline headers, no HSTS.
    http_req = MagicMock()
    http_req.url.scheme = "http"
    http_req.headers = {}
    resp = await mw.dispatch(http_req, _call_next)
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in resp.headers

    # Forwarded HTTPS: HSTS added.
    https_req = MagicMock()
    https_req.url.scheme = "http"
    https_req.headers = {"x-forwarded-proto": "https"}
    resp2 = await mw.dispatch(https_req, _call_next)
    assert "strict-transport-security" in resp2.headers


def test_get_usda_client_requires_initialization() -> None:
    """``get_usda_client`` raises when the process-scoped client is unset."""
    from pulse_server import app as app_module

    with patch.object(app_module, "usda_client", None):
        with pytest.raises(RuntimeError):
            app_module.get_usda_client()


def test_get_usda_client_returns_initialized_client() -> None:
    """``get_usda_client`` returns the process-scoped client once initialized."""
    from pulse_server import app as app_module

    sentinel = object()
    with patch.object(app_module, "usda_client", sentinel):
        assert app_module.get_usda_client() is sentinel


@pytest.mark.asyncio
async def test_read_capped_rejects_oversize_upload() -> None:
    """``_read_capped`` raises 413 once the running total exceeds the cap."""
    from pulse_server.routers.measures_photos import _read_capped

    upload = MagicMock()
    upload.read = AsyncMock(side_effect=[b"abcdef", b""])  # 6 bytes vs 4-byte cap
    with pytest.raises(HTTPException) as exc:
        await _read_capped(upload, max_bytes=4)
    assert exc.value.status_code == 413


def test_process_photo_rejects_decompression_bomb() -> None:
    """``process_photo`` maps Pillow's ``DecompressionBombError`` to a 415-class error."""
    from PIL import Image

    from pulse_server.services import image_processing as ip

    with patch.object(ip.Image, "open", side_effect=Image.DecompressionBombError("boom")):
        with pytest.raises(ip.UnsupportedImageError):
            ip.process_photo(b"imgbytes", max_bytes=1_000_000)


@pytest.mark.asyncio
async def test_require_session_paths() -> None:
    """``require_session`` raises 401 without an email and passes when one is set."""
    from types import SimpleNamespace

    from pulse_server.auth.middleware import require_session

    no_email = MagicMock()
    no_email.state = SimpleNamespace()
    with pytest.raises(HTTPException) as exc:
        await require_session(no_email)
    assert exc.value.status_code == 401

    with_email = MagicMock()
    with_email.state = SimpleNamespace(email="khashzd@gmail.com")
    assert await require_session(with_email) is None


def test_progress_photo_process_too_large_413() -> None:
    """``_process_or_raise`` maps ``PhotoTooLargeError`` to a 413."""
    from pulse_server.services import progress_photo_service as svc
    from pulse_server.services.image_processing import PhotoTooLargeError

    with patch.object(svc, "process_photo", side_effect=PhotoTooLargeError("too big")):
        with pytest.raises(HTTPException) as exc:
            svc._process_or_raise(b"imgbytes")
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_close_pool_disposes_engine() -> None:
    """``close_pool`` disposes the engine and clears module globals."""
    engine = MagicMock()
    engine.dispose = AsyncMock()
    with patch.object(db, "_engine", engine), patch.object(db, "_session_factory", MagicMock()):
        await db.close_pool()
        engine.dispose.assert_awaited_once()
        assert db._engine is None
        assert db._session_factory is None


@pytest.mark.asyncio
async def test_close_pool_noop_when_uninitialized() -> None:
    """``close_pool`` is a no-op when no engine was ever created."""
    with patch.object(db, "_engine", None), patch.object(db, "_session_factory", None):
        await db.close_pool()
        assert db._engine is None
