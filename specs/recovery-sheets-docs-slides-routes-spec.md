# Spec: [Recovery] Add Sheets, Docs, and Slides Routes to the Drive Module (Fixed Architecture)

> **Status:** Recovery spec — supersedes the original implementation plan in task t_cb75e033e8c2. The original plan was found to be technically inviable because it assumed the existing proxy could route to `sheets.googleapis.com`, `docs.googleapis.com`, and `slides.googleapis.com` via `google_path` alone. It cannot. This spec defines the minimal architectural changes required to make those routes actually work.

> **Critical directive (carried over from root task):** Do NOT deploy Gatekeeper. This plan covers code changes only — commit to the `gatekeeper` repo on `main`. Chris will handle deployment and re-auth separately.

---

## Overview

Add Google Sheets, Docs, and Slides API routes into the existing Drive module so agents can read/write cell ranges, document content, and slide elements — operations the current Drive routes cannot perform.

**The single root cause of the previous plan's failure:** the proxy in `gatekeeper/api/proxy.py` hardcodes `GOOGLE_API_BASE = "https://www.googleapis.com"` and uses it for *every* URL it constructs. Sheets (`sheets.googleapis.com`), Docs (`docs.googleapis.com`), and Slides (`slides.googleapis.com`) live on **different hostnames** that `www.googleapis.com` does not serve. Live testing confirmed `https://www.googleapis.com/v4/spreadsheets/{id}` returns HTML 404, while `https://sheets.googleapis.com/v4/spreadsheets/{id}` returns 403 (endpoint exists, auth required — expected).

This spec defines three prerequisite changes plus the route additions, all of which together make the original goal achievable.

**Module placement decision:** Respect the root task's choice to add routes to the existing `DriveModule` (not new modules). The Drive module already has access to all Drive files; from a user/agent perspective Sheets/Docs/Slides are "Drive files." The architectural cost (mixing three hostnames in one module) is acceptable here. If a future cleanup wants to split them into `SheetsModule`/`DocsModule`/`SlidesModule`, the per-route `base_url` introduced by this spec makes that a mechanical refactor — no other proxy work is needed.

**Tech stack:** Python 3.12, FastAPI, Pydantic v2, httpx, google-auth.

---

## Architecture

### Components

- **`gatekeeper/modules/route.py`** — `RouteDef` Pydantic model. Gains a new optional `base_url: str | None` field.
- **`gatekeeper/api/proxy.py`** — `GoogleProxy.call_google()`. URL construction is updated to prefer `route.base_url` over the global `GOOGLE_API_BASE`.
- **`gatekeeper/modules/drive/__init__.py`** — `DriveModule.required_scopes` is expanded; 16 new `RouteDef` entries (9 Sheets + 3 Docs + 4 Slides) are appended, each with the correct `base_url`.
- **`tests/test_proxy_url_hosts.py`** — new test file. Verifies the proxy routes to the correct hostname for each new route, and confirms existing Drive/Gmail/Calendar routes still hit `www.googleapis.com`.

### Data flow

```
agent → /api/proxy/{module}/{route_id}
  → GoogleProxy.call_google()
  → builds URL: f"{route.base_url or GOOGLE_API_BASE}{google_path}"
  → forwards to Sheets/Docs/Slides/Drive/Gmail/Calendar as appropriate
```

### Dependencies

- No new third-party dependencies. The change uses only the existing httpx client, Pydantic v2, and Python's `urllib.parse`-equivalent string formatting.
- No new OAuth flows required. The new scopes are added to the existing `drive` OAuth consent. Chris will re-run `gatekeeper auth` once to re-consent (post-deploy, not part of this spec).

### Constraints / non-goals

- **Not in scope:** Splitting Drive into separate modules, adding per-module base_url defaults on `GoogleModule`, restructuring `MODULE_API_MAP`, OAuth re-consent flow changes, deployment scripts, smoke test updates.
- **In scope:** Minimal `base_url` field on `RouteDef`, three-line change in `proxy.py` URL construction, 16 new routes on the Drive module, scope list update, and tests proving multi-host routing.
- **Body transformations are out of scope.** The proxy already passes `body_params` as JSON via `httpx.AsyncClient.{post,patch,put}(json=...)`. The new Sheets/Docs/Slides write routes use the same flat-parameter → JSON-body pipeline. Two body-shape exceptions (sheets.spreadsheets.create, sheets.values.update) are called out as separate follow-up tasks in §5 so they don't block the hostname fix.

---

## File-by-File Change List

### Change 1 — `gatekeeper/modules/route.py`

**Add one optional field to `RouteDef`.**

Insert immediately after the existing `enabled_by_default: bool = True` field (line 39):

```python
    # Optional per-route base URL. When set, the proxy uses it instead of the
    # global GOOGLE_API_BASE for URL construction. Required for Google APIs
    # that don't live on www.googleapis.com (Sheets, Docs, Slides).
    # Examples: "https://sheets.googleapis.com", "https://docs.googleapis.com",
    # "https://slides.googleapis.com". Defaults to None (use GOOGLE_API_BASE).
    base_url: str | None = None
```

Rationale: keeping it `Optional[str]` preserves backwards compatibility — every existing route continues to work because `None` falls through to the current `GOOGLE_API_BASE` constant. This is the smallest possible field addition.

### Change 2 — `gatekeeper/api/proxy.py`

**Update the URL-construction block in `call_google()` (currently lines 196-202).**

Replace:

```python
        # Construct the final URL
        if route.google_path.startswith("/"):
            # google_path already includes full API path (e.g., /calendar/v3/...)
            url = f"{GOOGLE_API_BASE}{google_path}"
        else:
            # Relative path — prepend the module API prefix
            api_prefix = MODULE_API_MAP.get(module_name, f"/{module_name}/v1")
            url = f"{GOOGLE_API_BASE}{api_prefix}/{google_path}"
```

With:

```python
        # Construct the final URL
        # Per-route base_url (set on Sheets/Docs/Slides routes) takes priority
        # over the global GOOGLE_API_BASE; everything else falls back to the
        # default Google API host. This is the only URL-construction change
        # needed to support APIs on different hostnames.
        base = route.base_url or GOOGLE_API_BASE
        if route.google_path.startswith("/"):
            # google_path already includes full API path (e.g., /calendar/v3/...)
            url = f"{base}{google_path}"
        else:
            # Relative path — prepend the module API prefix
            api_prefix = MODULE_API_MAP.get(module_name, f"/{module_name}/v1")
            url = f"{base}{api_prefix}/{google_path}"
```

Rationale: three lines added (the `base = …` line, and renaming `GOOGLE_API_BASE` → `base` in the two f-strings). Behaviour for every existing route is preserved because `route.base_url` is `None` for all current routes.

### Change 3 — `gatekeeper/modules/drive/__init__.py`

**3a. Expand `required_scopes`.**

Replace the existing class header (lines 9-15):

```python
class DriveModule(GoogleModule):
    name = "drive"
    display_name = "Google Drive"
    description = "Browse, search, and read files in Google Drive"
    icon = "📁"

    required_scopes = ["https://www.googleapis.com/auth/drive"]
```

With:

```python
class DriveModule(GoogleModule):
    name = "drive"
    display_name = "Google Drive"
    description = (
        "Browse, search, and read files in Google Drive, "
        "including Sheets, Docs, and Slides content"
    )
    icon = "📁"

    required_scopes = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/presentations",
    ]
```

**3b. Append 16 new `RouteDef` entries to the `get_routes()` return list.**

Insert the entire block below immediately before the closing `]` of the `return [...]` list (currently at line 1150, just before `Module = DriveModule` at line 1153). Use a clearly delimited section header to separate from existing Drive routes:

```python
            # ── Google Sheets API (sheets.googleapis.com) ──
            # All routes target https://sheets.googleapis.com, NOT
            # www.googleapis.com, so each carries base_url=...
            RouteDef(
                route_id="drive.sheets.spreadsheets.get",
                method="GET",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}",
                description="Get spreadsheet metadata (sheets, named ranges, properties)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "The ID of the spreadsheet to retrieve",
                        },
                        "fields": {
                            "type": "string",
                            "description": "Fields to include in the response (partial response)",
                        },
                    },
                    "required": ["spreadsheet_id"],
                },
                query_params=["fields"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.sheets.values.get",
                method="GET",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}/values/{range}",
                description="Read a single range of cell values from a spreadsheet",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "The ID of the spreadsheet",
                        },
                        "range": {
                            "type": "string",
                            "description": "A1 or R1C1 notation of the range (e.g., 'Sheet1!A1:C10')",
                        },
                        "value_render_option": {
                            "type": "string",
                            "description": "FORMATTED_VALUE, UNFORMATTED_VALUE, or FORMULA",
                            "default": "FORMATTED_VALUE",
                        },
                        "date_time_render_option": {
                            "type": "string",
                            "description": "SERIAL_NUMBER or FORMATTED_STRING",
                        },
                        "major_dimension": {
                            "type": "string",
                            "description": "ROWS or COLUMNS",
                        },
                    },
                    "required": ["spreadsheet_id", "range"],
                },
                query_params=["value_render_option", "date_time_render_option", "major_dimension"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.sheets.values.batch_get",
                method="GET",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}/values:batchGet",
                description="Read multiple ranges of cell values in one request",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "The ID of the spreadsheet",
                        },
                        "ranges": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "A1/R1C1 ranges to retrieve (e.g., ['Sheet1!A1:B2'])",
                        },
                        "value_render_option": {
                            "type": "string",
                            "description": "FORMATTED_VALUE, UNFORMATTED_VALUE, or FORMULA",
                        },
                        "date_time_render_option": {"type": "string"},
                        "major_dimension": {"type": "string", "description": "ROWS or COLUMNS"},
                    },
                    "required": ["spreadsheet_id"],
                },
                query_params=["ranges", "value_render_option", "date_time_render_option", "major_dimension"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.sheets.values.update",
                method="PUT",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}/values/{range}",
                description="Write values to a range of cells in a spreadsheet",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "string"},
                        "range": {"type": "string", "description": "A1/R1C1 range to write"},
                        "values": {
                            "type": "array",
                            "items": {"type": "array", "items": {}},
                            "description": "2D array of values (e.g., [['A', 1], ['B', 2]])",
                        },
                        "value_input_option": {
                            "type": "string",
                            "description": "RAW or USER_ENTERED",
                            "default": "RAW",
                        },
                    },
                    "required": ["spreadsheet_id", "range", "values"],
                },
                query_params=["value_input_option"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.sheets.values.append",
                method="POST",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}/values/{range}:append",
                description="Append values after the last row of data in a range",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "string"},
                        "range": {
                            "type": "string",
                            "description": "A1 notation of the table to search (e.g., 'Sheet1!A1:B')",
                        },
                        "values": {
                            "type": "array",
                            "items": {"type": "array", "items": {}},
                            "description": "2D array of values to append",
                        },
                        "value_input_option": {
                            "type": "string",
                            "default": "RAW",
                            "description": "RAW or USER_ENTERED",
                        },
                        "insert_data_option": {
                            "type": "string",
                            "default": "OVERWRITE",
                            "description": "OVERWRITE or INSERT_ROWS",
                        },
                    },
                    "required": ["spreadsheet_id", "range", "values"],
                },
                query_params=["value_input_option", "insert_data_option"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.sheets.values.clear",
                method="POST",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}/values/{range}:clear",
                description="Clear values from a range of cells",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "string"},
                        "range": {"type": "string", "description": "A1/R1C1 range to clear"},
                    },
                    "required": ["spreadsheet_id", "range"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.sheets.values.batch_update",
                method="POST",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}/values:batchUpdate",
                description="Update multiple ranges of cell values in a single request",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "string"},
                        "value_input_option": {
                            "type": "string",
                            "default": "RAW",
                            "description": "RAW or USER_ENTERED",
                        },
                        "data": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "range": {"type": "string"},
                                    "values": {
                                        "type": "array",
                                        "items": {"type": "array", "items": {}},
                                    },
                                },
                            },
                            "description": "One entry per range to write",
                        },
                    },
                    "required": ["spreadsheet_id", "data"],
                },
                query_params=["value_input_option"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.sheets.spreadsheets.create",
                method="POST",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets",
                description="Create a new spreadsheet (optional title and sheets)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title of the new spreadsheet"},
                        "sheet_titles": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Names of sheets to create within the spreadsheet",
                        },
                    },
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.sheets.spreadsheets.batch_update",
                method="POST",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}:batchUpdate",
                description="Apply one or more updates to a spreadsheet (formatting, formulas, charts, etc.)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "string"},
                        "requests": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "List of update request objects (see Sheets API batchUpdate reference)",
                        },
                    },
                    "required": ["spreadsheet_id", "requests"],
                },
                default_policy={},
                enabled_by_default=False,
            ),

            # ── Google Docs API (docs.googleapis.com) ──
            RouteDef(
                route_id="drive.docs.documents.get",
                method="GET",
                base_url="https://docs.googleapis.com",
                google_path="/v1/documents/{documentId}",
                description="Get the full content and structure of a Google Doc",
                input_schema={
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string"},
                        "suggestions_view_mode": {
                            "type": "string",
                            "description": (
                                "SUGGESTIONS_INLINE, PREVIEW_SUGGESTIONS_ACCEPTED, "
                                "or PREVIEW_WITHOUT_SUGGESTIONS"
                            ),
                        },
                    },
                    "required": ["document_id"],
                },
                query_params=["suggestions_view_mode"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.docs.documents.create",
                method="POST",
                base_url="https://docs.googleapis.com",
                google_path="/v1/documents",
                description="Create a new Google Doc with an optional title",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title for the new document"},
                    },
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.docs.documents.batch_update",
                method="POST",
                base_url="https://docs.googleapis.com",
                google_path="/v1/documents/{documentId}:batchUpdate",
                description="Apply one or more updates to a Google Doc (insert text, delete, style, etc.)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string"},
                        "requests": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Update requests (InsertTextRequest, DeleteContentRangeRequest, etc.)",
                        },
                        "write_control": {
                            "type": "object",
                            "description": "Optional concurrency control (required_revision_id / target_revision_id)",
                        },
                    },
                    "required": ["document_id", "requests"],
                },
                default_policy={},
                enabled_by_default=False,
            ),

            # ── Google Slides API (slides.googleapis.com) ──
            RouteDef(
                route_id="drive.slides.presentations.get",
                method="GET",
                base_url="https://slides.googleapis.com",
                google_path="/v1/presentations/{presentationId}",
                description="Get the full content and structure of a Google Slides presentation",
                input_schema={
                    "type": "object",
                    "properties": {
                        "presentation_id": {"type": "string"},
                    },
                    "required": ["presentation_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.slides.presentations.pages.get",
                method="GET",
                base_url="https://slides.googleapis.com",
                google_path="/v1/presentations/{presentationId}/pages/{pageObjectId}",
                description="Get a specific page (slide) from a presentation",
                input_schema={
                    "type": "object",
                    "properties": {
                        "presentation_id": {"type": "string"},
                        "page_object_id": {"type": "string"},
                    },
                    "required": ["presentation_id", "page_object_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.slides.presentations.create",
                method="POST",
                base_url="https://slides.googleapis.com",
                google_path="/v1/presentations",
                description="Create a new Google Slides presentation with an optional title",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title for the new presentation"},
                    },
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.slides.presentations.batch_update",
                method="POST",
                base_url="https://slides.googleapis.com",
                google_path="/v1/presentations/{presentationId}:batchUpdate",
                description="Apply updates to a presentation (add slides, insert text, update shapes, etc.)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "presentation_id": {"type": "string"},
                        "requests": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Update requests (CreateSlideRequest, InsertTextRequest, etc.)",
                        },
                    },
                    "required": ["presentation_id", "requests"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
```

