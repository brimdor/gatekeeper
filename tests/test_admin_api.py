"""Integration tests for Gatekeeper admin API endpoints.

Tests key management, module status, route policies, audit log,
auth status, dashboard, and admin UI pages.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
class TestKeyManagement:
    """Tests for /admin/api/keys endpoints."""

    async def test_create_key(self, client, admin_headers):
        """POST /admin/api/keys creates a new API key."""
        response = await client.post(
            "/admin/api/keys",
            json={"name": "test-key", "permissions": "*"},
            headers=admin_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-key"
        assert data["key_prefix"].startswith("gkp_")
        assert len(data["raw_key"]) > 20
        assert isinstance(data["id"], int)  # Key now includes database ID

    async def test_create_key_with_permissions(self, client, admin_headers):
        """POST /admin/api/keys with specific permissions."""
        response = await client.post(
            "/admin/api/keys",
            json={"name": "drive-only", "permissions": "drive"},
            headers=admin_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "drive-only"

    async def test_list_keys(self, client, admin_headers):
        """GET /admin/api/keys returns list of keys."""
        # Create a key first
        await client.post(
            "/admin/api/keys",
            json={"name": "list-test", "permissions": "*"},
            headers=admin_headers,
        )
        response = await client.get("/admin/api/keys", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["name"] is not None
        assert data[0]["key_prefix"] is not None

    async def test_revoke_key(self, client, admin_headers):
        """DELETE /admin/api/keys/{id} revokes a key."""
        # Create a key and get its ID directly from the response
        create_resp = await client.post(
            "/admin/api/keys",
            json={"name": "revoke-test", "permissions": "*"},
            headers=admin_headers,
        )
        key_id = create_resp.json()["id"]

        # Revoke it
        response = await client.delete(f"/admin/api/keys/{key_id}", headers=admin_headers)
        assert response.status_code == 204

    async def test_revoke_nonexistent_key_returns_404(self, client, admin_headers):
        """DELETE /admin/api/keys/9999 returns 404."""
        response = await client.delete("/admin/api/keys/9999", headers=admin_headers)
        assert response.status_code == 404


@pytest.mark.asyncio
class TestModuleStatus:
    """Tests for /admin/api/modules endpoints."""

    async def test_list_modules(self, client, admin_headers):
        """GET /admin/api/modules returns all three modules."""
        response = await client.get("/admin/api/modules", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        names = {m["name"] for m in data}
        assert "drive" in names
        assert "gmail" in names
        assert "calendar" in names

    async def test_module_status_fields(self, client, admin_headers):
        """Each module has expected fields."""
        response = await client.get("/admin/api/modules", headers=admin_headers)
        data = response.json()
        for mod in data:
            assert "name" in mod
            assert "display_name" in mod
            assert "icon" in mod
            assert "description" in mod
            assert "enabled" in mod
            assert "route_count" in mod
            assert "scopes" in mod


@pytest.mark.asyncio
class TestRoutePolicies:
    """Tests for /admin/api/routes endpoints."""

    async def test_list_all_routes(self, client, admin_headers):
        """GET /admin/api/routes returns all route policies."""
        response = await client.get("/admin/api/routes", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 39  # 13 + 14 + 12 routes

    async def test_list_routes_filtered_by_module(self, client, admin_headers):
        """GET /admin/api/routes?module=drive returns only drive routes."""
        response = await client.get("/admin/api/routes?module=drive", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 13
        for route in data:
            assert route["module"] == "drive"

    async def test_list_routes_gmail_module(self, client, admin_headers):
        """GET /admin/api/routes?module=gmail returns gmail routes."""
        response = await client.get("/admin/api/routes?module=gmail", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 14

    async def test_list_routes_calendar_module(self, client, admin_headers):
        """GET /admin/api/routes?module=calendar returns calendar routes."""
        response = await client.get("/admin/api/routes?module=calendar", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 12

    async def test_route_policy_fields(self, client, admin_headers):
        """Route policies have expected fields."""
        response = await client.get("/admin/api/routes", headers=admin_headers)
        data = response.json()
        for route in data:
            assert "id" in route
            assert "module" in route
            assert "route" in route
            assert "enabled" in route
            assert "policy_config" in route

    async def test_update_route_toggle_enabled(self, client, admin_headers):
        """PATCH /admin/api/routes/{id} toggles enabled status."""
        # Get the first route
        routes_resp = await client.get("/admin/api/routes?module=drive", headers=admin_headers)
        route_id = routes_resp.json()[0]["id"]

        # Toggle it off
        response = await client.patch(
            f"/admin/api/routes/{route_id}",
            json={"enabled": False},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False

        # Toggle it back on
        response = await client.patch(
            f"/admin/api/routes/{route_id}",
            json={"enabled": True},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True

    async def test_update_route_config(self, client, admin_headers):
        """PATCH /admin/api/routes/{id} updates policy config."""
        routes_resp = await client.get("/admin/api/routes?module=drive", headers=admin_headers)
        route_id = routes_resp.json()[0]["id"]

        response = await client.patch(
            f"/admin/api/routes/{route_id}",
            json={"policy_config": {"max_results": 10}},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "max_results" in data["policy_config"]

    async def test_update_nonexistent_route_returns_404(self, client, admin_headers):
        """PATCH /admin/api/routes/9999 returns 404."""
        response = await client.patch(
            "/admin/api/routes/9999",
            json={"enabled": True},
            headers=admin_headers,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestAuditLog:
    """Tests for /admin/api/audit endpoint."""

    async def test_audit_list(self, client, admin_headers):
        """GET /admin/api/audit returns audit log (may be empty)."""
        response = await client.get("/admin/api/audit", headers=admin_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_audit_with_module_filter(self, client, admin_headers):
        """GET /admin/api/audit?module=drive filters by module."""
        response = await client.get("/admin/api/audit?module=drive", headers=admin_headers)
        assert response.status_code == 200

    async def test_audit_with_key_prefix_filter(self, client, admin_headers):
        """GET /admin/api/audit?key_prefix=gkp_ filters by key."""
        response = await client.get("/admin/api/audit?key_prefix=gkp_", headers=admin_headers)
        assert response.status_code == 200

    async def test_audit_limit_and_offset(self, client, admin_headers):
        """GET /admin/api/audit supports limit and offset."""
        response = await client.get("/admin/api/audit?limit=10&offset=0", headers=admin_headers)
        assert response.status_code == 200


@pytest.mark.asyncio
class TestAuthStatus:
    """Tests for /admin/api/auth/status endpoint."""

    async def test_auth_status_defaults(self, client, admin_headers):
        """GET /admin/api/auth/status returns status structure."""
        response = await client.get("/admin/api/auth/status", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data
        assert "scopes" in data
        assert "expired" in data
        assert "has_refresh_token" in data


@pytest.mark.asyncio
class TestDashboard:
    """Tests for /admin/api/dashboard endpoint."""

    async def test_dashboard_structure(self, client, admin_headers):
        """GET /admin/api/dashboard returns expected fields."""
        response = await client.get("/admin/api/dashboard", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert "active_keys" in data
        assert "enabled_routes" in data
        assert "auth_connected" in data

    async def test_dashboard_types(self, client, admin_headers):
        """Dashboard fields have correct types."""
        response = await client.get("/admin/api/dashboard", headers=admin_headers)
        data = response.json()
        assert isinstance(data["total_requests"], int)
        assert isinstance(data["active_keys"], int)
        assert isinstance(data["enabled_routes"], int)
        assert isinstance(data["auth_connected"], bool)


@pytest.mark.asyncio
class TestAdminUIPages:
    """Tests for admin UI HTML pages."""

    async def test_dashboard_page(self, client, admin_headers):
        """GET /admin/ returns dashboard HTML."""
        # Admin UI pages don't require auth at the HTML level
        # (auth is enforced via JS on the client side)
        response = await client.get("/admin/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    async def test_modules_page(self, client):
        """GET /admin/modules returns modules HTML."""
        response = await client.get("/admin/modules")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    async def test_keys_page(self, client):
        """GET /admin/keys returns keys HTML."""
        response = await client.get("/admin/keys")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    async def test_audit_page(self, client):
        """GET /admin/audit returns audit HTML."""
        response = await client.get("/admin/audit")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    async def test_auth_page(self, client):
        """GET /admin/auth returns auth HTML."""
        response = await client.get("/admin/auth")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


@pytest.mark.asyncio
class TestAdminAuthEnforcement:
    """Tests that admin endpoints require Basic Auth."""

    async def test_keys_without_auth_returns_401(self, client):
        """GET /admin/api/keys without auth returns 401."""
        response = await client.get("/admin/api/keys")
        assert response.status_code == 401

    async def test_modules_without_auth_returns_401(self, client):
        """GET /admin/api/modules without auth returns 401."""
        response = await client.get("/admin/api/modules")
        assert response.status_code == 401

    async def test_routes_without_auth_returns_401(self, client):
        """GET /admin/api/routes without auth returns 401."""
        response = await client.get("/admin/api/routes")
        assert response.status_code == 401

    async def test_dashboard_without_auth_returns_401(self, client):
        """GET /admin/api/dashboard without auth returns 401."""
        response = await client.get("/admin/api/dashboard")
        assert response.status_code == 401

    async def test_create_key_with_wrong_auth_returns_401(self, client, wrong_admin_headers):
        """POST /admin/api/keys with wrong auth returns 401."""
        response = await client.post(
            "/admin/api/keys",
            json={"name": "bad-key", "permissions": "*"},
            headers=wrong_admin_headers,
        )
        assert response.status_code == 401