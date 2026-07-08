# Spec: Gatekeeper MCP Header Authentication (X-Gatekeeper-API-Key)

**Spec ID:** mcp-header-auth
**Created:** 2026-07-08
**Author:** Cartographer
**Source Research:** `docs/research/header-auth-tool-calls-research.md` (28 claims validated)
**Parent Task:** t_a50e102c
**Downstream Task:** t_b26fcc46607e (Nova → implementation)
**Status:** Design complete, awaiting Lens review

---

## 0. Overview

Gatekeeper currently requires every MCP tool call to include `api_key` as a **required** argument in the tool's JSON schema. This is inconsistent with the REST API (which uses the `X-Gatekeeper-API-Key` HTTP header), leaks the raw API key into the LLM's context window on every tool call, and forces every tool schema to carry an auth field.

This spec moves MCP tool-call authentication onto the `X-Gatekeeper-API-Key` HTTP header (header is primary; the `api_key` argument is kept as an optional fallback for clients that cannot send custom headers). The MCP SDK's `request_ctx` ContextVar carries the Starlette `Request` from the SSE/StreamableHTTP POST into the tool handler, so the header can be read there without any SDK modification.

**Validated approach (Option A1 from research):**
1. In `call_tool`, attempt to read `X-Gatekeeper-API-Key` from `request_ctx.get().request.headers`.
2. If absent, fall back to `arguments.pop("api_key", None)`.
3. If still absent, return the existing 401 error.
4. **Always** pop `api_key` from `arguments` (whether header or arg was used) so the key never reaches the proxy.
5. Make `api_key` optional in the tool schema (remove from `required`, keep in `properties`, update description).
6. Update the MCP `instructions` string to document the header-auth preference.
7. Add 12 test scenarios (see §5) that cover both transport paths, all auth combinations, CORS, `LookupError` resilience, and backward compatibility.

**Scope:** Python code change in `gatekeeper/mcp_server/__init__.py` (≈3 small regions), one new test file, and doc updates. No SDK modification, no schema migration, no DB change, no deployment change. CORS already permits the header (line 155 of `gatekeeper/main.py`).

**Non-goals:** Switching to the MCP SDK's OAuth/Bearer auth (Option B from research — heavier, recommended only as a future enhancement once A1 ships).

---

## 1. Architecture & Data Flow

### 1.1 Components Touched

| File | Change |
|---|---|
| `gatekeeper/mcp_server/__init__.py` | Import `request_ctx`; update schema in `list_tools`; rewrite auth flow in `call_tool`; update `instructions` string. |
| `tests/test_mcp_auth.py` (NEW) | 12 scenarios from research §5; uses existing `app`/`client`/`api_key` fixtures from `tests/conftest.py`. |
| `docs/MCP_SETUP_AGENT.md` | Add a short section explaining header auth is preferred; the `api_key` argument is fallback. |
| `docs/MCP_SETUP_HUMAN.md` | Mention header auth in the MCP client configuration examples. |
| `CHANGELOG.md` | One-line entry under the next version. |

No changes to: `gatekeeper/main.py` (CORS already correct), `gatekeeper/auth.py` (REST path is unchanged), any module under `gatekeeper/modules/`, the proxy, the DB models, or the policy engine.

### 1.2 Data Flow (before → after)

**Before (current):**

```
agent (LLM)            MCP client                  Gatekeeper                     Google API
─────────────         ──────────────              ──────────────                  ───────────
tool call(args)  →  JSON-RPC with api_key    →   POST /mcp/messages/             → (proxy)
                       in arguments                call_tool(name, args)
                                                  args.pop("api_key")
                                                  _resolve_api_key(raw)
                                                  call_google(...)
```

**After (this spec):**

```
agent (LLM)            MCP client                  Gatekeeper                     Google API
─────────────         ──────────────              ──────────────                  ───────────
tool call(args)  →  JSON-RPC POST with        →   POST /mcp/messages/
                       X-Gatekeeper-API-Key         request_ctx populated
                       header (and optionally        with Starlette Request
                       api_key arg)                  call_tool(name, args)
                                                  1. header = ctx.request.headers.get("X-Gatekeeper-API-Key")
                                                  2. if not header: header = args.pop("api_key", None)
                                                  3. args.pop("api_key", None)  # always
                                                  4. _resolve_api_key(header)
                                                  5. call_google(...)
```

### 1.3 Transport Coverage

The change works for **both** transports the MCP SDK supports:

- **SSE** — `mcp/server/sse.py:269` calls `ServerMessageMetadata(request_context=request)` where `request` is the Starlette `Request` from `handle_post_message`. Verified by research claim #8.
- **Streamable HTTP** — `mcp/server/streamable_http.py:268-274, 543, 566` carry the same `request_context=request`. Verified by research claim #23.

The same `request_ctx` ContextVar is set by the low-level server before the handler runs (lines 759-775 of `mcp/server/lowlevel/server.py`) and reset after (line 798). Gatekeeper registers its handler via `@mcp._mcp_server.call_tool(validate_input=False)`, so the handler runs inside that context.

### 1.4 Why This Is Safe