**Route count summary (16 new):** 9 Sheets + 3 Docs + 4 Slides. Read operations (`*.get`, `*.values.get`, `*.values.batch_get`) are `enabled_by_default=True`; all writes are `enabled_by_default=False` for safety — admins must opt keys in, matching the existing Drive write-route policy.

### Change 4 — `tests/test_proxy_url_hosts.py` (new file)

See the full test file content in §3 (Test Plan) below. It proves the proxy hits the correct hostname for every new route and that the original Drive/Gmail/Calendar routes are unaffected.

### Change 5 — `tests/test_drive_workspace_routes.py` (new file)

See §3 for full content. Module-structure tests for the new routes (presence, MCP tool names, enabled-by-default behaviour, scope list).

---

## Test Plan

### Goals

1. **Prove the proxy correctly routes to the right hostname** for every new Sheets/Docs/Slides route.
2. **Prove the proxy still routes to `www.googleapis.com`** for every existing Drive/Gmail/Calendar route (no regressions).
3. **Prove the new routes have the right structural properties** (presence, scope list, MCP tool names, default-enabled behaviour).
4. **Prove no full-hostname leakage** in the URL (e.g., one route's base_url doesn't bleed into another).

### Test file 1 — `tests/test_proxy_url_hosts.py` (new)

The signature test is "given a route with a non-default `base_url`, the proxy must hit that hostname, not `www.googleapis.com`." Use the same mock-`httpx.AsyncClient` pattern already used in `tests/test_proxy.py`.

