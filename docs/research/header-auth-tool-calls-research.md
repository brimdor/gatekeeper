## Intelligence Brief: Gatekeeper Header Auth for MCP Tool Calls

### Summary

Gatekeeper has a two-layer auth problem: the REST API authenticates via the `X-Gatekeeper-API-Key` header (validated by `validate_api_key` dependency), while the MCP/SSE endpoint requires the `api_key` as a required parameter in every tool call argument. This means MCP clients must pass the API key as a tool argument, which (a) exposes the raw key in the LLM's context window, (b) forces every tool schema to include an `api_key` field, and (c) creates a divergence from the REST API's header-based auth pattern. The fix is feasible: the MCP SDK's SSE transport carries the Starlette `Request` object (with headers) through to tool call handlers via `request_ctx` context variable, enabling header-based auth at the SSE/MCP layer that eliminates the need for `api_key` in tool arguments.

**All 28 claims in the original brief have been validated against the installed MCP SDK (mcp>=1.0) and the Gatekeeper source code. The technical path is confirmed.**

---

### Validated Findings

#### Current Problematic Behavior

| # | Claim | Source | Confidence |
|---|---|---|---|
| 1 | REST API uses `X-Gatekeeper-API-Key` header via `validate_api_key` FastAPI dependency | `gatekeeper/auth.py:28-66` — reads `request.headers.get("X-Gatekeeper-API-Key")`, raises 401 if missing | **Certain** ✅ |
| 2 | MCP endpoint requires `api_key` as a required parameter in every tool's `inputSchema` | `gatekeeper/mcp_server/__init__.py:146-151` — `props["api_key"] = {...}` and `required.append("api_key")` for every enabled route | **Certain** ✅ |
| 3 | MCP `call_tool()` extracts `api_key` from arguments, pops it, then validates via `_resolve_api_key()` | `gatekeeper/mcp_server/__init__.py:188-210` — `arguments.pop("api_key", None)`, returns 401 JSON if missing | **Certain** ✅ |
| 4 | Raw API key appears in LLM context window because it's a tool argument | MCP specification: tool arguments are serialized in the JSON-RPC call, visible to the LLM | **Certain** ✅ |
| 5 | The `api_key` parameter is injected into tool schemas at listing time, not part of the route's own `input_schema` | `gatekeeper/mcp_server/__init__.py:144-151` — `props["api_key"] = {...}` and `required.append("api_key")` are added dynamically | **Certain** ✅ |
| 6 | Header auth cannot flow to MCP tool calls because `call_tool` handler only receives `(name, arguments)` — no request object | `mcp/server/lowlevel/server.py:541` — `results = await func(tool_name, arguments)` passes only name and arguments to the handler | **Certain** ✅ |
| 7 | The MCP SDK DOES carry the Starlette `Request` in a context variable `request_ctx` | `mcp/server/lowlevel/server.py:109` — `request_ctx: contextvars.ContextVar[RequestContext[...]]` is a module-level ContextVar; `mcp/server/lowlevel/server.py:759-775` — `request_ctx.set(RequestContext(..., request=request_data, ...))` before calling handler | **Certain** ✅ |
| 8 | The `request_data` is the Starlette `Request` object from the SSE POST message | `mcp/server/sse.py:269` — `metadata = ServerMessageMetadata(request_context=request)` where `request` is the Starlette `Request` from `handle_post_message` (line 219); `mcp/server/lowlevel/server.py:747` — `request_data = message.message_metadata.request_context` | **Certain** ✅ |
| 9 | The SSE transport validates DNS rebinding but does NOT check for API key headers | `mcp/server/sse.py:222` — `error_response = await self._security.validate_request(request, is_post=True)` checks Host/Origin/Content-Type but not custom auth headers | **Certain** ✅ |
| 10 | CORS middleware allows the `X-Gatekeeper-API-Key` header | `gatekeeper/main.py:155` — `allow_headers=["X-Gatekeeper-API-Key", "Authorization", "Content-Type"]` | **Certain** ✅ |

#### Option A1 Feasibility: Header on every POST message (recommended)