| Risk | Mitigation |
|---|---|
| `request_ctx` is a public SDK API that could change | It is a module-level `ContextVar` declared at line 109 of `mcp/server/lowlevel/server.py`. The research notes it is "stable API" and the package version is `mcp>=1.0`. We still wrap the lookup in `try/except LookupError` so the code degrades gracefully if the SDK is ever downgraded. |
| `RequestContext.request` can be `None` | The dataclass field is typed `RequestT \| None` (`mcp/shared/context.py:30`). We check `if ctx.request is not None` before reading headers. |
| Tool call invoked outside an HTTP context (e.g. stdio) | `request_ctx.get()` raises `LookupError`. We catch and fall back to the `api_key` argument. Verified by research scenario #12. |
| CORS not applied to the mounted sub-app | FastAPI mounts inherit parent middleware; `X-Gatekeeper-API-Key` is already in `allow_headers` (`gatekeeper/main.py:155`). Verified by research scenario #11 (still included as an explicit test). |
| Concurrent requests share state | `request_ctx` is a `ContextVar`; each asyncio task gets its own copy. No cross-request contamination is possible. |
| Backward compatibility broken | Old clients that pass `api_key` as an argument continue to work — the argument path is the explicit fallback. Existing `TestMCPToolSchema` tests pass through unchanged. |

---

## 2. Interface Definitions

### 2.1 New Behavior in `call_tool`

```python
# gatekeeper/mcp_server/__init__.py  (pseudo-diff, see §3 for exact edits)

from mcp.server.lowlevel.server import request_ctx  # NEW import

@mcp._mcp_server.call_tool(validate_input=False)
async def call_tool(name: str, arguments: dict[str, Any]) -> list:
    import mcp.types as types
    from gatekeeper.api.proxy import GoogleProxy
    from gatekeeper.modules import load_module

    # ---- AUTH: header first, argument fallback, always pop ----
    api_key: str | None = None
    try:
        ctx = request_ctx.get()
        if ctx is not None and ctx.request is not None:
            api_key = ctx.request.headers.get("X-Gatekeeper-API-Key") or None
    except LookupError:
        pass  # No request context (e.g. stdio transport)

    # Always pop api_key from arguments so it never reaches the proxy
    arg_api_key = arguments.pop("api_key", None)
    if not api_key:
        api_key = arg_api_key

    if not api_key:
        return [_err(401, "API key required (set X-Gatekeeper-API-Key header or pass api_key argument)")]

    key_record = await _resolve_api_key(api_key)
    if not key_record:
        return [_err(401, "Invalid API key")]

    # ... rest of call_tool unchanged: parse module/route, call_google, format response
```

### 2.2 Updated Schema in `list_tools`

The `api_key` property stays in `properties` but is removed from `required`. Description is updated.

```python
props["api_key"] = {
    "type": "string",
    "description": (
        "Gatekeeper API key. Optional when the X-Gatekeeper-API-Key HTTP header "
        "is set on the request; otherwise required for authentication."
    ),
}
required = list(schema.get("required", []))
# NOTE: previously `required.append("api_key")` is REMOVED
```

### 2.3 Updated `instructions` String

```python
instructions=(
    "Gatekeeper MCP server — a policy gateway for Google Workspace APIs "
    "(Drive, Gmail, Calendar). Each tool proxies a single Google API route "
    "through the policy engine. Authentication is via the X-Gatekeeper-API-Key "
    "HTTP header on the POST /mcp/messages/ request. As a fallback for clients "
    "that cannot send custom headers, an api_key argument is also accepted, "
    "but header auth is preferred because it keeps the key out of the LLM "
    "context. Available tools depend on which routes are enabled by the "
    "administrator — call list_tools to see what's currently available. Do not "
    "assume any route is enabled or disabled; if a tool call returns a 403 "
    "error, that route is disabled and only the administrator can enable it. "
    "You cannot bypass disabled routes, modify policies, or access admin "
    "settings."
),
```

### 2.4 Error-Response Helper (extracted, optional refactor)

The current code inlines two nearly-identical `TextContent` 401 error blocks. Extract a tiny helper to keep the auth path tight and testable. The helper lives in the same file and is private:

```python
def _auth_error(status: int, message: str) -> list:
    """Build a TextContent error response for an auth failure."""
    import mcp.types as types
    return [types.TextContent(type="text", text=json.dumps(
        {"error": True, "status": status, "message": message}
    ))]
```

This is a minor cleanup, not a behavior change. The implementer may inline the response construction instead if they prefer to keep the diff minimal.

---

## 3. File-by-File Change List

### 3.1 `gatekeeper/mcp_server/__init__.py`

**Edit 1 — module-level import (around line 9-14).**
Add `from mcp.server.lowlevel.server import request_ctx` to the imports. Place it next to other `mcp.*` imports.

**Edit 2 — `instructions` string (lines 104-113).**
Replace the existing `instructions=` block with the updated text in §2.3.

**Edit 3 — `list_tools` schema injection (lines 146-151).**
- Update the `api_key` description to the text in §2.2.
- Remove the `required.append("api_key")` line so `api_key` is no longer in the required list.
- Keep `props["api_key"]` so clients that want to pass it can still see the parameter in the schema.

**Edit 4 — `call_tool` auth flow (lines 187-210).**
Replace the existing `arguments.pop("api_key", None)` + key-presence check + `_resolve_api_key` block with the header-first logic from §2.1. The rest of `call_tool` (module/route parsing, `proxy.call_google`, response formatting) is unchanged.

