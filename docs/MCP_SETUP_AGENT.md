# Gatekeeper MCP Setup — For AI Agents

You are an AI agent that has connected to a repository containing **Gatekeeper** — a policy gateway for Google Workspace APIs (Drive, Gmail, Calendar). This document tells you exactly how to set up and use the Gatekeeper MCP server.

---

## What is Gatekeeper?

Gatekeeper sits between you and Google's APIs. You call MCP tools, Gatekeeper enforces policies:

- Every call requires an **API key** and is audit-logged
- Some routes may be disabled — calling them returns `403`
- You **cannot bypass** disabled routes
- You **cannot modify** policies, keys, or admin settings — those require HTTP Basic Auth
- **Always list available tools first** — do not assume any route is enabled or disabled. Routes are toggled by the human admin, and you must discover what's available by calling `list_tools`.

---

## Step 1 — Get your connection details from the admin

Ask the human administrator for three things:

1. **Gatekeeper URL** — e.g., `http://10.0.30.10:8080/mcp/sse` (LAN) or `http://100.127.113.87:8080/mcp/sse` (Tailscale)
2. **API key** — starts with `gkp_`, e.g., `gkp_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890`
3. **Which modules are enabled** — Drive, Gmail, Calendar (or a combination)

You cannot proceed without these. The API key is required for every tool call.

---

## Step 2 — Add Gatekeeper to your MCP config

### Hermes Agent

Edit `~/.hermes/profiles/<profile>/config.yaml`:

```yaml
mcp_servers:
  gatekeeper:
    url: http://10.0.30.10:8080/mcp/sse
    transport: sse
    headers:
      X-Gatekeeper-API-Key: gkp_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890
    timeout: 120
    connect_timeout: 15
```

Then restart: `hermes gateway restart`

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or the equivalent path on your OS:

```json
{
  "mcpServers": {
    "gatekeeper": {
      "url": "http://10.0.30.10:8080/mcp/sse",
      "transport": "sse",
      "headers": {
        "X-Gatekeeper-API-Key": "gkp_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890"
      }
    }
  }
}
```

### Cursor / Windsurf / Other MCP clients

The format is the same JSON as Claude Desktop above. Place it in your client's MCP config file with the `transport: sse` and `X-Gatekeeper-API-Key` header.

### ⚠️ You MUST set `transport: sse`

Gatekeeper uses SSE transport. Most MCP clients default to Streamable HTTP. Without `transport: sse`, you will get **405 Method Not Allowed** errors on every call.

- YAML: `transport: sse`
- JSON: `"transport": "sse"`

---

## Step 3 — Verify the connection

After configuring, check:

1. **Health endpoint**: `curl http://HOST:8080/health` should return `{"status":"ok","version":"0.1.0"}`
2. **Tool discovery**: Call `list_tools` to see what's available. This is your source of truth — do not assume any tool exists or is usable.
3. **Test a call**: Try listing calendars or files to confirm the connection works.

---

## How to call tools

Every Gatekeeper tool requires an `api_key` parameter. Pass your API key with each call.

### Example: List Drive files

```
Tool: drive__files_list
Arguments: { "api_key": "gkp_...", "page_size": 10 }
```

### Example: Get a Drive file by ID

```
Tool: drive__files_get
Arguments: { "api_key": "gkp_...", "file_id": "1abc..." }
```

### Example: List Gmail messages

```
Tool: gmail__messages_list
Arguments: { "api_key": "gkp_...", "page_size": 5, "query": "is:unread" }
```

### Example: List calendar events

```
Tool: calendar__events_list
Arguments: { "api_key": "gkp_...", "calendar_id": "primary", "time_min": "2025-01-01T00:00:00Z", "time_max": "2025-01-31T23:59:59Z" }
```

### Example: Create a file

```
Tool: drive__files_create
Arguments: { "api_key": "gkp_...", "name": "meeting-notes.txt", "mime_type": "text/plain" }
```

### Example: Delete a file

```
Tool: drive__files_delete
Arguments: { "api_key": "gkp_...", "file_id": "1abc..." }
```

If a tool returns `403`, that route is disabled. Ask the admin to enable it — you cannot enable it yourself.

---

## Tool name mapping

Tool names follow the pattern: `{module}__{route_suffix}`

Dots in the route ID become double underscores. Examples:

| Route ID | MCP tool name |
|---|---|
| `drive.files.list` | `drive__files_list` |
| `gmail.messages.get` | `gmail__messages_get` |
| `calendar.events.create` | `calendar__events_create` |
| `calendar.freebusy.query` | `calendar__freebusy_query` |

---

## Possible tools

Gatekeeper can expose tools from three modules. **Call `list_tools` to see which ones are actually available** — the admin decides which routes are enabled.

### Drive module
`drive__files_list`, `drive__files_get`, `drive__files_export`, `drive__files_list_shared`, `drive__files_copy`, `drive__files_create`, `drive__files_update`, `drive__files_delete`, `drive__files_trash`, `drive__permissions_list`, `drive__permissions_get`, `drive__permissions_create`, `drive__permissions_delete`

### Gmail module
`gmail__messages_list`, `gmail__messages_get`, `gmail__messages_send`, `gmail__drafts_list`, `gmail__drafts_create`, `gmail__labels_list`

### Calendar module
`calendar__events_list`, `calendar__events_get`, `calendar__events_create`, `calendar__events_update`, `calendar__events_delete`, `calendar__calendars_list`, `calendar__calendarlist_list`, `calendar__freebusy_query`

---

## Error responses

| Status | Meaning | What to do |
|---|---|---|
| 401 | Invalid or missing API key | Check your API key — must include the `gkp_` prefix and be the full key |
| 403 | Route is disabled | Ask the admin to enable the route. Do not retry — it will keep failing until they enable it. |
| 401 | Google credentials not configured | The admin needs to run `gatekeeper auth` |
| 404 | Route not found | Check the tool name — use `__` (double underscore) not `.` (dot) |
| 502 | Google API error | Temporary upstream issue, retry after a moment |

---

## Security boundaries

As an agent, you **cannot**:
- Enable or disable routes
- Create, list, or revoke API keys
- Modify policy configurations
- Access the admin UI or admin API

These require HTTP Basic Auth (admin credentials). This is by design — Gatekeeper is a **policy gateway** that constrains what you can do. Only the human administrator can change what's allowed.

---

## Connection troubleshooting

| Symptom | Fix |
|---|---|
| 405 Method Not Allowed | Add `transport: sse` to your MCP config |
| Connection refused | Is Gatekeeper running? Try `curl http://HOST:8080/health` |
| "Invalid API key" | Verify the full key (including `gkp_` prefix) is in the `X-Gatekeeper-API-Key` header or `api_key` parameter |
| "Route X is disabled" (403) | Ask your admin to enable the route. You cannot bypass this. |
| "Google credentials not configured" | Tell the admin to run `gatekeeper auth` |
| Connection drops / timeouts | SSE connections can time out. Increase `timeout` to 120 seconds. Most agents reconnect automatically. |