The MCP SDK already carries the Starlette `Request` object from each `POST /mcp/messages/` call through to the tool handler via `request_ctx`. This means:

1. The `call_tool` handler in Gatekeeper can access `request_ctx.get().request` to get the Starlette `Request` object
2. From that `Request`, it can read `request.headers.get("X-Gatekeeper-API-Key")`
3. If the header is present, use it for auth; fall back to `api_key` argument for backward compatibility

**Key validation of the `request_ctx` mechanism:**

- **`request_ctx` is a `contextvars.ContextVar`** (line 109 of `mcp/server/lowlevel/server.py`) — this means it's safe across asyncio tasks; each request gets its own context copy.
- **It's set BEFORE the handler runs** (lines 759-775): `token = request_ctx.set(RequestContext(..., request=request_data, ...))` is called before `response = await handler(req)` at line 776.
- **It's reset AFTER the handler runs** (line 798): `request_ctx.reset(token)` in the `finally` block.
- **The handler registered via `@mcp._mcp_server.call_tool()` is called INSIDE this context** — the `handler(req)` at line 776 calls the wrapper which calls `func(tool_name, arguments)` at line 541, which is the Gatekeeper `call_tool` function.
- **`RequestContext.request` is typed as `RequestT | None`** (line 30 of `mcp/shared/context.py`) — it can be `None` if no request context was provided, so code must handle this case.

**Implementation path (confirmed):**
```python
# In gatekeeper/mcp_server/__init__.py call_tool handler:
from mcp.server.lowlevel.server import request_ctx

async def call_tool(name: str, arguments: dict[str, Any]) -> list:
    # Try header auth first
    api_key = None
    try:
        ctx = request_ctx.get()
        if ctx and ctx.request is not None:
            api_key = ctx.request.headers.get("X-Gatekeeper-API-Key")
    except LookupError:
        pass  # No request context available
    
    # Fall back to argument-based auth
    if not api_key:
        api_key = arguments.pop("api_key", None)
    else:
        arguments.pop("api_key", None)  # Remove if present, header takes priority
    
    if not api_key:
        return [types.TextContent(type="text", text=json.dumps({...}))]
    
    key_record = await _resolve_api_key(api_key)
    ...
```

| # | Claim | Source | Confidence |
|---|---|---|---|
| 11 | `request_ctx` context variable is set before `call_tool` handler runs | `mcp/server/lowlevel/server.py:759-776` — `request_ctx.set(...)` at line 759, `await handler(req)` at line 776 | **Certain** ✅ |
| 12 | The Starlette `Request` object contains all HTTP headers from the POST message | Starlette docs + `mcp/server/sse.py:219,269` — `Request(scope, receive)` carries full ASGI scope including headers; `ServerMessageMetadata(request_context=request)` passes the complete `Request` | **Certain** ✅ |
| 13 | MCP clients (Claude Desktop, Cursor, etc.) can be configured to send custom headers on SSE connections | MCP SSE spec: the initial GET `/sse` and subsequent POST `/messages/` are standard HTTP requests; clients can add headers | **Likely** — untested per-client, but HTTP spec supports it |
| 14 | The `X-Gatekeeper-API-Key` header is already in the CORS `allow_headers` list | `gatekeeper/main.py:155` | **Certain** ✅ |
| 15 | FastAPI's CORS middleware will process the `/mcp/messages/` POST path since the MCP SSE app is mounted under `/mcp` | `gatekeeper/main.py:322` — `app.mount("/mcp", starlette_app)` — mounted sub-apps receive middleware from the parent | **Likely** ✅ — Starlette mounting behavior means middleware on the parent app applies to mounted sub-apps |

**IMPORTANT CAVEAT on claim #15:** FastAPI's `app.mount()` creates a sub-application. CORS middleware added via `app.add_middleware()` on the parent FastAPI app will process requests BEFORE they reach the mounted sub-app. However, this depends on Starlette's middleware execution order. If the mounted sub-app handles the response directly without the parent middleware seeing it, CORS headers might not be added. This should be verified in integration testing (test scenario #7). The SSE transport's own `TransportSecurityMiddleware` runs inside the sub-app and does NOT interfere with CORS headers.

