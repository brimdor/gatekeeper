# Gatekeeper MCP Setup — For AI Agents

You are an AI agent that has connected to a repository containing **Gatekeeper** — a policy gateway for Google Workspace APIs (Drive, Gmail, Calendar). This document tells you exactly how to set up and use the Gatekeeper MCP server.

---

## What is Gatekeeper?

Gatekeeper sits between you and Google's APIs. You call MCP tools, Gatekeeper enforces policies:

- **Read routes** (list, get, export) are **enabled by default**
- **Write routes** (create, send, update, delete) are **disabled by default** — only a human admin can enable them
- Every call requires an **API key** and is audit-logged
- You **cannot bypass** disabled routes — they return `403`
- You **cannot modify** policies, keys, or admin settings — those require HTTP Basic Auth

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
2. **Tool discovery**: Your MCP client should list Gatekeeper tools (e.g., `drive__files_list`, `gmail__messages_list`, `calendar__calendars_list`)
3. **Test a read call**: Try listing calendars or files — these are enabled by default

---

## How to call tools

Every Gatekeeper tool requires an `api_key` parameter. This is the `gkp_...` key the admin gave you.

### Example: List Drive files

```
Tool: drive__files_list
Arguments: {
  "api_key": "gkp_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890",
  "page_size": 10
}
```

Returns:
```json
{
  "files": [
    {"id": "1abc...", "name": "Report.pdf", "mimeType": "application/pdf"},
    {"id": "2def...", "name": "Notes.docx", "mimeType": "application/vnd.google-apps.document"}
  ]
}
```

### Example: Get a Drive file by ID

```
Tool: drive__files_get
Arguments: {
  "api_key": "gkp_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890",
  "file_id": "1abc..."
}
```

### Example: List Gmail messages

```
Tool: gmail__messages_list
Arguments: {
  "api_key": "gkp_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890",
  "page_size": 5,
  "query": "is:unread"
}
```

### Example: List calendar events

```
Tool: calendar__events_list
Arguments: {
  "api_key": "gkp_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890",
  "calendar_id": "primary",
  "time_min": "2025-01-01T00:00:00Z",
  "time_max": "2025-01-31T23:59:59Z"
}
```

### Example: Create a file (if enabled)

```
Tool: drive__files_create
Arguments: {
  "api_key": "gkp_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890",
  "name": "meeting-notes.txt",
  "mime_type": "text/plain"
}
```

### Example: Delete a file (if enabled)

```
Tool: drive__files_delete
Arguments: {
  "api_key": "gkp_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890",
  "file_id": "1abc..."
}
```

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

## All available tools

### Drive

| Tool | Default | What it does | Key parameters |
|---|---|---|---|
| `drive__files_list` | ✅ On | Search and list files | `query`, `page_size`, `order_by` |
| `drive__files_get` | ✅ On | Get file metadata by ID | `file_id`, `fields` |
| `drive__files_export` | ✅ On | Export Google Docs to PDF/DOCX | `file_id`, `mime_type` |
| `drive__files_list_shared` | ✅ On | List files shared with you | `page_size` |
| `drive__files_copy` | ❌ Off | Copy a file | `file_id`, `name` |
| `drive__files_create` | ❌ Off | Create a new file | `name`, `mime_type`, `parents` |
| `drive__files_update` | ❌ Off | Update file metadata | `file_id` |
| `drive__files_delete` | ❌ Off | Permanently delete a file | `file_id` |
| `drive__files_trash` | ❌ Off | Move file to trash (recoverable) | `file_id` |
| `drive__permissions_list` | ✅ On | List who has access to a file | `file_id` |
| `drive__permissions_get` | ✅ On | Get a specific permission | `file_id`, `permission_id` |
| `drive__permissions_create` | ❌ Off | Share a file with someone | `file_id`, `email` |
| `drive__permissions_delete` | ❌ Off | Remove someone's access | `file_id`, `permission_id` |

### Gmail

| Tool | Default | What it does | Key parameters |
|---|---|---|---|
| `gmail__messages_list` | ✅ On | List messages (spam/trash filtered) | `query`, `page_size`, `label_ids` |
| `gmail__messages_get` | ✅ On | Get a message by ID | `message_id`, `fields` |
| `gmail__messages_send` | ❌ Off | Send an email | `raw` (base64) |
| `gmail__drafts_list` | ✅ On | List drafts | `page_size` |
| `gmail__drafts_create` | ❌ Off | Create a draft | `message` |
| `gmail__labels_list` | ✅ On | List all labels | (none) |

### Calendar

| Tool | Default | What it does | Key parameters |
|---|---|---|---|
| `calendar__events_list` | ✅ On | List events on a calendar | `calendar_id` (use `primary`), `time_min`, `time_max`, `page_size` |
| `calendar__events_get` | ✅ On | Get a specific event | `event_id`, `calendar_id` |
| `calendar__events_create` | ❌ Off | Create an event | `calendar_id`, `summary`, `start`, `end` |
| `calendar__events_update` | ❌ Off | Update an event | `event_id`, `calendar_id` |
| `calendar__events_delete` | ❌ Off | Delete an event | `event_id`, `calendar_id` |
| `calendar__calendars_list` | ✅ On | List user's calendars | (none) |
| `calendar__calendarlist_list` | ✅ On | List calendar list entries | `page_size` |
| `calendar__freebusy_query` | ✅ On | Check free/busy times | `time_min`, `time_max`, `calendar_ids` (array) |

**❌ Off** = Disabled by default. If you call a disabled tool, you'll get:
```json
{"error": true, "status": 403, "message": "Route drive.files.create is disabled"}
```
Ask your admin to enable it. You cannot enable it yourself.

---

## Error responses

| Status | Meaning | What to do |
|---|---|---|
| 401 | Invalid or missing API key | Check your API key — must include the `gkp_` prefix and be the full key |
| 403 | Route is disabled | Ask the admin to enable the route in the Gatekeeper Admin UI |
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
| "Route X is disabled" (403) | This is normal for write routes. Ask your admin to enable it |
| "Google credentials not configured" | Tell the admin to run `gatekeeper auth` |
| Connection drops / timeouts | SSE connections can time out. Increase `timeout` to 120 seconds. Most agents reconnect automatically |