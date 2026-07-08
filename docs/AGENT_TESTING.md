# Gatekeeper Agent Testing Guide

**Audience:** Agent developers testing an integration with Gatekeeper.  
**See also:** [MCP_SETUP_AGENT.md](MCP_SETUP_AGENT.md), [AGENT_ERRORS.md](AGENT_ERRORS.md), [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. Local Test Harness

1. Install Gatekeeper in a dev profile:

   ```bash
   git clone https://github.com/brimdor/gatekeeper.git
   cd gatekeeper
   uv pip install -e ".[dev]"
   ```

2. Initialize the database and seed default policies:

   ```bash
   gatekeeper init
   ```

3. Authenticate to a test Google account:

   ```bash
   gatekeeper auth
   ```

4. Create an API key:

   ```bash
   gatekeeper key create --name test-agent --permissions drive,gmail,calendar
   ```

5. Start the server:

   ```bash
   gatekeeper serve
   ```

6. Point your agent at:

   ```text
   http://localhost:8080/mcp/sse
   ```

Every `tools/call` must include the `api_key` argument.

## 2. Smoke Test Script

`smoke_test.py` validates every route against live Google APIs. It requires an authenticated test account and prompts for confirmation before making writes.

First 30 lines of expected output when prerequisites are not met:

```text
============================================================
  Gatekeeper Route Smoke Test
  ============================
  WARNING: This will make live calls to Google APIs
  Ensure you have authenticated to your SECONDARY / TEST account.
============================================================

❌ No credentials found. Run 'gatekeeper auth' first.
```

After auth, the script prints per-route pass/fail tallies.

## 3. Per-Route Verification

For each module, confirm at least one enabled route works.

### Drive

REST:

```bash
curl -H "Authorization: Bearer *** \
  "http://localhost:8080/api/v1/drive/files/list?max_results=5"
```

MCP `tools/call`:

```json
{
  "name": "drive__files_list",
  "arguments": {"api_key": "gkp_...", "max_results": 5}
}
```

### Gmail

REST:

```bash
curl -H "Authorization: Bearer *** \
  "http://localhost:8080/api/v1/gmail/messages/list?max_results=5&label_ids=INBOX"
```

MCP:

```json
{
  "name": "gmail__messages_list",
  "arguments": {"api_key": "gkp_...", "max_results": 5, "label_ids": ["INBOX"]}
}
```

### Calendar

REST:

```bash
curl -H "Authorization: Bearer *** \
  "http://localhost:8080/api/v1/calendar/events/list?calendar_id=primary&max_results=5"
```

MCP:

```json
{
  "name": "calendar__events_list",
  "arguments": {"api_key": "gkp_...", "calendar_id": "primary", "max_results": 5}
}
```

## 4. Negative Tests

| Scenario | Setup | Expected outcome |
|---|---|---|
| Route disabled | Disable `drive.files.delete` in admin UI | Tool disappears from `list_tools`; calling it returns 403. |
| Key revoked | Revoke the key via admin UI or `gatekeeper key revoke --prefix ...` | Any call returns 401/403. |
| Missing scopes | Request a Drive scope the admin account did not grant | Google returns 403 inside the Gatekeeper response. |
| Bad API key | Omit or truncate `api_key` | MCP returns 401 with "API key required". |
| Rate limit | Exceed 120 requests/minute with one key | Returns 429. |

## 5. MCP Connection Debugging

If the agent cannot connect to the MCP SSE endpoint, walk this list:

1. **Transport** — Gatekeeper uses SSE. Ensure the client connects to `http://localhost:8080/mcp/sse` and posts messages to `/mcp/messages/`.
2. **Allowed hosts** — If you see 421 or transport-level rejections, add the hostname via `gatekeeper hosts add` or `GATEKEEPER_MCP_ALLOWED_HOSTS`. Source: `gatekeeper/mcp_server/__init__.py:27-59`.
3. **Transport security** — The SDK's DNS rebinding protection is enabled by default. Localhost/127.0.0.1 are allowed automatically. Source: `gatekeeper/mcp_server/transport.py`.
4. **Authentication** — MCP uses the `api_key` argument, not JWT. REST uses the `Authorization` header. They carry the same key.
5. **Server health** — Run `gatekeeper status` and `curl http://localhost:8080/health` to confirm the server is up.
6. **Firewall / proxy** — Confirm port 8080 is reachable and no reverse proxy is stripping SSE headers.

## 6. CI Integration

Illustrative GitHub Actions step:

```yaml
- name: Run smoke test
  run: |
    gatekeeper init
    gatekeeper auth --flow device
    uv run python smoke_test.py --yes
  env:
    GATEKEEPER_GOOGLE_CLIENT_ID: ${{ secrets.GK_CLIENT_ID }}
    GATEKEEPER_GOOGLE_CLIENT_SECRET: ${{ secrets.GK_CLIENT_SECRET }}
```

This is **illustrative only** — running live Google API calls in CI requires a dedicated test account and secure secret handling.
