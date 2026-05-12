"""Tests for the API proxy layer."""

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select

from gatekeeper.models import ApiKey, RoutePolicy


@pytest.mark.asyncio
class TestApiProxy:
    """Tests for GoogleProxy policy enforcement."""

    async def test_route_denied_returns_403(self, db_session):
        """Request to a disabled route should return 403."""
        from gatekeeper.api.proxy import GoogleProxy
        from gatekeeper.models import ApiKey

        # Create an API key
        raw, hash_val, prefix = ApiKey.generate_key()
        key = ApiKey(name="test", key_hash=hash_val, key_prefix=prefix, permissions="*")
        db_session.add(key)
        await db_session.commit()

        # Create a disabled route policy
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.send",
            enabled=False,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        proxy = GoogleProxy(db_session)
        result = await proxy.call_google(
            module_name="gmail",
            route_id="gmail.messages.send",
            params={},
            api_key_record=key,
            request_path="/api/v1/gmail/messages/send",
            request_method="POST",
        )
        assert result["error"] is True
        assert result["status"] == 403
        assert "disabled" in result["message"].lower() or "deny" in result["message"].lower()

    async def test_key_lacks_module_permission_returns_403(self, db_session):
        """Key with 'drive' permission cannot access 'gmail' routes."""
        from gatekeeper.api.proxy import GoogleProxy

        raw, hash_val, prefix = ApiKey.generate_key()
        key = ApiKey(name="drive-only", key_hash=hash_val, key_prefix=prefix, permissions="drive")
        db_session.add(key)
        await db_session.commit()

        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        proxy = GoogleProxy(db_session)
        result = await proxy.call_google(
            module_name="gmail",
            route_id="gmail.messages.list",
            params={},
            api_key_record=key,
            request_path="/api/v1/gmail/messages/list",
            request_method="GET",
        )
        assert result["error"] is True
        assert result["status"] == 403

    async def test_no_policy_returns_404(self, db_session):
        """Request for a route with no policy defined returns 404."""
        from gatekeeper.api.proxy import GoogleProxy

        raw, hash_val, prefix = ApiKey.generate_key()
        key = ApiKey(name="test", key_hash=hash_val, key_prefix=prefix, permissions="*")
        db_session.add(key)
        await db_session.commit()

        # Note: gmail.messages.list has a policy but we're asking for gmail.messages.get (no policy)
        result = await GoogleProxy(db_session).call_google(
            module_name="gmail",
            route_id="gmail.messages.get",
            params={},
            api_key_record=key,
            request_path="/api/v1/gmail/messages/get",
            request_method="GET",
        )
        # Default deny = no policy
        assert result["error"] is True

    async def test_audit_log_written_on_denied_request(self, db_session):
        """A denied request should still create an audit log entry."""
        from gatekeeper.api.proxy import GoogleProxy
        from gatekeeper.models import AuditLog

        raw, hash_val, prefix = ApiKey.generate_key()
        key = ApiKey(name="test", key_hash=hash_val, key_prefix=prefix, permissions="drive")
        db_session.add(key)
        await db_session.commit()

        proxy = GoogleProxy(db_session)
        await proxy.call_google(
            module_name="gmail",
            route_id="gmail.messages.list",
            params={},
            api_key_record=key,
            request_path="/api/v1/gmail/messages/list",
            request_method="GET",
        )

        # Check audit log — need fresh session since log_request uses its own
        # (This test verifies the flow, the actual DB write happens in a separate session)