"""Tests that `build_mcp` registers the documented tool surface and instructions.

Verifies that the MCP server returned by `build_mcp` exposes every tool
the iOS/agent contracts depend on, and that the assembled workflow
instructions reference the canonical helpers (e.g., `resolve_food`,
`list_meals`, alias-management tools).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_build_mcp_registers_expected_tools() -> None:
    """`build_mcp` registers every tool name the documented agent workflow expects."""
    from pulse_server.mcp import build_mcp

    mcp = build_mcp(lambda: MagicMock())
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    expected = {
        "search_food",
        "log_food",
        "get_day",
        "delete_entry",
        "get_targets",
        "set_targets",
        "resolve_food",
        "save_custom_food",
        "update_custom_food",
        "delete_custom_food",
        "list_custom_foods",
        "remember_food",
        "forget_food",
        "list_remembered_foods",
        "add_food_alias",
        "remove_food_alias",
        "create_meal",
        "list_meals",
        "get_meal",
        "update_meal",
        "delete_meal",
        "add_meal_item",
        "update_meal_item",
        "delete_meal_item",
        "log_meal",
        "add_meal_alias",
        "remove_meal_alias",
    }
    assert expected.issubset(names)


@pytest.mark.asyncio
async def test_build_mcp_emits_workflow_instructions() -> None:
    """The MCP server's instructions string includes the canonical workflow guidance."""
    from pulse_server.mcp import build_mcp
    from pulse_server.mcp.server import WORKFLOW_INSTRUCTIONS

    mcp = build_mcp(lambda: MagicMock())
    assert mcp.instructions is not None
    assert "resolve_food" in mcp.instructions
    assert "list_meals" in mcp.instructions
    assert WORKFLOW_INSTRUCTIONS in mcp.instructions


@pytest.mark.asyncio
async def test_workflow_instructions_mention_aliases() -> None:
    """Workflow instructions reference the alias-management tools."""
    from pulse_server.mcp.server import WORKFLOW_INSTRUCTIONS
    assert "add_meal_alias" in WORKFLOW_INSTRUCTIONS
    assert "add_food_alias" in WORKFLOW_INSTRUCTIONS


from types import SimpleNamespace
from unittest.mock import patch


def _settings(**over) -> SimpleNamespace:
    """Build a minimal settings stand-in for ``build_mcp`` guard tests."""
    base = dict(
        timezone="America/Toronto",
        mcp_oauth_enabled=False,
        github_users_allowlist=set(),
        is_local_env=True,
        mcp_service_token_enabled=False,
        mcp_service_token="x" * 32,
        allowed_github_users_set=set(),
        legacy_user_key="khash",
        mcp_allow_unauth=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_build_mcp_refuses_oauth_without_allowlist_outside_local() -> None:
    """GitHub OAuth + empty allowlist outside local env is refused."""
    from pulse_server.mcp.server import build_mcp

    settings = _settings(mcp_oauth_enabled=True, github_users_allowlist=set(), is_local_env=False)
    with patch("pulse_server.mcp.server.get_settings", return_value=settings):
        with pytest.raises(RuntimeError):
            build_mcp(lambda: None)


def test_build_mcp_refuses_unauth_outside_local() -> None:
    """No auth provider outside local env without the unauth escape hatch is refused."""
    from pulse_server.mcp.server import build_mcp

    settings = _settings(is_local_env=False, mcp_allow_unauth=False)
    with patch("pulse_server.mcp.server.get_settings", return_value=settings):
        with pytest.raises(RuntimeError):
            build_mcp(lambda: None)


def test_build_mcp_adds_allowlist_middleware_with_service_token() -> None:
    """A service token plus a non-empty GitHub allowlist installs the gate middleware."""
    from pulse_server.mcp.server import build_mcp

    settings = _settings(mcp_service_token_enabled=True, allowed_github_users_set={"khash"})
    with patch("pulse_server.mcp.server.get_settings", return_value=settings), patch(
        "pulse_server.mcp.server.FastMCP.add_middleware"
    ) as add_mw:
        mcp = build_mcp(lambda: None)
    assert mcp is not None
    add_mw.assert_called_once()