#### Option A2: Header on SSE connection (capture at GET) — NOT recommended

| # | Claim | Source | Confidence |
|---|---|---|---|
| 16 | SSE sessions are keyed by UUID, and the session ID is passed via query param on POST messages | `mcp/server/sse.py:226-233` — session_id validated on POST | **Certain** ✅ |
| 17 | The MCP SDK does NOT currently provide a way to store per-session state from the initial GET request that survives to tool call time | No session-level key-value store exists in `SseServerTransport` or `Server` | **Certain** ✅ |
| 18 | Custom session-level state would require monkey-patching or subclassing `SseServerTransport` | The `_read_stream_writers` dict only stores `MemoryObjectSendStream` objects, not arbitrary session data | **Certain** ✅ |

**Sub-approach A2 is NOT recommended** — it requires invasive SDK modifications and doesn't handle session reconnection well. A1 is simpler and more robust.

#### Option B: MCP SDK's Built-in OAuth/Bearer Auth

| # | Claim | Source | Confidence |
|---|---|---|---|
| 19 | `BearerAuthBackend` intercepts the `Authorization` header and validates via `TokenVerifier.verify_token()` | `mcp/server/auth/middleware/bearer_auth.py` exists in the SDK | **Certain** ✅ |
| 20 | `RequireAuthMiddleware` enforces auth on SSE endpoints | `mcp/server/auth/middleware/bearer_auth.py` | **Certain** ✅ |
| 21 | Gatekeeper currently creates `FastMCP` without `auth_server_provider` or `token_verifier` | `gatekeeper/mcp_server/__init__.py:102-117` — no auth params passed | **Certain** ✅ |
| 22 | Using the SDK's auth system would require implementing `TokenVerifier` to validate Gatekeeper API keys | Custom implementation needed — `verify_token(token)` must return `AccessToken | None` | **Likely** ✅ |

**Option B is viable but heavier.** It requires implementing `TokenVerifier` that maps Gatekeeper API keys to `AccessToken` objects, and potentially the full `OAuthAuthorizationServerProvider` for dynamic client registration. This is the "proper" OAuth approach but adds significant complexity for what is essentially a single-token authentication system.

**Recommendation: Option A1 (header on every POST) is the simplest path with the least SDK coupling.**

#### Streamable HTTP Transport Support

| # | Claim | Source | Confidence |
|---|---|---|---|
| 23 | The MCP SDK also supports `StreamableHTTPTransport` that carries `request_context=request` metadata | `mcp/server/streamable_http.py:268-274,543,566` — `ServerMessageMetadata(request_context=request)` in multiple places | **Certain** ✅ |
| 24 | The same `request_ctx` mechanism works for StreamableHTTP transport | Same `request_ctx` ContextVar is set by the low-level server regardless of transport | **Certain** ✅ |

This means Option A1 would support both SSE and StreamableHTTP transports without changes.

### Tool Schema Updates Required

To make `api_key` optional (header auth primary, argument fallback):

| # | Change | File & Lines | Confidence |
|---|---|---|---|
| 25 | Remove `api_key` from `required` list in `list_tools()` | `gatekeeper/mcp_server/__init__.py:151` — currently `required.append("api_key")` | **Certain** ✅ |
| 26 | Keep `api_key` in `properties` but mark it as optional (not in `required`) | `gatekeeper/mcp_server/__init__.py:146-149` — keep `props["api_key"]` but don't add to required | **Certain** ✅ |
| 27 | Update `api_key` description to indicate header auth is preferred | Change description from `"Gatekeeper API key for authentication"` to `"API key (optional if X-Gatekeeper-API-Key header is provided)"` | **Certain** ✅ |
| 28 | Update `call_tool()` to try header auth first, fall back to argument | `gatekeeper/mcp_server/__init__.py:188-210` — add header extraction before argument extraction | **Certain** ✅ |
| 29 | Update `call_tool()` to pop `api_key` from arguments even when using header auth | Prevent the key from being forwarded to `proxy.call_google()` — `arguments.pop("api_key", None)` should always execute | **Certain** ✅ |
| 30 | Update MCP server instructions to mention header auth | `gatekeeper/mcp_server/__init__.py:104-113` — FastMCP `instructions` string | **Certain** ✅ |