```python
"""Hostname routing tests — prove base_url override routes to the correct Google API host.

These tests use the same mocking pattern as tests/test_proxy.py — credential_manager
and httpx.AsyncClient are mocked so we can inspect the URL the proxy constructs
without hitting real Google APIs.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gatekeeper.api.proxy import GoogleProxy
from gatekeeper.models import ApiKey, RoutePolicy
from gatekeeper.modules import _loaded_modules


# --------------------------------------------------------------------------- #
# Helpers (mirror the patterns in tests/test_proxy.py)
# --------------------------------------------------------------------------- #


def _unwrap(response) -> dict:
    return json.loads(response.body.decode())


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


@pytest.fixture(autouse=True)
def clear_module_cache():
    _loaded_modules.clear()
    yield
    _loaded_modules.clear()


async def _run_proxy(
    db_session,
    module_name: str,
    route_id: str,
    method: str,
    params: dict,
):
    """Drive a single proxy call with mocked credentials/transport.

    Returns the (URL, query_params, body) sent to httpx.
    """
    policy = RoutePolicy(
        module=module_name, route=route_id, enabled=True, policy_config="{}"
    )
    db_session.add(policy)
    await db_session.commit()

    api_key = _make_api_key()
    proxy = GoogleProxy(db_session)

    with (
        patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
        patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_cm.get_credentials.return_value = _mock_creds()

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}

        mock_client = AsyncMock()
        mock_method = AsyncMock(return_value=mock_response)
        setattr(mock_client, method.lower(), mock_method)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await proxy.call_google(
            module_name=module_name,
            route_id=route_id,
            params=params,
            api_key_record=api_key,
            request_method=method,
        )

        call_args = mock_method.call_args
        url = call_args[0][0]
        # body/json may be passed positionally or by keyword depending on method
        kwargs = call_args[1] if len(call_args) > 1 else {}
        return url, kwargs.get("params", {}), kwargs.get("json")


# --------------------------------------------------------------------------- #
# Sheets hostname tests
# --------------------------------------------------------------------------- #


class TestSheetsHostname:
    @pytest.mark.asyncio
    async def test_sheets_spreadsheets_get_hits_sheets_host(self, db_session):
        url, _, _ = await _run_proxy(
            db_session, "drive", "drive.sheets.spreadsheets.get", "GET",
            {"spreadsheet_id": "ss123"},
        )
        assert url.startswith("https://sheets.googleapis.com/"), f"Got: {url}"
        assert "/v4/spreadsheets/ss123" in url
        # Critical: must NOT hit www.googleapis.com
        assert "www.googleapis.com" not in url

    @pytest.mark.asyncio
    async def test_sheets_values_get_hits_sheets_host(self, db_session):
        url, params, _ = await _run_proxy(
            db_session, "drive", "drive.sheets.values.get", "GET",
            {"spreadsheet_id": "ss1", "range": "A1:B2"},
        )
        assert url.startswith("https://sheets.googleapis.com/"), f"Got: {url}"
        assert "/v4/spreadsheets/ss1/values/A1:B2" in url
        assert "www.googleapis.com" not in url
        # Range param must NOT appear in the URL (it's in the path)
        assert "range" not in params or "A1:B2" in url

    @pytest.mark.asyncio
    async def test_sheets_values_update_hits_sheets_host(self, db_session):
        url, _, json_body = await _run_proxy(
            db_session, "drive", "drive.sheets.values.update", "PUT",
            {"spreadsheet_id": "ss1", "range": "A1:B2", "values": [["a", 1]]},
        )
        assert url.startswith("https://sheets.googleapis.com/"), f"Got: {url}"
        assert "/v4/spreadsheets/ss1/values/A1:B2" in url
        # valueInputOption must be in the query string, not the body
        assert json_body is None or "valueInputOption" not in json_body

    @pytest.mark.asyncio
    async def test_sheets_batch_get_passes_ranges_as_query(self, db_session):
        url, params, _ = await _run_proxy(
            db_session, "drive", "drive.sheets.values.batch_get", "GET",
            {"spreadsheet_id": "ss1", "ranges": ["A1:B2", "C3:D4"]},
        )
        assert url.startswith("https://sheets.googleapis.com/")
        assert "ranges=" in url or "ranges" in params


# --------------------------------------------------------------------------- #
# Docs hostname tests
# --------------------------------------------------------------------------- #


class TestDocsHostname:
    @pytest.mark.asyncio
    async def test_docs_documents_get_hits_docs_host(self, db_session):
        url, _, _ = await _run_proxy(
            db_session, "drive", "drive.docs.documents.get", "GET",
            {"document_id": "doc123"},
        )
        assert url.startswith("https://docs.googleapis.com/"), f"Got: {url}"
        assert "/v1/documents/doc123" in url
        assert "www.googleapis.com" not in url

    @pytest.mark.asyncio
    async def test_docs_documents_batch_update_hits_docs_host(self, db_session):
        url, _, json_body = await _run_proxy(
            db_session, "drive", "drive.docs.documents.batch_update", "POST",
            {"document_id": "doc1", "requests": [{"insertText": {"text": "hi"}}]},
        )
        assert url.startswith("https://docs.googleapis.com/")
        assert "/v1/documents/doc1:batchUpdate" in url
        assert json_body and "requests" in json_body


# --------------------------------------------------------------------------- #
# Slides hostname tests
# --------------------------------------------------------------------------- #


class TestSlidesHostname:
    @pytest.mark.asyncio
    async def test_slides_presentations_get_hits_slides_host(self, db_session):
        url, _, _ = await _run_proxy(
            db_session, "drive", "drive.slides.presentations.get", "GET",
            {"presentation_id": "pres123"},
        )
        assert url.startswith("https://slides.googleapis.com/"), f"Got: {url}"
        assert "/v1/presentations/pres123" in url
        assert "www.googleapis.com" not in url

    @pytest.mark.asyncio
    async def test_slides_pages_get_substitutes_both_params(self, db_session):
        url, _, _ = await _run_proxy(
            db_session, "drive", "drive.slides.presentations.pages.get", "GET",
            {"presentation_id": "pres1", "page_object_id": "slide_42"},
        )
        assert url.startswith("https://slides.googleapis.com/")
        assert "/v1/presentations/pres1/pages/slide_42" in url
        assert "www.googleapis.com" not in url


# --------------------------------------------------------------------------- #
# Regression: existing routes still hit www.googleapis.com
# --------------------------------------------------------------------------- #


class TestExistingRoutesUnchanged:
    """Pre-existing Drive/Gmail/Calendar routes must still hit www.googleapis.com."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("module_name,route_id,params", [
        ("drive", "drive.files.list", {}),
        ("drive", "drive.files.get", {"file_id": "f1"}),
        ("drive", "drive.permissions.list", {"file_id": "f1"}),
        ("gmail", "gmail.messages.list", {}),
        ("gmail", "gmail.messages.get", {"message_id": "m1"}),
        ("calendar", "calendar.events.list", {}),
        ("calendar", "calendar.events.get", {"event_id": "e1"}),
    ])
    async def test_legacy_routes_use_www_googleapis_com(
        self, db_session, module_name, route_id, params
    ):
        url, _, _ = await _run_proxy(
            db_session, module_name, route_id, "GET", params,
        )
        assert url.startswith("https://www.googleapis.com/"), (
            f"{route_id} should still hit www.googleapis.com, got: {url}"
        )
        # No new route's hostname should leak into a legacy route
        for host in ("sheets.googleapis.com", "docs.googleapis.com", "slides.googleapis.com"):
            assert host not in url, (
                f"{route_id} leaked host {host} (got: {url})"
            )
```