**Edit 5 — error helper (optional).**
If the implementer chooses to extract `_auth_error` (see §2.4), add it as a module-level private function above `create_mcp_server`. Both call sites in `call_tool` (no key, invalid key) call this helper.

### 3.2 `tests/test_mcp_auth.py` (NEW)

A new test file at `tests/test_mcp_auth.py`. It must NOT replace the existing `tests/test_mcp.py` (which covers tool naming and schema structure). It adds **auth-specific** tests.

Structure:
- `TestMCPHeaderAuth` class — header-primary path (scenarios 1, 3, 5, 9, 10).
- `TestMCPArgumentAuth` class — argument fallback path (scenarios 2, 6, 10).
- `TestMCPAuthFailures` class — missing/invalid keys (scenarios 4, 5, 6).
- `TestMCPTransportContext` class — `request_ctx` behavior, SSE happy path, CORS (scenarios 7, 8, 11, 12).

Reuses fixtures from `tests/conftest.py`:
- `client` — httpx `AsyncClient` against the test app.
- `api_key` — a real raw API key string.
- `app` — the test FastAPI app (mcp is **not** auto-mounted in tests; tests mount it explicitly, see §3.2.1).
- `test_settings` — settings with `mcp_enabled=True` for the auth tests.

#### 3.2.1 Mounting MCP for tests

The default `app` fixture sets `mcp_enabled=False`. The auth tests need MCP mounted. Add a session-scoped autouse-like fixture in `test_mcp_auth.py` (or extend `conftest.py`) that:

1. Overrides `settings.mcp_enabled = True`.
2. Calls `mount_mcp_server(test_app)` before yielding.
3. Restores the original setting after.

The cleanest approach is a local `mcp_app` fixture inside `test_mcp_auth.py` that depends on the `app` fixture, patches `mcp_enabled`, and calls `mount_mcp_server(app)`. Document the pattern in the test file's module docstring so future tests can copy it.

#### 3.2.2 Test pattern: invoking a tool

The MCP JSON-RPC surface accepts `POST /mcp/messages/` with a body of the form:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "drive__files_list",
    "arguments": { "pageSize": 5 }
  }
}
```

For SSE-initiated sessions, the POST also requires a `session_id` query param. For tests, the easiest path is to send a JSON-RPC `initialize` first, capture the session, then call. If the test app's SSE transport does not require a session for direct tool calls (verify during implementation by reading `mcp/server/sse.py:226-233`), tests can POST a single `tools/call` without a session — research claim #16 confirms session_id is only used for routing, not for auth.

Two test patterns to support:
- **Pattern A (unit-test `call_tool` directly):** call the registered handler function with a synthetic `arguments` dict. Mock `request_ctx` to set the header or raise `LookupError`. This is the simplest path and should be used for scenarios 1-6, 9, 10, 12.
- **Pattern B (full integration via `httpx.AsyncClient`):** start the test app, POST a JSON-RPC body, assert response. Used for scenarios 7, 8, 11.

The implementer should choose Pattern A for most tests (it's faster, more isolated, and lets us control `request_ctx` precisely) and Pattern B for the explicit SSE/CORS/session tests.

#### 3.2.3 The 12 test scenarios

Each scenario has a name, the API to use (Pattern A or B), and an explicit pass criterion.

| # | Scenario | Pattern | Test Name | Pass Criterion |
|---|---|---|---|---|
| 1 | Header auth only | A | `test_header_auth_succeeds` | Set `request_ctx` with a header carrying a valid key; call `call_tool("drive__files_list", {})`; assert the response is not a 401 error. |
| 2 | Argument auth only | A | `test_argument_auth_succeeds` | No `request_ctx`; call `call_tool("drive__files_list", {"api_key": valid_key})`; assert not 401. |
| 3 | Both header and argument | A | `test_header_takes_precedence_over_argument` | Set both; assert `_resolve_api_key` is called with the header value, not the argument value. Use a unittest mock on `_resolve_api_key`. |
| 4 | No auth at all | A | `test_no_auth_returns_401` | No `request_ctx` and no `api_key` in arguments; call `call_tool`; assert response contains `{"status": 401}` and the existing error message. |
| 5 | Invalid header key | A | `test_invalid_header_returns_401` | Set `request_ctx` with header `X-Gatekeeper-API-Key: gkp_invalid`; assert 401 with "Invalid API key" message. |
| 6 | Invalid argument key | A | `test_invalid_argument_returns_401` | Arguments contain `{"api_key": "gkp_invalid"}`; assert 401. |
| 7 | Header auth SSE end-to-end | B | `test_header_auth_full_sse_flow` | Mount the SSE app; open GET `/mcp/sse`; POST `tools/call` to `/mcp/messages/` with the header; assert a successful JSON-RPC response. (May be marked `@pytest.mark.skip` initially if SSE test harness is too complex; document the skip reason.) |
| 8 | Header auth across reconnect | B | `test_header_auth_after_reconnect` | (Optional, can be skipped.) Open a session, reconnect with a new `session_id`, POST tool call with the header, assert success. |
| 9 | Schema: api_key not required | A | `test_list_tools_marks_api_key_optional` | Call the registered `list_tools`; for every returned tool, assert `inputSchema.required` does **not** contain `"api_key"` and `inputSchema.properties` **does** contain `"api_key"`. |
| 10 | Existing clients still work | A | `test_existing_argument_only_client_unchanged` | Replay the exact pattern from the previous test suite (call with `api_key` argument, no header) and assert success. Acts as a regression guard. |
| 11 | CORS preflight for header | B | `test_cors_preflight_allows_header` | Send `OPTIONS /mcp/messages/` with `Access-Control-Request-Headers: x-gatekeeper-api-key`; assert response includes `Access-Control-Allow-Headers` containing `x-gatekeeper-api-key` (case-insensitive). |
| 12 | `request_ctx` absent | A | `test_falls_back_to_argument_when_request_ctx_missing` | Mock `request_ctx.get` to raise `LookupError`; pass `api_key` in arguments; assert success (uses argument, not header). Also assert no exception is raised. |

Implementation notes for the test file:
- The `request_ctx` ContextVar is set via `request_ctx.set(RequestContext(...))`; import `RequestContext` from `mcp.shared.context`. Wrap in `try/finally` with `request_ctx.reset(token)` so tests don't leak state.
- A `RequestContext` instance with only `request` set is valid — all other fields have defaults. Construct via `RequestContext(request=fake_starlette_request)`.
- A fake Starlette `Request` can be constructed by `Request(scope={"type": "http", "headers": [(b"x-gatekeeper-api-key", valid_key.encode())]})` and used directly — only the `headers` attribute is read by the implementation.
- To mock `_resolve_api_key` (scenario 3), use `unittest.mock.patch("gatekeeper.mcp_server._resolve_api_key")` and capture the argument passed in.
- For Pattern B tests, use the existing `client` fixture and POST to the app with a JSON-RPC envelope. If the SSE transport requires a session, retrieve the `session_id` from the initial GET response and pass it as a query param on subsequent POSTs.

### 3.3 `docs/MCP_SETUP_AGENT.md`

Add a new short section after the existing "Authentication" content (currently describes the `api_key` argument as the only method):

```markdown
### Header Authentication (Preferred)