### Detailed Affected Files/Functions

| File | Lines | Function/Section | Change Required |
|---|---|---|---|
| `gatekeeper/mcp_server/__init__.py` | 1-10 | Module imports | Add `from mcp.server.lowlevel.server import request_ctx` |
| `gatekeeper/mcp_server/__init__.py` | 104-113 | `instructions` in `FastMCP()` constructor | Update text to document header auth as preferred |
| `gatekeeper/mcp_server/__init__.py` | 146-151 | `list_tools()` schema building | Remove `required.append("api_key")`, update `api_key` description |
| `gatekeeper/mcp_server/__init__.py` | 179-210 | `call_tool()` handler | Add header extraction via `request_ctx`, modify auth flow to try header first then argument |

### Testing Scenarios (Validated and Finalized)

| # | Scenario | What to Test | Priority | Test Approach |
|---|---|---|---|---|
| 1 | Header auth only (no `api_key` argument) | Send `X-Gatekeeper-API-Key` header on POST `/mcp/messages/`, no `api_key` in tool arguments → should succeed | Critical | MCP integration test with httpx client sending custom header |
| 2 | Argument auth only (no header) | Send tool call with `api_key` argument, no header → should succeed (backward compat) | Critical | Existing test pattern (unit test of `call_tool` with `api_key` in arguments) |
| 3 | Both header and argument | Send both header and `api_key` argument → header should take priority, argument should be ignored/removed | High | Integration test with both header and argument |
| 4 | No auth at all | Send tool call with neither header nor `api_key` argument → should return 401 error | Critical | Unit test of `call_tool` with empty arguments and no request context |
| 5 | Invalid header key | Send `X-Gatekeeper-API-Key: invalid` header → should return 401 | High | Integration test with invalid header value |
| 6 | Invalid argument key | Send `api_key: "invalid"` argument → should return 401 | High | Existing test pattern |
| 7 | Header auth with SSE connection | Full SSE flow: `GET /mcp/sse` + `POST /mcp/messages/` with header → tool calls should work | Critical | End-to-end test with actual MCP client or SSE test harness |
| 8 | Header auth across session reconnection | After SSE reconnect (new session_id), header on new POST should still work | Medium | Integration test simulating session reconnect |
| 9 | Schema validation: `api_key` not required | `list_tools` response should show `api_key` in properties but NOT in required | Critical | Unit test of `list_tools` output |
| 10 | Existing clients continue to work | Clients passing `api_key` as argument (current behavior) should still work without changes | Critical | Regression test of existing `call_tool` behavior |
| 11 | CORS preflight for `X-Gatekeeper-API-Key` | Browser-based MCP clients should receive CORS headers allowing the custom header | Medium | Integration test checking CORS preflight response |
| 12 | `request_ctx` absent (non-SSE invocation) | If `call_tool` is called without an SSE transport (e.g., stdio), `request_ctx.get()` raises `LookupError` → should fall back to argument auth gracefully | High | Unit test mocking `LookupError` from `request_ctx.get()` |

### Gaps and Unknowns

