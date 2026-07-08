"""End-to-end proxy test for PATCH file move against a fake Google transport."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from gatekeeper.api.proxy import GoogleProxy
from gatekeeper.models import ApiKey, RoutePolicy


def _make_api_key(permissions: str = "*") -> ApiKey:
    return ApiKey(
        name="test-key",
        key_hash="$2b$12$fakehashfakehashfakehashfakehashfa",
        key_prefix="gkp_test",
        permissions=permissions,
    )


def _mock_creds(token: str = "mock_access_token") -> MagicMock:
    creds = MagicMock()
    creds.token = token
    creds.expired = False
    creds.refresh_token = "mock_refresh"
    return creds


@pytest.mark.asyncio
class TestPatchMoveE2E:
    """Full router -> proxy -> fake Google path for a PATCH move request."""

    async def test_patch_move_sends_query_and_body_correctly(self, db_session):
        """PATCH move: addParents/removeParents go to query, name goes to body."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.update",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        captured = {}

        def _fake_handler(request: httpx.Request):
            captured["url"] = str(request.url)
            captured["method"] = request.method
            captured["query"] = dict(request.url.params)
            try:
                captured["body"] = json.loads(request.content.decode())
            except Exception:
                captured["body"] = request.content.decode()
            return httpx.Response(
                status_code=200,
                json={"id": "file123", "name": "renamed.doc"},
            )

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            from unittest.mock import AsyncMock

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            async def _mock_patch(*args, **kwargs):
                request = httpx.Request(
                    "PATCH",
                    kwargs.get("url", args[0] if args else ""),
                    params=kwargs.get("params", {}),
                    headers={},
                    content=json.dumps(kwargs.get("json", {})).encode(),
                )
                return _fake_handler(request)

            mock_client.patch = AsyncMock(side_effect=_mock_patch)
            mock_client_cls.return_value = mock_client

            result = await proxy.call_google(
                module_name="drive",
                route_id="drive.files.update",
                params={
                    "file_id": "file123",
                    "add_parents": "folderA",
                    "remove_parents": "folderB",
                    "name": "renamed.doc",
                },
                api_key_record=api_key,
                request_method="PATCH",
            )

        assert result.status_code == 200
        assert captured["method"] == "PATCH"
        assert "file123" in captured["url"]
        assert captured["query"].get("addParents") == "folderA"
        assert captured["query"].get("removeParents") == "folderB"
        assert captured["body"] == {"name": "renamed.doc"}
        assert "file_id" not in captured["body"]
        assert "addParents" not in captured["body"]
        assert "removeParents" not in captured["body"]