**Run:** `python -m pytest tests/test_proxy_url_hosts.py -v`

### Test file 2 — `tests/test_drive_workspace_routes.py` (new)

Module-structure tests. Smaller, no mocking needed. Validates presence, MCP tool naming, default-enabled behaviour, and the expanded scope list.

```python
"""Structural tests for the Sheets, Docs, and Slides routes added to the Drive module."""


from gatekeeper.modules.drive import DriveModule


# ── Sheets ──

def test_sheets_routes_present():
    ids = {r.route_id for r in DriveModule().get_routes()}
    expected = [
        "drive.sheets.spreadsheets.get",
        "drive.sheets.values.get",
        "drive.sheets.values.batch_get",
        "drive.sheets.values.update",
        "drive.sheets.values.append",
        "drive.sheets.values.clear",
        "drive.sheets.values.batch_update",
        "drive.sheets.spreadsheets.create",
        "drive.sheets.spreadsheets.batch_update",
    ]
    for rid in expected:
        assert rid in ids, f"Missing Sheets route: {rid}"


def test_sheets_routes_have_correct_base_url():
    """Every Sheets route must target sheets.googleapis.com."""
    routes = [r for r in DriveModule().get_routes() if r.route_id.startswith("drive.sheets.")]
    assert len(routes) == 9, f"Expected 9 sheets routes, found {len(routes)}"
    for r in routes:
        assert r.base_url == "https://sheets.googleapis.com", (
            f"{r.route_id} has base_url={r.base_url!r}"
        )


def test_sheets_mcp_tool_names():
    tools = {t["name"] for t in DriveModule().get_mcp_tools()}
    for name in (
        "drive__sheets_spreadsheets_get",
        "drive__sheets_values_get",
        "drive__sheets_values_update",
        "drive__sheets_values_append",
        "drive__sheets_values_clear",
        "drive__sheets_values_batch_get",
        "drive__sheets_values_batch_update",
        "drive__sheets_spreadsheets_create",
        "drive__sheets_spreadsheets_batch_update",
    ):
        assert name in tools, f"Missing MCP tool: {name}"


def test_sheets_read_enabled_by_default():
    routes = {r.route_id: r for r in DriveModule().get_routes()}
    for rid in ("drive.sheets.spreadsheets.get",
                "drive.sheets.values.get",
                "drive.sheets.values.batch_get"):
        assert routes[rid].enabled_by_default is True, f"{rid} should be on by default"


def test_sheets_write_disabled_by_default():
    routes = {r.route_id: r for r in DriveModule().get_routes()}
    for rid in ("drive.sheets.values.update",
                "drive.sheets.values.append",
                "drive.sheets.values.clear",
                "drive.sheets.spreadsheets.create",
                "drive.sheets.spreadsheets.batch_update"):
        assert routes[rid].enabled_by_default is False, f"{rid} should be off by default"


# ── Docs ──

def test_docs_routes_present():
    ids = {r.route_id for r in DriveModule().get_routes()}
    for rid in ("drive.docs.documents.get",
                "drive.docs.documents.create",
                "drive.docs.documents.batch_update"):
        assert rid in ids, f"Missing Docs route: {rid}"


def test_docs_routes_have_correct_base_url():
    routes = [r for r in DriveModule().get_routes() if r.route_id.startswith("drive.docs.")]
    assert len(routes) == 3
    for r in routes:
        assert r.base_url == "https://docs.googleapis.com", (
            f"{r.route_id} has base_url={r.base_url!r}"
        )


def test_docs_read_enabled_docs_write_disabled():
    routes = {r.route_id: r for r in DriveModule().get_routes()}
    assert routes["drive.docs.documents.get"].enabled_by_default is True
    assert routes["drive.docs.documents.create"].enabled_by_default is False
    assert routes["drive.docs.documents.batch_update"].enabled_by_default is False


# ── Slides ──

def test_slides_routes_present():
    ids = {r.route_id for r in DriveModule().get_routes()}
    for rid in ("drive.slides.presentations.get",
                "drive.slides.presentations.pages.get",
                "drive.slides.presentations.create",
                "drive.slides.presentations.batch_update"):
        assert rid in ids, f"Missing Slides route: {rid}"


def test_slides_routes_have_correct_base_url():
    routes = [r for r in DriveModule().get_routes() if r.route_id.startswith("drive.slides.")]
    assert len(routes) == 4
    for r in routes:
        assert r.base_url == "https://slides.googleapis.com", (
            f"{r.route_id} has base_url={r.base_url!r}"
        )


def test_slides_read_enabled_slides_write_disabled():
    routes = {r.route_id: r for r in DriveModule().get_routes()}
    assert routes["drive.slides.presentations.get"].enabled_by_default is True
    assert routes["drive.slides.presentations.pages.get"].enabled_by_default is True
    assert routes["drive.slides.presentations.create"].enabled_by_default is False
    assert routes["drive.slides.presentations.batch_update"].enabled_by_default is False


# ── Scopes ──

def test_drive_module_has_all_four_scopes():
    scopes = DriveModule().required_scopes
    for required in (
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/presentations",
    ):
        assert required in scopes, f"Missing scope: {required}"


# ── Cross-cutting ──

def test_no_route_uses_global_base_for_new_routes():
    """Defensive: confirm the new routes do NOT inherit GOOGLE_API_BASE via accident."""
    bad = [
        r for r in DriveModule().get_routes()
        if r.route_id.startswith(("drive.sheets.", "drive.docs.", "drive.slides."))
        and r.base_url is None
    ]
    assert bad == [], f"New routes missing base_url: {[r.route_id for r in bad]}"


def test_existing_drive_routes_have_no_base_url():
    """Pre-existing Drive routes should NOT have base_url set (they use the default)."""
    for r in DriveModule().get_routes():
        if r.route_id.startswith("drive.files.") or r.route_id.startswith("drive.permissions."):
            assert r.base_url is None, (
                f"Existing route {r.route_id} unexpectedly has base_url={r.base_url!r}"
            )
```