MCP clients that can send custom HTTP headers should authenticate via the
`X-Gatekeeper-API-Key` header on the `POST /mcp/messages/` request. This
keeps the raw API key out of the LLM's context window. The `api_key`
argument remains available as a fallback for clients that cannot send
custom headers (some UIs strip them).

Example client config (Claude Desktop):

```json
{
  "mcpServers": {
    "gatekeeper": {
      "url": "http://localhost:8080/mcp/sse",
      "headers": {
        "X-Gatekeeper-API-Key": "gkp_..."
      }
    }
  }
}
```

If the client's UI does not expose a headers field, continue passing
`api_key` as a tool argument — both methods authenticate against the same
key store.
```

(Adjust the `headers` example to the actual client config syntax supported; the JSON above is illustrative.)

### 3.4 `docs/MCP_SETUP_HUMAN.md`

Add a one-paragraph note in the "Connecting an MCP client" section, immediately after the existing instructions, that mentions header auth is supported and points readers to `MCP_SETUP_AGENT.md` for client config examples.

### 3.5 `CHANGELOG.md`

Append one line under the next release header (or under "Unreleased" if that section exists):

```
- MCP tools now prefer `X-Gatekeeper-API-Key` header for auth; `api_key` argument remains as a fallback.
```

---

## 4. Task Breakdown

| # | Task | Assignee | Depends On | Acceptance Criteria |
|---|---|---|---|---|
| 1 | Update `gatekeeper/mcp_server/__init__.py`: add `request_ctx` import, update `instructions`, update `list_tools` schema (remove required, update description), rewrite `call_tool` auth flow per §2.1, optionally extract `_auth_error` helper. | implementer | — | (a) `from mcp.server.lowlevel.server import request_ctx` is importable from this module; (b) `instructions` string contains "X-Gatekeeper-API-Key"; (c) `list_tools` returns tools whose `inputSchema.required` does not contain `"api_key"` and whose `inputSchema.properties` does contain `"api_key"` with the updated description; (d) `call_tool` reads the header from `request_ctx` first, falls back to `arguments.pop("api_key")`, always pops `api_key` from arguments before passing to `proxy.call_google`; (e) `LookupError` from `request_ctx.get()` is caught and treated as "no header." |
| 2 | Create `tests/test_mcp_auth.py` with the 12 test scenarios from §3.2.3. | implementer | #1 | All 12 tests pass; `pytest tests/test_mcp_auth.py` returns exit 0. The `list_tools` schema test (scenario 9) must fail against the pre-#1 code and pass against the post-#1 code. |
| 3 | Update `docs/MCP_SETUP_AGENT.md` and `docs/MCP_SETUP_HUMAN.md` per §3.3-3.4. | implementer | #1 (or in parallel) | The new "Header Authentication (Preferred)" section is present in `MCP_SETUP_AGENT.md` and is reachable from the docs' table of contents / index. `MCP_SETUP_HUMAN.md` mentions header auth and links to `MCP_SETUP_AGENT.md`. |
| 4 | Update `CHANGELOG.md` with the one-line entry per §3.5. | implementer | #1 | Entry exists under the appropriate version or "Unreleased" heading. |
| 5 | Run full test suite (`pytest tests/`) and confirm no regressions. | implementer | #1, #2 | `pytest tests/` exits 0. Existing tests in `tests/test_mcp.py` and `tests/test_auth.py` continue to pass without modification. |

### Per-Task Specification

#### Task 1 — `call_tool` and `list_tools` updates

**Objective:** Move tool-call authentication from the `api_key` argument (required) to the `X-Gatekeeper-API-Key` HTTP header (primary), with the `api_key` argument kept as an optional fallback.

**Files to Create/Modify:**
- `gatekeeper/mcp_server/__init__.py` — five edits per §3.1.

**Acceptance Criteria:**
- [ ] `request_ctx` is imported at the top of the file.
- [ ] `instructions` text mentions "X-Gatekeeper-API-Key" by name.
- [ ] `list_tools` no longer appends `"api_key"` to `required`.
- [ ] `api_key` description in `properties` is the new text from §2.2.
- [ ] `call_tool` attempts `request_ctx.get().request.headers.get("X-Gatekeeper-API-Key")` first.
- [ ] If header missing/empty, `call_tool` uses `arguments.pop("api_key", None)`.
- [ ] `arguments.pop("api_key", None)` is executed in both branches (never leak the key to the proxy).
- [ ] If `request_ctx.get()` raises `LookupError`, the exception is caught and the function falls back to argument auth.
- [ ] If `ctx.request` is `None`, header auth is skipped (treated as no header) without error.
- [ ] The error messages for "API key required" and "Invalid API key" are byte-identical to the previous strings (so any client that pattern-matches on them is unaffected).
- [ ] `proxy.call_google` receives a `params=arguments` dict that contains no `api_key` key.

**Deliverable Location:** `/home/echo/repos/gatekeeper/gatekeeper/mcp_server/__init__.py`

**Expected Effort:** ~30 min. The diff is small and localized; the trickiest part is the `LookupError` guard.

#### Task 2 — `tests/test_mcp_auth.py` (NEW)

**Objective:** Lock in the 12 test scenarios from research §5 so the change is fully verified and regression-safe.

**Files to Create/Modify:**
- `tests/test_mcp_auth.py` — new file, ~12 test functions, organized into 4 test classes per §3.2.

**Acceptance Criteria:**
- [ ] Each of the 12 scenarios has at least one test function with a docstring naming the scenario number.
- [ ] The test file passes against the post-#1 code (`pytest tests/test_mcp_auth.py` exits 0).
- [ ] The list_tools schema test (scenario 9) demonstrably fails against the pre-#1 code (i.e., if you revert edit 3 in §3.1, the test fails with an `AssertionError` mentioning `api_key` in `required`). Add a comment in the test explaining this regression-detection role.
- [ ] Pattern A tests use `unittest.mock.patch` on `request_ctx.get` or set the ContextVar directly with `try/finally` cleanup.
- [ ] Pattern B tests (7, 11) use `httpx.AsyncClient` and the `client` fixture.
- [ ] No new dependencies are added to `pyproject.toml` or `requirements.txt`.
- [ ] The file's module docstring explains the Pattern A vs Pattern B choice and links to §3.2.2 of this spec.

**Deliverable Location:** `/home/echo/repos/gatekeeper/tests/test_mcp_auth.py`

**Expected Effort:** ~1-1.5 hours. Most time is on Pattern B tests (SSE session handling, CORS preflight) — these may need iteration.

#### Task 3 — Documentation updates

**Objective:** Surface header auth in the docs so operators and agents know it's supported.

**Files to Create/Modify:**
- `docs/MCP_SETUP_AGENT.md` — new "Header Authentication (Preferred)" section.
- `docs/MCP_SETUP_HUMAN.md` — one-paragraph mention linking to `MCP_SETUP_AGENT.md`.

**Acceptance Criteria:**
- [ ] The new section in `MCP_SETUP_AGENT.md` includes a working client config example with `X-Gatekeeper-API-Key`.
- [ ] The new section is reachable from the file's existing table of contents (or the file's top-level navigation if there is one).
- [ ] `MCP_SETUP_HUMAN.md` cross-link resolves (clicking the link lands in `MCP_SETUP_AGENT.md`).
- [ ] No existing content is removed; the change is purely additive.

**Deliverable Location:** `/home/echo/repos/gatekeeper/docs/MCP_SETUP_AGENT.md`, `/home/echo/repos/gatekeeper/docs/MCP_SETUP_HUMAN.md`

**Expected Effort:** ~20 min.

#### Task 4 — CHANGELOG entry

**Objective:** Record the change in the project changelog.

**Files to Create/Modify:**
- `CHANGELOG.md` — one-line entry per §3.5.

**Acceptance Criteria:**
- [ ] The entry is under the correct version heading (or "Unreleased").
- [ ] The entry text is the exact one-liner from §3.5.
- [ ] No other lines in the file are modified.

**Deliverable Location:** `/home/echo/repos/gatekeeper/CHANGELOG.md`

**Expected Effort:** ~5 min.

#### Task 5 — Full regression run

**Objective:** Confirm no existing test broke.

**Files to Create/Modify:** none.

**Acceptance Criteria:**
- [ ] `pytest tests/` exits 0.
- [ ] `pytest tests/test_mcp.py tests/test_mcp_auth.py tests/test_auth.py` exits 0 (the three test files most likely to be affected).
- [ ] No new warnings or deprecations are introduced by the change (run with `pytest -W error` to confirm).

**Deliverable Location:** N/A (run, don't write).

**Expected Effort:** ~10 min.

---

## 5. Test Plan (Detailed)

This section expands the 12-scenario table from §3.2.3 into a concrete test plan that the implementer can follow. Every scenario has a "Setup → Action → Assert" structure.

### 5.1 Test infrastructure

**Shared helpers in `tests/test_mcp_auth.py`:**

```python
import contextlib
import json
from unittest.mock import patch

