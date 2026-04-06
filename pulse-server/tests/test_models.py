import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch


# Summary: Validates that Settings reads required values from environment variables.
# Parameters:
# - monkeypatch (pytest.MonkeyPatch): Fixture used to set temporary environment values.
# Returns:
# - None: The test performs assertions only.
# Raises/Throws:
# - AssertionError: Raised when actual settings values differ from expectations.
def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("USDA_API_KEY", "test-usda-key")
    monkeypatch.setenv("API_KEY", "test-api-key")

    from nutrition_server.config import Settings

    settings = Settings()
    assert settings.database_url == "postgresql://localhost/test"
    assert settings.usda_api_key == "test-usda-key"
    assert settings.api_key == "test-api-key"
    assert settings.default_user_key == "default"
    assert settings.port == 8787
    assert settings.timezone == "America/Toronto"


# Summary: Ensures that Settings validation fails when DATABASE_URL is missing.
# Parameters:
# - monkeypatch (pytest.MonkeyPatch): Fixture used to clear and set environment values.
# Returns:
# - None: The test only validates exception behavior.
# Raises/Throws:
# - AssertionError: Raised when Settings unexpectedly initializes without DATABASE_URL.
def test_settings_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("USDA_API_KEY", "k")
    monkeypatch.setenv("API_KEY", "k")

    from nutrition_server.config import Settings

    with pytest.raises(Exception):
        Settings()


# Summary: Verifies auth dependency rejects requests without a matching API key header.
# Parameters:
# - None: Uses an in-memory FastAPI app and patched auth configuration.
# Returns:
# - None: The test performs HTTP status assertions only.
# Raises/Throws:
# - AssertionError: Raised if unauthorized requests are not rejected.
def test_auth_rejects_missing_key() -> None:
    with patch("nutrition_server.auth._configured_key", "secret"):
        from nutrition_server.auth import require_api_key

        app = FastAPI()

        # Summary: Test endpoint guarded by API-key dependency.
        # Parameters:
        # - key (str): Resolved dependency value from the auth checker.
        # Returns:
        # - dict[str, bool]: Response payload indicating success.
        # Raises/Throws:
        # - fastapi.HTTPException: Propagated when dependency authorization fails.
        @app.get("/test")
        def endpoint(key: str = Depends(require_api_key)) -> dict[str, bool]:
            _ = key
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 401


# Summary: Verifies auth dependency accepts requests containing the configured API key.
# Parameters:
# - None: Uses an in-memory FastAPI app and patched auth configuration.
# Returns:
# - None: The test performs HTTP status assertions only.
# Raises/Throws:
# - AssertionError: Raised if authorized requests are rejected.
def test_auth_accepts_valid_key() -> None:
    with patch("nutrition_server.auth._configured_key", "secret"):
        from nutrition_server.auth import require_api_key

        app = FastAPI()

        # Summary: Test endpoint guarded by API-key dependency.
        # Parameters:
        # - key (str): Resolved dependency value from the auth checker.
        # Returns:
        # - dict[str, bool]: Response payload indicating success.
        # Raises/Throws:
        # - fastapi.HTTPException: Propagated when dependency authorization fails.
        @app.get("/test")
        def endpoint(key: str = Depends(require_api_key)) -> dict[str, bool]:
            _ = key
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/test", headers={"X-API-Key": "secret"})
        assert response.status_code == 200
