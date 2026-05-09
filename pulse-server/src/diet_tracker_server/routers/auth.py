from __future__ import annotations

import secrets

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from diet_tracker_server.auth.google import build_authorize_url


router = APIRouter(prefix="/auth")


STATE_COOKIE_NAME = "oauth_state"
STATE_COOKIE_PATH = "/auth/google"
STATE_COOKIE_MAX_AGE = 600  # 10 minutes


# Summary: Detects whether the request reached the server over TLS.
# Parameters:
# - request (Request): Incoming HTTP request.
# Returns:
# - bool: True when scheme is https or x-forwarded-proto reports https.
# Raises/Throws:
# - None: Pure header inspection.
def _is_secure_request(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


# Summary: Begins Google OAuth: sets a state cookie and redirects to Google's authorize URL.
# Parameters:
# - request (Request): Incoming HTTP request used to decide cookie Secure flag.
# Returns:
# - RedirectResponse: 302 to Google with the state echoed in the query string.
# Raises/Throws:
# - None: All work is local random + URL build.
@router.get("/google/start")
async def google_start(request: Request) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    location = build_authorize_url(state=state)
    response = RedirectResponse(url=location, status_code=302)
    response.set_cookie(
        key=STATE_COOKIE_NAME,
        value=state,
        max_age=STATE_COOKIE_MAX_AGE,
        path=STATE_COOKIE_PATH,
        secure=_is_secure_request(request),
        httponly=True,
        samesite="lax",
    )
    return response