import pytest
import pytest_asyncio
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext
from starlette.requests import Request


def make_request_ctx(headers: dict[str, str] | None = None) -> RequestContext:
    """Build a RequestContext with a fake Starlette Request carrying the given headers."""
    if headers is None:
        headers = {}
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    fake_request = Request(scope={"type": "http", "headers": raw_headers})
    return RequestContext(request=fake_request)


@contextlib.contextmanager
def use_request_ctx(ctx: RequestContext | None):
    """Context manager that sets request_ctx for the duration of a block.
    Pass None to simulate 'no request context available' (LookupError)."""
    if ctx is None:
        # Simulate stdio transport: get() raises LookupError
        with patch.object(request_ctx, "get", side_effect=LookupError):
            yield
    else:
        token = request_ctx.set(ctx)
        try:
            yield
        finally:
            request_ctx.reset(token)
```

**Getting the registered tool handlers for Pattern A:**

```python
from gatekeeper.mcp_server import create_mcp_server

@pytest_asyncio.fixture
async def mcp_handlers():
    """Yield (list_tools_fn, call_tool_fn) for direct invocation."""
    mcp = create_mcp_server()
    # The handlers are registered on mcp._mcp_server via decorators.
    # We grab them from the request handlers list to call directly.
    handlers = mcp._mcp_server.request_handlers
    # Look up by the names registered in the low-level server.
    list_tools = handlers["tools/list"]   # may be wrapped; see mcp source
    call_tool = handlers["tools/call"]
    return list_tools, call_tool
