# Gatekeeper Error Handling Guide for Agents

**Audience:** AI agents and their developers integrating with Gatekeeper.  
**See also:** [MCP_SETUP_AGENT.md](MCP_SETUP_AGENT.md) for transport setup, [ARCHITECTURE.md](ARCHITECTURE.md) for request flow, [POLICY_REFERENCE.md](POLICY_REFERENCE.md) for policy behavior.

---

## 1. Error Envelope

Gatekeeper returns errors in a consistent JSON envelope:

```json
{
  "error": true,
  "status": 403,
  "message": "Route drive.files.delete is disabled"
}
```

The same envelope is used for:

- MCP `tools/call` responses (as the `text` field of a `TextContent` object)
- REST API error responses

Sources: `gatekeeper/mcp_server/__init__.py:194-209` (MCP auth errors), `gatekeeper/api/proxy.py:90-93` (policy deny), `gatekeeper/api/proxy.py:415-422` (upstream failure).

## 2. HTTP Status Code Reference

| Code | When it occurs | What the agent should do |
|---|---|---|
| **400** | Missing required parameter, invalid JSON body, malformed multipart upload, or a parameter type mismatch. | Fix the request payload. Do not retry the same payload. |
| **401** | Missing `api_key` argument (MCP) or missing/invalid API key header (REST). | Verify the key is present, complete, and not truncated. Re-prompt the user for a key if needed. |
| **403** | Key lacks module permission, route is disabled, or no policy exists for the route. | Call `list_tools` to confirm the tool is visible. If not visible, ask the admin to enable the route or grant module permissions. |
| **404** | Module or route not found (usually indicates a stale tool list or a renamed route). | Refresh `list_tools` and retry. Escalate if the tool remains missing. |
| **413** | Multipart upload exceeds `max_file_size_mb`. | Compress or split the file, or ask the admin to raise the policy limit. |
| **421** | DNS rebinding protection rejected the Host header. | See §5 below. |
| **429** | Per-key rate limit exceeded (`GATEKEEPER_RATE_LIMIT_PER_MINUTE`). | Back off and retry with exponential delay. See §4. |
| **500** | Unexpected internal error in the proxy. | Treat as transient; retry once, then escalate to admin. |
| **502** | Google API returned an HTTP error the proxy could not recover from. | Treat as transient; retry with backoff. See §4. |
| **503** | Google API transient error or unavailability. | Treat as transient; retry with backoff. See §4. |
| **504** | Google API request timed out. | Treat as transient; retry once cautiously. See §4. |

### Example responses

**401 — missing API key (MCP):**

```json
{
  "error": true,
  "status": 401,
  "message": "API key required (pass as api_key argument)"
}
```

**403 — route disabled:**

```json
{
  "error": true,
  "status": 403,
  "message": "Route drive.files.delete is disabled"
}
```

**403 — module not permitted for key:**

```json
{
  "error": true,
  "status": 403,
  "reason": "Key not authorized for module: gmail"
}
```

**421 — DNS rebinding rejected:**

```json
{
  "error": true,
  "status": 421,
  "message": "DNS rebinding protection blocked this request"
}
```

**429 — rate limit:**

```json
{
  "error": true,
  "status": 429,
  "message": "Rate limit exceeded"
}
```

**502 — Google upstream failure:**

```json
{
  "error": true,
  "status": 502,
  "message": "Google API request failed: <httpx error>"
}
```

## 3. Structured Error Fields Beyond `status`

Gatekeeper keeps the error envelope minimal. Depending on the failure source you may see:

- `error`: always `true` for failures.
- `status`: the HTTP status code.
- `message` or `reason`: human-readable explanation.

Agents should treat the response as opaque except for the three well-known keys above. Do not depend on additional fields; log the full payload for admin review.

## 4. Transient Errors and Retry Policy

Treat these codes as safe to retry:

- **429** — rate limit
- **502** — Google upstream error
- **503** — Google transient
- **504** — Google timeout

Recommended algorithm:

```text
max_attempts = 3
base_delay_seconds = 1
max_delay_seconds = 30
for attempt in 1..max_attempts:
    try request
    if status in (429, 502, 503, 504):
        delay = min(base_delay_seconds * 2^(attempt-1), max_delay_seconds)
        wait(delay)
        continue
    return result
return last error
```

Do **not** retry these codes with the same payload:

- **400** — fix the request first.
- **401** — verify credentials first.
- **403** — escalate to admin first.
- **421** — fix the host configuration first.
- **413** — reduce payload size first.

## 5. DNS Rebinding (421) Deep Dive

The MCP SDK enables DNS rebinding protection by default. Gatekeeper allows `localhost` and `127.0.0.1` automatically, plus any hosts in `GATEKEEPER_MCP_ALLOWED_HOSTS`. If your agent connects from a different hostname or IP, the SSE handshake will fail with 421.

Sources: `gatekeeper/mcp_server/__init__.py:_build_transport_security()` (lines 27-59), `gatekeeper/main.py:481-539` (`gatekeeper hosts` CLI).

### How to fix

1. Add the host to the allowed list:

   ```bash
   gatekeeper hosts add myhost.tail-abc.ts.net
   # or for any hostname on the configured port:
   gatekeeper hosts add "*"
   ```

2. Restart Gatekeeper:

   ```bash
   gatekeeper service restart
   ```

3. Verify the host appears in `gatekeeper hosts list`.

See also: [PODMAN_DEPLOYMENT.md](PODMAN_DEPLOYMENT.md) § DNS rebinding / MCP allowed hosts.

## 6. Disabled Route Behavior

When an admin disables a route:

- The tool disappears from `list_tools` on the next discovery call (no server restart required).
- An existing `call_tool` to the old tool name returns 403.
- The policy row remains in the database so it can be re-enabled later.

Source: `gatekeeper/mcp_server/__init__.py:139-142`.

## 7. Timeouts and Partial Failures

Current timeout configuration:

- `GATEKEEPER_RATE_LIMIT_PER_MINUTE` defaults to `120` (see `gatekeeper/config.py:74`).
- Google API calls use `httpx.AsyncClient` with no explicit read timeout today; long requests may hang until the OS times out the socket.

On a timeout the agent receives a 504 or a transport-level error. Treat it as transient and retry once. If a mutation request (POST/PUT/PATCH/DELETE) timed out, verify whether the mutation actually succeeded before retrying — check with a corresponding GET first.

## 8. Debugging Checklist

Before escalating to an admin, walk this list:

1. **Verify `list_tools`** includes the expected tool. If it is missing, the route is disabled or the module is not enabled.
2. **Confirm `api_key`** is present and not truncated. MCP tools require an `api_key` argument on every call.
3. **Check the structured error.** Read `status` and `message`/`reason` to decide whether to retry or escalate.
4. **Check `gatekeeper status`** for server health, OAuth connectivity, and module enablement.
5. **Verify allowed hosts** if you see 421 or transport-level connection failures.
6. **Escalate to admin** if the error is 403, 500 on retry, or persistent 502/503.
