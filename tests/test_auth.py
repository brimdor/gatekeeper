"""Tests for API key authentication and admin auth."""

import pytest
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from gatekeeper.models import ApiKey


@pytest.fixture
def app():
    """Create a test FastAPI app with auth endpoints."""
    from gatekeeper.auth import validate_api_key, require_admin

    api = FastAPI()

    @api.get("/test-api-key")
    async def test_api_key_endpoint(key: ApiKey = Depends(validate_api_key)):
        return {"name": key.name, "permissions": key.permissions}

    @api.get("/test-admin")
    async def test_admin_endpoint(admin=Depends(require_admin)):
        return {"admin": True}

    return api


# Need to import Depends for the fixture
from fastapi import Depends


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


class TestApiKeyGeneration:
    """Tests for ApiKey.generate_key()."""

    def test_generate_key_returns_gkp_prefix(self):
        """Generated keys should start with the configured prefix."""
        raw, hash_val, prefix = ApiKey.generate_key()
        assert raw.startswith("gkp_")
        assert prefix.startswith("gkp_")

    def test_generate_key_hash_verifiable(self):
        """The raw key should verify against the bcrypt hash."""
        import bcrypt

        raw, hash_val, prefix = ApiKey.generate_key()
        assert bcrypt.checkpw(raw.encode(), hash_val.encode())

    def test_generate_key_wrong_key_fails(self):
        """A different key should NOT verify against the hash."""
        import bcrypt

        raw, hash_val, prefix = ApiKey.generate_key()
        assert not bcrypt.checkpw(b"wrong_key", hash_val.encode())

    def test_generate_key_prefix_length(self):
        """Key prefix should be 12 chars (prefix + 8 random chars)."""
        raw, hash_val, prefix = ApiKey.generate_key()
        assert len(prefix) == 12  # "gkp_" + 8 chars

    def test_generate_key_custom_prefix(self):
        """Custom prefix should be respected."""
        raw, hash_val, prefix = ApiKey.generate_key(prefix="test_")
        assert raw.startswith("test_")
        assert prefix.startswith("test_")


class TestAdminAuth:
    """Tests for require_admin dependency."""

    def test_admin_auth_success(self, client):
        """Valid admin credentials should return 200."""
        from gatekeeper.config import Settings

        s = Settings(
            _env_file=None,
            secret_key="test",
            admin_password="testpass123",
            encryption_key="a" * 64,
        )
        s.ensure_secrets()

        import gatekeeper.auth

        original = gatekeeper.auth.settings
        gatekeeper.auth.settings = s

        try:
            response = client.get(
                "/test-admin",
                auth=(s.admin_username, s.admin_password),
            )
            assert response.status_code == 200
            assert response.json() == {"admin": True}
        finally:
            gatekeeper.auth.settings = original

    def test_admin_auth_wrong_password(self, client):
        """Wrong password should return 401."""
        from gatekeeper.config import Settings

        s = Settings(
            _env_file=None,
            secret_key="test",
            admin_password="correctpass",
            encryption_key="a" * 64,
        )
        s.ensure_secrets()

        import gatekeeper.auth

        original = gatekeeper.auth.settings
        gatekeeper.auth.settings = s

        try:
            response = client.get(
                "/test-admin",
                auth=(s.admin_username, "wrongpass"),
            )
            assert response.status_code == 401
        finally:
            gatekeeper.auth.settings = original

    def test_admin_auth_no_credentials(self, client):
        """Missing credentials should return 401."""
        from gatekeeper.config import Settings

        s = Settings(
            _env_file=None,
            secret_key="test",
            admin_password="testpass",
            encryption_key="a" * 64,
        )
        s.ensure_secrets()

        import gatekeeper.auth

        original = gatekeeper.auth.settings
        gatekeeper.auth.settings = s

        try:
            response = client.get("/test-admin")
            assert response.status_code == 401
        finally:
            gatekeeper.auth.settings = original