```

**Note for the implementer:** The exact attribute names (`request_handlers`, `tools/list`, `tools/call`) must be verified against the installed `mcp` package source before writing the fixture. If the SDK exposes them differently, the fixture can fall back to calling `list_tools()` and `call_tool()` via the `_mcp_server` private attribute (the same way `mcp_server/__init__.py` does — `mcp._mcp_server.list_tools()`).

### 5.2 Scenarios (detailed)

#### Scenario 1 — Header auth only

```python
async def test_header_auth_succeeds(mcp_handlers, db_session, api_key):
    _, call_tool = mcp_handlers
    ctx = make_request_ctx({"X-Gatekeeper-API-Key": api_key})
    with use_request_ctx(ctx):
        result = await call_tool("drive__files_list", {"pageSize": 5})
    # The handler returns a list of TextContent. The first one is JSON.
    payload = json.loads(result[0].text)
    assert "error" not in payload or payload.get("status") != 401
```

#### Scenario 2 — Argument auth only

```python
async def test_argument_auth_succeeds(mcp_handlers, db_session, api_key):
    _, call_tool = mcp_handlers
    with use_request_ctx(None):  # no request ctx
        result = await call_tool("drive__files_list", {"pageSize": 5, "api_key": api_key})
    payload = json.loads(result[0].text)
    assert "error" not in payload or payload.get("status") != 401
```

#### Scenario 3 — Both header and argument (header wins)

```python
async def test_header_takes_precedence_over_argument(mcp_handlers, db_session, api_key):
    _, call_tool = mcp_handlers
    ctx = make_request_ctx({"X-Gatekeeper-API-Key": api_key})
    # Use a different value for the argument so we can detect which one was used.
    bogus_arg = "gkp_argument_value_not_real_but_distinguishable"
    with use_request_ctx(ctx):
        with patch("gatekeeper.mcp_server._resolve_api_key") as mock_resolve:
            mock_resolve.return_value = None  # we just want to capture the call arg
            await call_tool("drive__files_list", {"api_key": bogus_arg})
    called_with = mock_resolve.call_args[0][0]
    assert called_with == api_key, f"Expected header value, got {called_with!r}"
```

#### Scenario 4 — No auth at all

```python
async def test_no_auth_returns_401(mcp_handlers):
    _, call_tool = mcp_handlers
    with use_request_ctx(None):
        result = await call_tool("drive__files_list", {})
    payload = json.loads(result[0].text)
    assert payload == {
        "error": True,
        "status": 401,
        "message": "API key required (set X-Gatekeeper-API-Key header or pass api_key argument)",
    }
```

#### Scenario 5 — Invalid header key

```python
async def test_invalid_header_returns_401(mcp_handlers):
    _, call_tool = mcp_handlers
    ctx = make_request_ctx({"X-Gatekeeper-API-Key": "gkp_does_not_exist"})
    with use_request_ctx(ctx):
        result = await call_tool("drive__files_list", {})
    payload = json.loads(result[0].text)
    assert payload["status"] == 401
    assert "Invalid" in payload["message"]
```

#### Scenario 6 — Invalid argument key

```python
async def test_invalid_argument_returns_401(mcp_handlers):
    _, call_tool = mcp_handlers
    with use_request_ctx(None):
        result = await call_tool("drive__files_list", {"api_key": "gkp_does_not_exist"})
    payload = json.loads(result[0].text)
    assert payload["status"] == 401
    assert "Invalid" in payload["message"]
