from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from diet_tracker_server.auth.sessions import email_to_user_key, hash_token
from diet_tracker_server.config import get_settings
from diet_tracker_server.db import get_session
from diet_tracker_server.repositories.sessions import SessionsRepository


# Paths that bypass auth + guardrail. /auth/* handles its own credential lifecycle.
PUBLIC_PATHS: frozenset[str] = frozenset({"/health"})


# Summary: Reports whether a path should bypass session auth and the user_key guardrail.
# Parameters:
# - path (str): Request path from `request.url.path`.
# Returns:
# - bool: True when the request must skip both middleware checks.
# Raises/Throws:
# - None: Pure string predicate.
def _is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith("/auth/")


class UserKeyGuardrailMiddleware(BaseHTTPMiddleware):
    """Rejects `?user_key=` on protected routes during the cutover window."""

    # Summary: Short-circuits requests that smuggle a stale `user_key` query param.
    # Parameters:
    # - request (Request): Incoming HTTP request.
    # - call_next (Callable): Downstream handler chain.
    # Returns:
    # - Response: 400 JSON when the param is present on a protected route, else `call_next` result.
    # Raises/Throws:
    # - None: Errors from downstream handlers propagate as their own responses.
    async def dispatch(self, request: Request, call_next):
        if not _is_public(request.url.path) and "user_key" in request.query_params:
            return JSONResponse(
                status_code=400,
                content={"error": "user_key query param is no longer accepted"},
            )
        return await call_next(request)


class SessionAuthMiddleware(BaseHTTPMiddleware):
    """Validates Bearer session tokens and slides the session TTL.

    Sets `request.state.email`, `request.state.user_key`, `request.state.session_expires_at`.
    """

    # Summary: Authenticates the request by Bearer token, sliding the session TTL on success.
    # Parameters:
    # - request (Request): Incoming HTTP request.
    # - call_next (Callable): Downstream handler chain.
    # Returns:
    # - Response: 401 on missing/invalid/expired session, otherwise the downstream response.
    # Raises/Throws:
    # - sqlalchemy.exc.SQLAlchemyError: Surfaces if the sessions DB write fails mid-request.
    async def dispatch(self, request: Request, call_next):
        if _is_public(request.url.path):
            return await call_next(request)

        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            return JSONResponse(status_code=401, content={"error": "Bearer token required"})
        token = header[7:].strip()
        if not token:
            return JSONResponse(status_code=401, content={"error": "Bearer token required"})

        token_hash = hash_token(token)
        settings = get_settings()
        now = datetime.now(timezone.utc)
        new_expires = now + timedelta(days=settings.session_ttl_days)

        async with get_session() as db_session:
            repo = SessionsRepository(db_session)
            row = await repo.get(token_hash)
            if row is None:
                return JSONResponse(status_code=401, content={"error": "Invalid session"})
            if row["expires_at"] <= now:
                await repo.delete(token_hash)
                await db_session.commit()
                return JSONResponse(status_code=401, content={"error": "Session expired"})
            await repo.slide(token_hash=token_hash, now=now, new_expires_at=new_expires)
            await db_session.commit()

        request.state.email = row["email"]
        request.state.user_key = email_to_user_key(row["email"])
        request.state.session_expires_at = new_expires
        return await call_next(request)


# Summary: FastAPI dependency that asserts a session was attached by the middleware.
# Parameters:
# - request (Request): Incoming HTTP request after middleware ran.
# Returns:
# - None: Confirms auth state is present so handlers can read request.state safely.
# Raises/Throws:
# - HTTPException(401): When the middleware did not populate request.state.email.
async def require_session(request: Request) -> None:
    if not getattr(request.state, "email", None):
        raise HTTPException(status_code=401, detail="Authentication required")
    return None
