from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault("USDA_API_KEY", "test-usda")
os.environ.setdefault("API_KEY", "test-api-key")


@pytest.mark.asyncio
async def test_build_mcp_registers_expected_tools() -> None:
    from nutrition_server.mcp import build_mcp

    mcp = build_mcp(lambda: MagicMock())
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    expected = {"search_food", "log_food", "get_day", "delete_entry", "get_targets", "set_targets"}
    assert expected.issubset(names)


def test_api_key_middleware_imports_cleanly() -> None:
    from nutrition_server.mcp.auth import ApiKeyMiddleware

    mw = ApiKeyMiddleware("secret")
    assert mw._configured_key == "secret"
