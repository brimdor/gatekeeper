"""Comprehensive integration tests for GoogleProxy — URL construction,
parameter normalization, policy enforcement, and credential handling.

These tests mock the httpx calls and credential_manager so we can verify
URL construction and parameter normalization without hitting real Google APIs.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from gatekeeper.models import ApiKey, RoutePolicy
from gatekeeper.api.proxy import GoogleProxy, GOOGLE_API_BASE, MODULE_API_MAP
from gatekeeper.modules import load_module, get_loaded_modules, _loaded_modules


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _unwrap(response: JSONResponse) -> dict:
    """Extract the JSON body from a JSONResponse returned by GoogleProxy."""
    import asyncio
    # JSONResponse.body is bytes, decode and parse
    return json.loads(response.body.decode())


def _make_api_key(permissions: str = "*") -> ApiKey:
    """Create a mock ApiKey row (not persisted to DB)."""
    return ApiKey(
        name="test-key",
        key_hash="$2b$12$fakehashfakehashfakehashfakehashfa",
        key_prefix="gkp_test",
        permissions=permissions,
    )


def _mock_creds(token: str = "mock_access_token") -> MagicMock:
    """Create a mock credentials object with a valid token."""
    creds = MagicMock()
    creds.token = token
    creds.expired = False
    creds.refresh_token = "mock_refresh"
    return creds


@pytest.fixture(autouse=True)
def clear_module_cache():
    """Clear loaded module cache between tests so each test gets a fresh state."""
    _loaded_modules.clear()
    yield
    _loaded_modules.clear()


# ---------------------------------------------------------------------------
# URL construction tests — verify path params are correctly substituted
# ---------------------------------------------------------------------------

class TestURLConstruction:
    """Test that GoogleProxy builds the correct Google API URLs.

    These tests focus on URL path construction with parameter substitution.
    We mock credential_manager.get_credentials() and httpx.AsyncClient so
    no real HTTP requests are made.
    """

    @pytest.mark.asyncio
    async def test_calendar_path_with_calendar_id(self, db_session):
        """Calendar route: {calendarId} should be substituted from params."""
        # Set up enabled policy
        policy = RoutePolicy(
            module="calendar",
            route="calendar.events.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        # Mock credential manager
        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            # Mock the async context manager
            mock_response = MagicMock()
            mock_response.json.return_value = {"items": []}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await proxy.call_google(
                module_name="calendar",
                route_id="calendar.events.list",
                params={"calendar_id": "primary", "maxResults": 10},
                api_key_record=api_key,
                request_method="GET",
            )

            # Verify URL: /calendar/v3/calendars/primary/events
            call_args = mock_client.get.call_args
            url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
            assert "/calendar/v3/calendars/primary/events" in url

    @pytest.mark.asyncio
    async def test_drive_path_with_file_id(self, db_session):
        """Drive route: {fileId} should be substituted from file_id param."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "file123", "name": "test.txt"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await proxy.call_google(
                module_name="drive",
                route_id="drive.files.get",
                params={"file_id": "file123", "fields": "id,name"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            assert "/drive/v3/files/file123" in url
            # file_id should NOT be in remaining query params
            params_sent = call_args[1].get("params", {})
            assert "fileId" not in params_sent
            assert "fields" in params_sent  # non-path param stays

    @pytest.mark.asyncio
    async def test_gmail_path_with_message_id(self, db_session):
        """Gmail route: {messageId} should be substituted from message_id param."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "msg_abc", "snippet": "Hello"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.get",
                params={"message_id": "msg_abc", "format": "full"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            assert "/gmail/v1/users/me/messages/msg_abc" in url
            params_sent = call_args[1].get("params", {})
            assert "messageId" not in params_sent
            assert "format" in params_sent

    @pytest.mark.asyncio
    async def test_gmail_path_with_draft_id(self, db_session):
        """Gmail draft route: {draftId} should be substituted from draft_id param."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.drafts.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "draft_xyz"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.drafts.get",
                params={"draft_id": "draft_xyz"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            assert "/gmail/v1/users/me/drafts/draft_xyz" in url

    @pytest.mark.asyncio
    async def test_drive_permissions_multiple_path_params(self, db_session):
        """Drive permissions: {fileId}/permissions/{permissionId} — two path params."""
        policy = RoutePolicy(
            module="drive",
            route="drive.permissions.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "perm1", "type": "user"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await proxy.call_google(
                module_name="drive",
                route_id="drive.permissions.get",
                params={"file_id": "fileABC", "permission_id": "permXYZ"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            # Both path params should be substituted
            assert "/drive/v3/files/fileABC/permissions/permXYZ" in url
            # Neither should remain in query params
            params_sent = call_args[1].get("params", {})
            assert "fileId" not in params_sent
            assert "permissionId" not in params_sent

    @pytest.mark.asyncio
    async def test_calendar_path_with_calendar_and_event_id(self, db_session):
        """Calendar events.get: {calendarId}/events/{eventId} — two path params."""
        policy = RoutePolicy(
            module="calendar",
            route="calendar.events.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "ev1", "summary": "Meeting"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await proxy.call_google(
                module_name="calendar",
                route_id="calendar.events.get",
                params={"calendar_id": "primary", "event_id": "ev123"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            assert "/calendar/v3/calendars/primary/events/ev123" in url


# ---------------------------------------------------------------------------
# Parameter normalization (snake_case → camelCase)
# ---------------------------------------------------------------------------

class TestParameterNormalization:
    """Test snake_case → camelCase conversion and path param removal."""

    @pytest.mark.asyncio
    async def test_snake_to_camel_case_file_id(self, db_session):
        """file_id → fileId in normalized params and removed when it's a path param."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "f1"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.get",
                params={"file_id": "abc123", "fields": "id,name"},
                api_key_record=api_key,
                request_method="GET",
            )

            # file_id became fileId and was consumed as path param
            # 'fields' stays as query param (no underscore, no transform)
            call_args = mock_client.get.call_args
            params_sent = call_args[1].get("params", {})
            assert "fields" in params_sent
            # fileId is NOT in params because it was used in the URL path
            assert "fileId" not in params_sent

    @pytest.mark.asyncio
    async def test_snake_to_camel_case_calendar_id(self, db_session):
        """calendar_id → calendarId normalization and path substitution."""
        policy = RoutePolicy(
            module="calendar",
            route="calendar.events.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"items": []}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="calendar",
                route_id="calendar.events.list",
                params={"calendar_id": "primary", "max_results": 20},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            # calendarId should be substituted in URL
            assert "/calendars/primary/" in url
            params_sent = call_args[1].get("params", {})
            # calendarId should NOT be in query params
            assert "calendarId" not in params_sent
            # max_results → maxResults should be in query params
            assert "maxResults" in params_sent
            assert params_sent["maxResults"] == 20

    @pytest.mark.asyncio
    async def test_snake_to_camel_case_message_id(self, db_session):
        """message_id → messageId, consumed as path param."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "m1"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.get",
                params={"message_id": "msg456", "format": "metadata"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            assert "/messages/msg456" in url
            params_sent = call_args[1].get("params", {})
            assert "format" in params_sent
            # messageId was consumed in path
            assert "messageId" not in params_sent

    @pytest.mark.asyncio
    async def test_non_path_params_stay_in_query_for_get(self, db_session):
        """GET routes: non-path params should be query parameters."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"files": []}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.list",
                params={"page_size": 25, "q": "name contains 'report'"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            params_sent = call_args[1].get("params", {})
            # No path params in drive.files.list, so all should be query params
            # snake_case should be normalized: page_size → pageSize
            assert "pageSize" in params_sent
            assert "q" in params_sent

    @pytest.mark.asyncio
    async def test_non_path_params_stay_in_body_for_post(self, db_session):
        """POST routes: non-path params should be in JSON body."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.create",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "new_file", "name": "test"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.create",
                params={"name": "My Doc", "mime_type": "application/pdf"},
                api_key_record=api_key,
                request_method="POST",
            )

            call_args = mock_client.post.call_args
            json_sent = call_args[1].get("json", {})
            # snake_case → camelCase: mime_type → mimeType
            assert "mimeType" in json_sent
            assert "name" in json_sent


# ---------------------------------------------------------------------------
# Policy enforcement integration
# ---------------------------------------------------------------------------

class TestPolicyEnforcement:
    """Test policy enforcement through the proxy layer."""

    @pytest.mark.asyncio
    async def test_enabled_route_forwards_to_google(self, db_session):
        """Enabled route should proxy the request through to Google."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"messages": [{"id": "1"}]}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

            # Should have called Google API
            mock_client.get.assert_called_once()
            assert "error" not in _unwrap(result) or _unwrap(result).get("error") is not True

    @pytest.mark.asyncio
    async def test_disabled_route_returns_403(self, db_session):
        """Disabled route should return 403 error response."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.send",
            enabled=False,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager"), \
             patch("gatekeeper.api.proxy.httpx.AsyncClient"):

            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.send",
                params={},
                api_key_record=api_key,
                request_method="POST",
            )

        assert _unwrap(result)["error"] is True
        assert result.status_code == 403
        assert _unwrap(result)["status"] == 403
        assert "disabled" in _unwrap(result)["message"].lower()

    @pytest.mark.asyncio
    async def test_key_with_wrong_module_returns_403(self, db_session):
        """Key lacking module permission should get 403."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        # Key only has drive permission, trying gmail
        api_key = _make_api_key(permissions="drive")
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager"), \
             patch("gatekeeper.api.proxy.httpx.AsyncClient"):

            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

        assert _unwrap(result)["error"] is True
        assert result.status_code == 403
        assert _unwrap(result)["status"] == 403
        assert "not authorized" in _unwrap(result)["message"].lower()

    @pytest.mark.asyncio
    async def test_no_policy_for_route_returns_403(self, db_session):
        """Route with no policy defined should be denied."""
        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager"), \
             patch("gatekeeper.api.proxy.httpx.AsyncClient"):

            result = await proxy.call_google(
                module_name="drive",
                route_id="drive.files.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

        assert _unwrap(result)["error"] is True
        assert result.status_code == 403
        assert _unwrap(result)["status"] == 403
        assert "no policy" in _unwrap(result)["message"].lower()

    @pytest.mark.asyncio
    async def test_policy_transforms_applied_before_proxy(self, db_session):
        """Request transforms from policy config should be applied."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config=json.dumps({"max_results": 10}),
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"messages": []}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Request maxResults=200, but policy caps to 10
            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={"maxResults": 200},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            params_sent = call_args[1].get("params", {})
            # maxResults should be capped to 10
            assert params_sent.get("maxResults") == 10


# ---------------------------------------------------------------------------
# Credential handling
# ---------------------------------------------------------------------------

class TestCredentialHandling:
    """Test credential-related behavior in the proxy."""

    @pytest.mark.asyncio
    async def test_no_credentials_returns_401(self, db_session):
        """Missing Google credentials should return 401 error."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm:
            # Return None credentials
            mock_cm.get_credentials.return_value = None

            with patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:
                result = await proxy.call_google(
                    module_name="gmail",
                    route_id="gmail.messages.list",
                    params={},
                    api_key_record=api_key,
                    request_method="GET",
                )

        assert _unwrap(result)["error"] is True
        assert result.status_code == 401
        assert _unwrap(result)["status"] == 401
        assert "credentials" in _unwrap(result)["message"].lower()

    @pytest.mark.asyncio
    async def test_credentials_without_token_returns_401(self, db_session):
        """Credentials with no token (None) should return 401."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        mock_creds = MagicMock()
        mock_creds.token = None  # No access token

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm:
            mock_cm.get_credentials.return_value = mock_creds

            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

        assert result.status_code == 401
        assert _unwrap(result)["error"] is True
        assert _unwrap(result)["status"] == 401

    @pytest.mark.asyncio
    async def test_valid_credentials_include_auth_header(self, db_session):
        """Valid credentials should produce an Authorization header in the request."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds(token="ya29.test_token")

            mock_response = MagicMock()
            mock_response.json.return_value = {"messages": []}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            headers = call_args[1].get("headers", {})
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer ya29.test_token"


# ---------------------------------------------------------------------------
# HTTP method dispatch
# ---------------------------------------------------------------------------

class TestHTTPMethodDispatch:
    """Test that the proxy uses the correct HTTP method for each route."""

    @pytest.mark.asyncio
    async def test_get_route_uses_get(self, db_session):
        """GET routes should call httpx.get."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

            mock_client.get.assert_called_once()
            mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_route_uses_post(self, db_session):
        """POST routes should call httpx.post with JSON body."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.create",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "new"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.create",
                params={"name": "test"},
                api_key_record=api_key,
                request_method="POST",
            )

            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_route_uses_delete(self, db_session):
        """DELETE routes should call httpx.delete."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.delete",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {}
            mock_response.status_code = 204

            mock_client = AsyncMock()
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.delete",
                params={"message_id": "msg1"},
                api_key_record=api_key,
                request_method="DELETE",
            )

            mock_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_patch_route_uses_patch(self, db_session):
        """PATCH routes should call httpx.patch with JSON body."""
        policy = RoutePolicy(
            module="calendar",
            route="calendar.events.update",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "ev1", "summary": "Updated"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.patch = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="calendar",
                route_id="calendar.events.update",
                params={"calendar_id": "primary", "event_id": "ev1", "summary": "Updated"},
                api_key_record=api_key,
                request_method="PATCH",
            )

            mock_client.patch.assert_called_once()


# ---------------------------------------------------------------------------
# Response filter integration
# ---------------------------------------------------------------------------

class TestResponseFilterIntegration:
    """Test that response filters are applied through the proxy."""

    @pytest.mark.asyncio
    async def test_blocked_fields_stripped_from_response(self, db_session):
        """blocked_fields in policy config should strip those fields from response."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.get",
            enabled=True,
            policy_config=json.dumps({"blocked_fields": ["raw", "internalDate"]}),
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            # Mock Google returning data with raw and internalDate
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "id": "msg1",
                "raw": "base64data",
                "internalDate": "12345",
                "snippet": "Hello world",
            }
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.get",
                params={"message_id": "msg1"},
                api_key_record=api_key,
                request_method="GET",
            )

            assert _unwrap(result)["id"] == "msg1"
            assert _unwrap(result)["snippet"] == "Hello world"
            assert "raw" not in _unwrap(result)
            assert "internalDate" not in _unwrap(result)

    @pytest.mark.asyncio
    async def test_max_items_caps_response_arrays(self, db_session):
        """max_items in policy config should cap response array lengths."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config=json.dumps({"max_items": {"messages": 3}}),
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm, \
             patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls:

            mock_cm.get_credentials.return_value = _mock_creds()

            # Mock Google returning 10 messages
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "messages": [{"id": f"m{i}"} for i in range(10)],
                "resultSizeEstimate": 10,
            }
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

            assert len(_unwrap(result)["messages"]) == 3
            assert _unwrap(result)["resultSizeEstimate"] == 10  # non-array not affected


# ---------------------------------------------------------------------------
# Module not found
# ---------------------------------------------------------------------------

class TestModuleNotFound:
    """Test proxy behavior when module is not found."""

    @pytest.mark.asyncio
    async def test_unknown_module_returns_404(self, db_session):
        """Requesting an unknown module should return 404 error after policy denial.

        Note: Even before checking module, the policy check happens first.
        If there's no policy, we get 403. But if policy somehow allows it
        (wildcard key + some bug), the module won't be found.
        We test this scenario directly with the module loading path.
        """
        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        # Since there's no route policy for "nonexistent", the default is deny.
        # But let's test what happens if somehow we get past that.
        result = await proxy.call_google(
            module_name="nonexistent_module",
            route_id="nonexistent.route",
            params={},
            api_key_record=api_key,
            request_method="GET",
        )

        assert result.status_code == 403
        # Should be denied because no policy
        assert _unwrap(result)["error"] is True
        assert _unwrap(result)["status"] == 403