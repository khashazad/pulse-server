from __future__ import annotations

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware, MiddlewareContext


class ApiKeyMiddleware(Middleware):
    """Validates the X-API-Key header (or Authorization: Bearer <key>) against the configured key.

    Applied to every tool call. Listing tools is unrestricted so MCP clients can introspect.
    """

    def __init__(self, configured_key: str) -> None:
        self._configured_key = configured_key

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        headers = get_http_headers() or {}
        api_key = headers.get("x-api-key", "").strip()
        if not api_key:
            auth = headers.get("authorization", "").strip()
            if auth.lower().startswith("bearer "):
                api_key = auth[7:].strip()
        if not self._configured_key or api_key != self._configured_key:
            raise ToolError("Invalid API key")
        return await call_next(context)