**Run:** `python -m pytest tests/test_drive_workspace_routes.py -v`

### Test file 3 — `tests/test_all_routes_url_construction.py` (existing)

This file already iterates over every route in every enabled module and verifies that the proxy builds a valid URL. It does NOT assert on hostname — it just checks that no `{placeholder}` survives. **After Change 2, this test must still pass for every existing and new route** because (a) every new route's `google_path` is well-formed, (b) `base_url` defaults to `None` for legacy routes, and (c) the new `base = route.base_url or GOOGLE_API_BASE` line preserves behavior for `None`.

**No change to this test file is required.** Run the full suite after Changes 1-5 are applied to confirm.

### Test plan summary

| Test | Type | What it proves |
|---|---|---|
| `test_proxy_url_hosts.py::TestSheetsHostname::*` | hostname | Each Sheets route hits `sheets.googleapis.com`, never `www.googleapis.com` |
| `test_proxy_url_hosts.py::TestDocsHostname::*` | hostname | Each Docs route hits `docs.googleapis.com` |
| `test_proxy_url_hosts.py::TestSlidesHostname::*` | hostname | Each Slides route hits `slides.googleapis.com` |
| `test_proxy_url_hosts.py::TestExistingRoutesUnchanged::*` | regression | Legacy Drive/Gmail/Calendar routes still hit `www.googleapis.com` and never leak the new hosts |
| `test_drive_workspace_routes.py::*` | structural | Route presence, `base_url` correctness, MCP tool names, default-enabled flags, scope list |
| `tests/test_all_routes_url_construction.py` (unchanged) | regression | No `{placeholder}` survives in any URL after the proxy change |

**Final verification command:**

```bash
python -m pytest tests/ -v
```

Expected: all existing tests pass + 2 new files pass with 30+ new test cases.

---

## Task Breakdown

Each task is sized 15-45 minutes. Sequential ordering reflects file-edit dependencies.

| # | Task | Assignee | Depends On | Acceptance Criteria |
|---|------|----------|------------|---------------------|
| 1 | Add `base_url: str \| None = None` field to `RouteDef` in `gatekeeper/modules/route.py` | implementer | — | Field present; existing tests still pass; `RouteDef(...).base_url` returns `None` by default |
| 2 | Update `call_google()` in `gatekeeper/api/proxy.py` to use `route.base_url or GOOGLE_API_BASE` | implementer | #1 | `www.googleapis.com` still used for all legacy routes (verified by `test_proxy.py` + `test_all_routes_url_construction.py`); no behaviour change for routes without `base_url` |
| 3 | Add `test_proxy_url_hosts.py` (new) with the 4 test classes above | implementer | #1, #2 | Test file exists; the 4 hostname test classes pass against the (still-empty) Drive module *if we only add the test now* — actually defer until #4 |
| 4 | Expand `DriveModule.required_scopes` and append 16 new `RouteDef` entries to `gatekeeper/modules/drive/__init__.py`, each with the correct `base_url` | implementer | #1, #2 | 16 new routes present; all 9 Sheets routes have `base_url="https://sheets.googleapis.com"`, all 3 Docs routes have `base_url="https://docs.googleapis.com"`, all 4 Slides routes have `base_url="https://slides.googleapis.com"`; `required_scopes` contains all 4 scopes |
| 5 | Add `tests/test_drive_workspace_routes.py` (new) with the structural tests | implementer | #4 | All tests in the new file pass; `test_sheets_routes_have_correct_base_url` and equivalents for Docs/Slides are green |
| 6 | Run `test_proxy_url_hosts.py` — fix any leaks between hosts | implementer | #4 | All hostname tests pass; `TestExistingRoutesUnchanged::test_legacy_routes_use_www_googleapis_com` is green for every legacy route parametrised |
| 7 | Run full test suite — no regressions | implementer | #1-#6 | `python -m pytest tests/ -v` exits 0; existing 80+ tests still pass |

**Parallelisation:** Tasks 1, 2 must be sequential. Tasks 3 and 5 can run in parallel (different files, no overlap). Task 4 depends on 1+2. Task 6 depends on 3+4. Task 7 is the gate.

---

## Task Specification (per task)

## Task 1: Add `base_url` field to `RouteDef`

### Objective
Extend the Pydantic model to carry an optional per-route base URL.

### Files to Modify
- `gatekeeper/modules/route.py` — add one field after `enabled_by_default` (line 39).

### Acceptance Criteria
- [ ] Field `base_url: str | None = None` is present in the `RouteDef` class.
- [ ] `RouteDef(route_id="x", google_path="/y")` instantiates with `route.base_url is None`.
- [ ] `RouteDef(route_id="x", google_path="/y", base_url="https://sheets.googleapis.com")` works.
- [ ] `python -m pytest tests/test_modules.py tests/test_proxy.py -v` exits 0 (no regressions).

### Deliverable Location
- Commit: `feat(route): add optional base_url field to RouteDef for multi-host API support`

## Task 2: Update `call_google()` to honour `route.base_url`

### Objective
Make the proxy URL construction prefer the per-route base URL.

### Files to Modify
- `gatekeeper/api/proxy.py` — replace the 8-line block at lines 196-202 with the 11-line block shown in Change 2.

### Acceptance Criteria
- [ ] Code change matches Change 2 above verbatim.
- [ ] `route.base_url or GOOGLE_API_BASE` is used to pick the host.
- [ ] `python -m pytest tests/test_proxy.py tests/test_all_routes_url_construction.py -v` exits 0.
- [ ] `python -m pytest tests/test_modules.py -v` exits 0.

### Deliverable Location
- Commit: `feat(proxy): route requests to per-route base_url when set`