```

#### Scenario 7 — Header auth over SSE (full flow)

```python
@pytest.mark.asyncio
async def test_header_auth_full_sse_flow(client, api_key):
    """Open SSE, POST tools/call with header, assert success.

    If the SSE transport requires a session_id, the test retrieves it from
    the initial GET response. If it doesn't, the POST works directly.
    """
    # 1. Open SSE stream
    async with client.stream("GET", "/mcp/sse", headers={"Accept": "text/event-stream"}) as sse:
        assert sse.status_code == 200
        # Read the 'endpoint' event to get the POST URL
        # (the actual mechanism depends on the SDK's SSE transport;
        # this test may need iteration against the installed mcp version)
        async for line in sse.aiter_lines():
            if line.startswith("data: "):
                post_path = line[len("data: "):].strip()
                break
        # 2. POST a tools/call to that path with the header
        resp = await client.post(
            post_path,
            headers={"X-Gatekeeper-API-Key": api_key, "Content-Type": "application/json"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "drive__files_list", "arguments": {}},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "error" not in body or body["error"]["code"] != 401
```

This test is the most likely to need iteration; mark with `@pytest.mark.xfail(reason="SSE test harness TBD", strict=False)` if the first run reveals environment issues. The unit tests in scenarios 1-6 already cover the auth path; scenario 7's job is to confirm wire-format compatibility, not to re-test the auth flow.

#### Scenario 8 — Header auth after reconnect

Marked **optional**. If the SSE harness from scenario 7 is working, add a second test that closes the first stream and opens a new one (new `session_id`), then POSTs a tool call with the header. If scenario 7 is too complex to stabilize, skip 8 with a clear comment.

#### Scenario 9 — Schema: api_key not required

```python
async def test_list_tools_marks_api_key_optional(mcp_handlers):
    list_tools, _ = mcp_handlers
    tools = await list_tools()
    assert tools, "Expected at least one tool"
    for tool in tools:
        schema = tool.inputSchema
        assert "api_key" in schema["properties"], (
            f"api_key should remain in properties for {tool.name}"
        )
        assert "api_key" not in schema.get("required", []), (
            f"api_key should NOT be in required for {tool.name} "
            f"(regression: this test fails against the pre-fix code)"
        )
```

#### Scenario 10 — Existing clients still work

```python
async def test_existing_argument_only_client_unchanged(mcp_handlers, db_session, api_key):
    """Regression: a client passing only api_key (no header) still works."""
    _, call_tool = mcp_handlers
    with use_request_ctx(None):
        result = await call_tool(
            "drive__files_list",
            {"api_key": api_key, "pageSize": 5},  # legacy pattern
        )
    payload = json.loads(result[0].text)
    assert "error" not in payload or payload.get("status") != 401
```

#### Scenario 11 — CORS preflight

```python
async def test_cors_preflight_allows_header(client):
    resp = await client.options(
        "/mcp/messages/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-gatekeeper-api-key, content-type",
        },
    )
    assert resp.status_code in (200, 204)
    allow_headers = resp.headers.get("access-control-allow-headers", "").lower()
    assert "x-gatekeeper-api-key" in allow_headers
```

#### Scenario 12 — `request_ctx` absent

```python
async def test_falls_back_to_argument_when_request_ctx_missing(mcp_handlers, db_session, api_key):
    _, call_tool = mcp_handlers
    with use_request_ctx(None):  # simulates stdio transport: LookupError
        result = await call_tool("drive__files_list", {"api_key": api_key})
    payload = json.loads(result[0].text)
    assert "error" not in payload or payload.get("status") != 401
    # Also assert no exception leaked out (the call returned normally)
    assert isinstance(result, list)
```

### 5.3 Running the tests

```bash
# Run only the new file
cd /home/echo/repos/gatekeeper
.venv/bin/pytest tests/test_mcp_auth.py -v

# Run the full suite to confirm no regressions
.venv/bin/pytest tests/ -v

