from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient


os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault("USDA_API_KEY", "x")
os.environ.setdefault("GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "secret")
os.environ.setdefault("OAUTH_REDIRECT_URI", "https://api.example.com/auth/google/callback")
os.environ.setdefault("APP_REDIRECT_SCHEME", "diettracker")
os.environ.setdefault("ALLOWED_EMAILS", "khashzd@gmail.com")
os.environ.setdefault("LEGACY_USER_KEY", "khash")
os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("SESSION_TTL_DAYS", "7")


@pytest.fixture
def client():
    with patch("diet_tracker_server.db.init_pool", new_callable=AsyncMock), \
         patch("diet_tracker_server.db.bootstrap_schema", new_callable=AsyncMock), \
         patch("diet_tracker_server.db.close_pool", new_callable=AsyncMock), \
         patch("diet_tracker_server.usda.USDAClient") as mock_usda:
        mock_usda.return_value.close = AsyncMock()
        from diet_tracker_server.config import get_settings
        get_settings.cache_clear()
        from diet_tracker_server.app import app
        with TestClient(app) as c:
            yield c


def test_start_redirects_to_google_with_state_cookie(client):
    r = client.get("/auth/google/start", follow_redirects=False)
    assert r.status_code == 302
    location = r.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    qs = parse_qs(urlparse(location).query)
    assert qs["client_id"] == ["cid.apps.googleusercontent.com"]
    assert qs["redirect_uri"] == ["https://api.example.com/auth/google/callback"]
    assert qs["response_type"] == ["code"]
    assert qs["state"][0]
    set_cookie = r.headers.get("set-cookie", "")
    assert "oauth_state=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/auth/google" in set_cookie