## Task 3: Add hostname-routing test file

### Objective
Prove the proxy hits the correct Google API host for every new route and the legacy host for legacy routes.

### Files to Create
- `tests/test_proxy_url_hosts.py` — content from §3 Test file 1.

### Acceptance Criteria
- [ ] File is created at the path above with the full content from the spec.
- [ ] `python -m pytest tests/test_proxy_url_hosts.py -v` runs (will fail until Task 4 lands; that's expected).
- [ ] Pytest discovery picks up the file (no import errors).

### Deliverable Location
- Commit: `test(proxy): add hostname-routing tests for Sheets/Docs/Slides + regression for legacy`

## Task 4: Add 16 new routes to `DriveModule`

### Objective
Add Sheets/Docs/Slides routes with the correct `base_url` per route.

### Files to Modify
- `gatekeeper/modules/drive/__init__.py`:
  - Replace the class header (lines 9-15) with the new 4-scope version.
  - Insert the 16 new `RouteDef` entries from Change 3b immediately before line 1150's `]`.

### Acceptance Criteria
- [ ] `DriveModule().required_scopes` is a list of 4 URLs in this order: `drive`, `spreadsheets`, `documents`, `presentations`.
- [ ] Exactly 9 routes with `route_id` starting with `drive.sheets.` exist; each has `base_url == "https://sheets.googleapis.com"`.
- [ ] Exactly 3 routes with `route_id` starting with `drive.docs.` exist; each has `base_url == "https://docs.googleapis.com"`.
- [ ] Exactly 4 routes with `route_id` starting with `drive.slides.` exist; each has `base_url == "https://slides.googleapis.com"`.
- [ ] Read routes (`*.get`, `*.values.get`, `*.values.batch_get`) have `enabled_by_default=True`; all POST/PUT/PATCH/DELETE write routes have `enabled_by_default=False`.
- [ ] `python -c "from gatekeeper.modules.drive import DriveModule; m=DriveModule(); print(sum(1 for r in m.get_routes() if r.route_id.startswith('drive.sheets.') or r.route_id.startswith('drive.docs.') or r.route_id.startswith('drive.slides.')))"` prints `16`.

### Deliverable Location
- Commit: `feat(drive): add Sheets, Docs, and Slides API routes with per-route base_url`

## Task 5: Add structural test file

### Objective
Prove the new routes exist and have the correct shape.

### Files to Create
- `tests/test_drive_workspace_routes.py` — content from §3 Test file 2.

### Acceptance Criteria
- [ ] File is created at the path above.
- [ ] `python -m pytest tests/test_drive_workspace_routes.py -v` exits 0 with all 13 tests green.
- [ ] The cross-cutting test `test_no_route_uses_global_base_for_new_routes` is green.
- [ ] The regression test `test_existing_drive_routes_have_no_base_url` is green.

### Deliverable Location
- Commit: `test(drive): add structural tests for Sheets/Docs/Slides routes`

## Task 6: Run the hostname test suite

### Objective
Verify the full hostname-routing story end-to-end.

### Acceptance Criteria
- [ ] `python -m pytest tests/test_proxy_url_hosts.py -v` exits 0 — all 4 test classes green.
- [ ] `TestExistingRoutesUnchanged::test_legacy_routes_use_www_googleapis_com` is green for all 7 parametrised legacy routes.
- [ ] No test shows a hostname leak between routes (e.g., a Sheets route ending up on `docs.googleapis.com`).

## Task 7: Full test suite regression

### Objective
Confirm no other tests break.

### Acceptance Criteria
- [ ] `python -m pytest tests/ -v` exits 0.
- [ ] No previously-passing test now fails.
- [ ] No skipped tests in the new files.

---

## Risks, Constraints, and Things Lens Must Verify

### Risks

1. **`base_url` schema serialization.** Pydantic v2 serializes `None` as `null` in JSON. If any persistence path stores `RouteDef` and round-trips through JSON Schema, the `None` should round-trip correctly. Lens should grep for `RouteDef` references in admin/UI code (e.g., `gatekeeper/admin/routes.py`) and confirm no `dumps(... exclude_none=True)` would silently drop the field. **Current code shows no such persistence — routes are constructed in-memory only — but this is worth a sanity check.**

2. **The Sheets `values.update` body shape.** The Sheets API expects the body to be a `ValueRange`: `{ "range": "...", "values": [[...]] }`. After the proxy substitutes `{range}` and `{spreadsheetId}` into the path, it currently would forward `{"range": "A1:B2", "values": [[...]]}` as the body. The `range` would be duplicated (in path *and* body). The Sheets API tolerates this (it ignores body.range), so it's safe today, but it's an open question whether we should strip the path param from the body. **Lens should verify by reading the Sheets API docs / running a live test, and call out any tightening needed as a follow-up task.** This is intentionally NOT a blocker for this spec — the hostname fix is the gate.

3. **The Sheets `spreadsheets.create` body shape.** The API expects `{ "properties": { "title": "..." }, "sheets": [...] }`. Our schema passes `{"title": "...", "sheet_titles": [...]}` as the body, which is **wrong** — Google's API will reject it. This is a known body-transformation gap. **Recommended approach: leave it as a known limitation in the v1 spec, and add a follow-up task in the root task to introduce a `body_transform` hook on `RouteDef` (like the existing `_restructure_filter_body` pattern for Gmail).** For now, mark `enabled_by_default=False` (which the spec already does) so the broken route is opt-in only.

4. **Auth scope re-consent.** Adding 3 new scopes means Chris must re-run `gatekeeper auth`. This is a post-deploy step that does **not** block this spec but is called out in the post-implementation notes for Chris.

5. **Drive-write vs Sheets-write scope split.** The Drive scope gives us read/write on Drive files, but to read/write *structured Sheets content* we need the Sheets scope. Both are now in `required_scopes`, so OAuth consent will request both. Users who only want Drive file operations will see a consent screen that asks for Sheets/Docs/Slides — this is a UX cost of consolidating into the Drive module. **Lens should confirm this is acceptable.** If not, the alternative is to split into separate `SheetsModule`/`DocsModule`/`SlidesModule` classes (cleaner separation, more work, covered in the parent research brief).

6. **No changes to `MODULE_API_MAP`.** This spec does NOT modify the `MODULE_API_MAP` constant in `proxy.py`. It remains a per-module *path-prefix* map. The `base_url` field is the per-route *hostname* override. The two are orthogonal. **Lens should confirm this is intentional and call out any future cleanup that wants to migrate `MODULE_API_MAP` to a per-module base-URL default (the parent research's alternative approach).**

### Constraints

- **No new third-party deps.** Confirmed.
- **No DB migrations.** `RouteDef` is not persisted; routes are constructed in-memory at module load.
- **Backwards-compatible.** `base_url: str | None = None` defaults to `None`; the proxy change is a one-line addition to the existing block, not a restructure.
- **Python 3.12 / Pydantic v2 syntax.** Use `str | None`, not `Optional[str]`. Confirmed by the existing modules.

### Assumptions Lens Must Verify

- **A1:** Every new route's `google_path` matches the canonical Sheets/Docs/Slides REST path **after** base URL prefixing. Lens should spot-check 2-3 routes against Google's API docs.
- **A2:** `query_params` lists for Sheets routes (especially `value_input_option`, `insert_data_option`, `ranges`) match what the Google API actually accepts as query parameters. The proxy already strips these from the JSON body and appends them as query string params.
- **A3:** The `enabled_by_default` flags match the root task's intent (read on, write off) — confirmed by the spec.
- **A4:** No code path elsewhere in `gatekeeper/` constructs Google API URLs by hand (e.g., `google_client.py` or `service.py`). **Lens should grep for `googleapis.com` and confirm the only URL construction site is `call_google()`.**
- **A5:** The `test_proxy.py` mock pattern (mocking `credential_manager` + `httpx.AsyncClient`) is reusable for the new test file — confirmed by reading the existing file.
- **A6:** The tests in `tests/test_all_routes_url_construction.py` will continue to pass after Change 2 — it only checks that no `{placeholder}` survives, which is unaffected by the new `base` variable.

---

## Post-Implementation: What Chris Needs to Do (NOT the Fleet)

These steps are for Chris after the code is merged. **The Fleet must NOT perform these operations:**

1. **Re-authenticate Google OAuth** — the current token only has the `drive` scope. The new `spreadsheets`, `documents`, and `presentations` scopes require a new consent. Since all scopes are now on the Drive module (which is already enabled), just re-auth:
   ```bash
   gatekeeper auth
   ```
   Google will prompt to approve the three new scopes in addition to the existing Drive scope.

2. **Restart Gatekeeper** on Mario (the Pi).

3. **Smoke-test from Buster** — after restarting, exercise one read route per API:
   ```bash
   hermes mcp call gatekeeper drive__sheets_spreadsheets_get '{"spreadsheet_id":"<test>"}'
   hermes mcp call gatekeeper drive__docs_documents_get '{"document_id":"<test>"}'
   hermes mcp call gatekeeper drive__slides_presentations_get '{"presentation_id":"<test>"}'
   ```
   The total MCP tool count should increase from 81 to 97 (16 new tools: 9 sheets + 3 docs + 4 slides).

4. **Enable write routes in admin** — Sheets/Docs/Slides write routes are disabled by default. Use the Gatekeeper admin panel to enable write operations for API keys that need them.

5. **Known body-shape gaps (follow-up tickets, not blockers):**
   - `drive.sheets.spreadsheets.create` — body is flat `{title, sheet_titles}`; Sheets API expects `{properties: {title}, sheets: [...]}`. Either document a manual JSON body workaround for now, or open a follow-up to add a `body_transform` hook to `RouteDef`.
   - `drive.sheets.values.update` — body includes the `range` even though it's in the path. Sheets API tolerates this, but it's redundant.

---

## Summary of Changes

| File | Change | LOC impact |
|---|---|---|
| `gatekeeper/modules/route.py` | Modified — add `base_url: str \| None = None` field | +6 |
| `gatekeeper/api/proxy.py` | Modified — use `route.base_url or GOOGLE_API_BASE` in URL construction | +3, -1 |
| `gatekeeper/modules/drive/__init__.py` | Modified — expand `required_scopes` (3 new), append 16 new `RouteDef` entries | +1, +440 |
| `tests/test_proxy_url_hosts.py` | **New** — 4 hostname test classes covering Sheets/Docs/Slides + regression | +180 |
| `tests/test_drive_workspace_routes.py` | **New** — 13 structural tests for the new routes | +130 |

**Total new MCP tools:** 16, bringing the Drive module from ~50 tools to ~66, and the total Gatekeeper tool count from 81 to 97.

**New MCP tool names (all under `drive__` namespace):**

| Tool Name | API | Operation | Default-enabled |
|---|---|---|---|
| `drive__sheets_spreadsheets_get` | Sheets | Get spreadsheet metadata | ✓ |
| `drive__sheets_values_get` | Sheets | Read cell range | ✓ |
| `drive__sheets_values_batch_get` | Sheets | Read multiple ranges | ✓ |
| `drive__sheets_values_update` | Sheets | Write cell range | ✗ |
| `drive__sheets_values_append` | Sheets | Append rows | ✗ |
| `drive__sheets_values_clear` | Sheets | Clear cell range | ✗ |
| `drive__sheets_values_batch_update` | Sheets | Update multiple ranges | ✗ |
| `drive__sheets_spreadsheets_create` | Sheets | Create spreadsheet | ✗ |
| `drive__sheets_spreadsheets_batch_update` | Sheets | Apply formatting/structural updates | ✗ |
| `drive__docs_documents_get` | Docs | Get document content | ✓ |
| `drive__docs_documents_create` | Docs | Create document | ✗ |
| `drive__docs_documents_batch_update` | Docs | Insert/edit text, formatting | ✗ |
| `drive__slides_presentations_get` | Slides | Get presentation content | ✓ |
| `drive__slides_presentations_pages_get` | Slides | Get specific slide | ✓ |
| `drive__slides_presentations_create` | Slides | Create presentation | ✗ |
| `drive__slides_presentations_batch_update` | Slides | Add slides, insert text | ✗ |