# Run with strict warnings to catch deprecations
.venv/bin/pytest tests/test_mcp_auth.py -W error
```

---

## 6. Acceptance Criteria for the Implementation Phase

The implementation is complete and ready for review when **all** of the following are true:

### 6.1 Code

- [ ] `gatekeeper/mcp_server/__init__.py` has the five edits from §3.1 applied.
- [ ] No other source files in `gatekeeper/` are modified (the change is self-contained).
- [ ] `git diff --stat` shows changes in exactly: `gatekeeper/mcp_server/__init__.py`, `tests/test_mcp_auth.py` (new), `docs/MCP_SETUP_AGENT.md`, `docs/MCP_SETUP_HUMAN.md`, `CHANGELOG.md`.
- [ ] `grep -n "from mcp.server.lowlevel.server import request_ctx" gatekeeper/mcp_server/__init__.py` returns a match.
- [ ] `grep -n "required.append" gatekeeper/mcp_server/__init__.py` returns **no** matches (the line is removed).

### 6.2 Tests

- [ ] `tests/test_mcp_auth.py` exists and contains at least 12 test functions (one per scenario in §5.2).
- [ ] `pytest tests/test_mcp_auth.py -v` exits 0.
- [ ] `pytest tests/ -v` exits 0 (no regressions in any existing test).
- [ ] The list_tools schema test (scenario 9) demonstrably fails against the pre-#1 code (i.e., a stash-and-rerun of the test against the previous `__init__.py` produces an `AssertionError` mentioning `api_key` in `required`).

### 6.3 Documentation

- [ ] `docs/MCP_SETUP_AGENT.md` has the "Header Authentication (Preferred)" section.
- [ ] `docs/MCP_SETUP_HUMAN.md` cross-links to `MCP_SETUP_AGENT.md`.
- [ ] `CHANGELOG.md` has the one-line entry under the appropriate heading.

### 6.4 Behavior (manual smoke check)

- [ ] Start Gatekeeper with `mcp_enabled=True`.
- [ ] Connect a real MCP client (e.g., Claude Desktop) configured to send `X-Gatekeeper-API-Key` on the SSE connection.
- [ ] Call a tool (`drive__files_list`) and confirm: (a) the tool returns a successful response; (b) the raw key does **not** appear in the LLM's tool-call arguments (verify in the MCP client's request log).
- [ ] Disconnect and reconnect; confirm the same call still works (the header is read on every POST, so reconnects are fine).
- [ ] Switch the client to passing `api_key` as an argument (legacy mode); confirm the call still works.
- [ ] Send a tool call with no auth at all; confirm a 401 response with the message from scenario 4.

### 6.5 Risks and Open Questions for Lens

Lens should specifically verify:

1. **CORS on mounted sub-app.** The research flags this as a potential issue. Test 11 is the empirical check. If the test fails, the implementer may need to add a second `CORSMiddleware` to the SSE sub-app or to `mount_mcp_server`.
2. **`request_ctx.request` typing.** The implementation reads `ctx.request.headers.get(...)` — this assumes `ctx.request` is a Starlette `Request`. It is, per the research and the SDK source. The implementer should add a `hasattr(ctx.request, "headers")` guard as a belt-and-suspenders check.
3. **Error-message stability.** The current "API key required" message says `"(pass as api_key argument)"`. The new message adds "or set X-Gatekeeper-API-Key header." Verify no client in the wild is doing exact-string matches against the old message (a search of the repo and the agent docs should be enough).
4. **`api_key` removal from `arguments`.** The implementer must `pop` the key in **both** branches (header path and argument path) so the key never reaches `proxy.call_google`. Add a sanity test (or extend scenario 3) that asserts `arguments` passed to `proxy.call_google` does not contain `api_key`.
5. **Backward compat with old clients reading `required`.** Any client that hardcodes the assumption that `api_key` is required will break. The `instructions` string update mitigates this. The regression test (scenario 10) ensures old code paths still work. Lens should check that no internal Gatekeeper code or doc instructs clients to fail-fast if `api_key` is missing from the tool schema.

### 6.6 Out-of-Scope Reminders (Lens should confirm these stay out)

- Implementing Option B (MCP SDK OAuth/Bearer) — explicitly deferred.
- Changing REST API auth (still uses `validate_api_key` dependency, unchanged).
- Changing the SSE transport's DNS-rebinding / allowed-hosts config.
- Adding new MCP routes or modifying existing route definitions.
- Changing the `ApiKey` model or key generation logic.

---

## 7. Dependency Map

```
Task 1 (code change) ──┬─→ Task 2 (tests) ──┐
                       │                     ├─→ Task 5 (full suite run)
                       ├─→ Task 3 (docs) ────┤
                       └─→ Task 4 (changelog) ┘
```

Tasks 3 and 4 are independent of Task 2 and can be done in parallel with it. Task 5 requires both 1 and 2 to be complete. Total wall-clock: ~2-3 hours for a single implementer, or ~1.5 hours if 3 and 4 are parallelized.

---

## 8. References

| Source | Purpose |
|---|---|
| `docs/research/header-auth-tool-calls-research.md` | Upstream research; 28 validated claims; 12 test scenarios. |
| `gatekeeper/mcp_server/__init__.py:62-82` | `_resolve_api_key` (unchanged). |
| `gatekeeper/mcp_server/__init__.py:85-117` | `create_mcp_server` and `instructions` (Edits 1, 2). |
| `gatekeeper/mcp_server/__init__.py:143-151` | `list_tools` schema injection (Edit 3). |
| `gatekeeper/mcp_server/__init__.py:179-210` | `call_tool` handler (Edit 4). |
| `gatekeeper/auth.py:28-66` | REST auth (reference, not modified). |
| `gatekeeper/main.py:150-156` | CORS config (already correct, no change). |
| `gatekeeper/main.py:322` | `app.mount("/mcp", starlette_app)` (verified, no change). |
| `mcp/server/lowlevel/server.py:109` | `request_ctx: ContextVar` definition. |
| `mcp/server/lowlevel/server.py:759-798` | `request_ctx.set()` and `request_ctx.reset()` lifecycle. |
| `mcp/server/sse.py:217-269` | SSE transport passes Starlette `Request` to low-level server. |
| `mcp/server/streamable_http.py:268-274, 543, 566` | Streamable HTTP transport passes the same context. |
| `mcp/shared/context.py:20-32` | `RequestContext` dataclass (request field is optional). |
| `mcp/shared/message.py:30-35` | `ServerMessageMetadata(request_context=...)` carrier. |
| `tests/conftest.py` | Reusable fixtures (`client`, `app`, `api_key`, etc.). |
| `tests/test_mcp.py` | Existing tool-naming and schema tests (unchanged, must keep passing). |
| `tests/test_auth.py` | REST auth tests (unchanged, must keep passing). |