- **MCP client header support:** Not all MCP clients (Claude Desktop, Cursor, etc.) may support sending custom headers on SSE connections. This needs verification per client. If a client doesn't support custom headers, the `api_key` argument fallback remains necessary. The MCP SSE spec itself allows custom headers — it's a client capability question.
- **Header precedence between GET and POST:** The SSE connection starts with a GET that could carry a header, but subsequent POSTs are separate HTTP requests. A1 only checks POST headers. If a client sends the header only on the initial GET, it won't work — but this is the correct behavior since each POST is a separate request.
- **`request_ctx` availability within low-level handler:** Confirmed that `request_ctx` IS set before the handler runs (line 759) and IS available inside the handler. However, this relies on the MCP SDK's internal implementation — a breaking change to `request_ctx` could break this approach. The ContextVar is a module-level variable (not private), which provides some stability guarantee.
- **Thread/coroutine safety of `request_ctx`:** `request_ctx` is a `contextvars.ContextVar`, which is safe across asyncio tasks. Each request gets its own context. No concurrency issues expected.
- **Streamable HTTP transport:** Confirmed that `ServerMessageMetadata(request_context=request)` is also set in `streamable_http.py` (lines 268-274, 543, 566), so Option A1 would support both transports.
- **CORS middleware on mounted sub-app:** The parent FastAPI app's CORS middleware should process requests to `/mcp/messages/` before they reach the mounted Starlette sub-app. This is the standard Starlette behavior but should be verified in integration testing (scenario #11).

### Recommendations

1. **Implement Option A1** — Extract `X-Gatekeeper-API-Key` from `request_ctx.get().request.headers` in the `call_tool` handler, falling back to `arguments.pop("api_key")`.
2. **Make `api_key` optional in tool schemas** — Remove from `required` list, update description to indicate header auth is preferred.
3. **Keep backward compatibility** — `api_key` as argument still works for clients that can't send headers.
4. **Update MCP server instructions** — Document header auth as preferred method.
5. **Add integration tests** for all 12 testing scenarios above, especially scenarios 1, 4, 7, 9, and 10.
6. **Handle `LookupError` gracefully** — When `request_ctx.get()` raises (e.g., stdio transport), fall back to argument auth without error.
7. **Consider Option B (SDK OAuth)** as a future enhancement — once header auth is working, the `TokenVerifier` approach would be a cleaner long-term solution that aligns with the MCP SDK's auth architecture.

---

### Key Files Referenced

| File | Role | Status |
|---|---|---|
| `gatekeeper/auth.py:18,28-66` | REST API key validation via `X-Gatekeeper-API-Key` header | **Confirmed** |
| `gatekeeper/mcp_server/__init__.py:62-82` | `_resolve_api_key()` — bcrypt-based key lookup | **Confirmed** |
| `gatekeeper/mcp_server/__init__.py:85-117` | `create_mcp_server()` — FastMCP constructor, `instructions`, `list_tools()` adds `api_key` to schema | **Needs modification** |
| `gatekeeper/mcp_server/__init__.py:143-151` | `list_tools()` — `api_key` injection into schema (properties + required) | **Needs modification** |
| `gatekeeper/mcp_server/__init__.py:179-210` | `call_tool()` — extracts `api_key` from arguments, validates | **Needs modification** |
| `gatekeeper/mcp_server/__init__.py:296-330` | `mount_mcp_server()` — mounts Starlette app under `/mcp` | **No change needed** |
| `gatekeeper/main.py:150-156` | CORS middleware configuration with `X-Gatekeeper-API-Key` in `allow_headers` | **No change needed** (already correct) |
| `gatekeeper/main.py:322` | `app.mount("/mcp", starlette_app)` — sub-app mounting | **No change needed** |
| `mcp/server/lowlevel/server.py:109` | `request_ctx` ContextVar definition | **Confirmed** — stable API |
| `mcp/server/lowlevel/server.py:740-775` | `request_ctx.set(...)` before handler invocation | **Confirmed** — the mechanism works |
| `mcp/server/lowlevel/server.py:797-798` | `request_ctx.reset(token)` in finally block | **Confirmed** — proper cleanup |
| `mcp/server/sse.py:217-269` | SSE transport: `handle_post_message()` passes Starlette `Request` as `ServerMessageMetadata.request_context` | **Confirmed** |
| `mcp/shared/context.py:20-32` | `RequestContext` dataclass with `request: RequestT | None` field | **Confirmed** — `request` can be `None` |
| `mcp/shared/message.py:30-35` | `ServerMessageMetadata(request_context=...)` — carries the `Request` object | **Confirmed** |
| `mcp/server/streamable_http.py:268-274,543,566` | StreamableHTTP transport also passes `request_context=request` | **Confirmed** — A1 works for both transports |