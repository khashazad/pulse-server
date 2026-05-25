"""Shared pytest env defaults.

Module-level env defaults so test files that import the app at import time
(via `from pulse_server.app import app`) succeed before any fixture
runs.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault("USDA_API_KEY", "test-usda")
os.environ.setdefault("GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "secret")
os.environ.setdefault("OAUTH_REDIRECT_URI", "https://api.example.com/auth/google/callback")
os.environ.setdefault("APP_REDIRECT_SCHEME", "diettracker")
os.environ.setdefault("ALLOWED_EMAILS", "khashzd@gmail.com")
os.environ.setdefault("LEGACY_USER_KEY", "khash")
os.environ.setdefault("APP_ENV", "local")

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Clear process-global rate limiters before each test.

    The limiters are module-level singletons, so without a reset their hit
    counts would leak across tests sharing the worker and cause spurious 429s.
    """
    limiters = []
    try:
        from pulse_server.routers.usda import _usda_rate_limiter

        limiters.append(_usda_rate_limiter)
    except Exception:  # pragma: no cover - import-time guard
        pass
    try:
        from pulse_server.routers.auth import _auth_rate_limiter

        limiters.append(_auth_rate_limiter)
    except Exception:  # pragma: no cover
        pass
    try:
        from pulse_server.routers.containers import _photo_upload_rate_limiter as _c

        limiters.append(_c)
    except Exception:  # pragma: no cover
        pass
    try:
        from pulse_server.routers.measures_photos import _photo_upload_rate_limiter as _m

        limiters.append(_m)
    except Exception:  # pragma: no cover
        pass
    for limiter in limiters:
        limiter.reset()
    yield
