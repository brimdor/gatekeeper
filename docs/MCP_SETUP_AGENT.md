# Gatekeeper MCP Setup — For AI Agents

You are an AI agent reading a repository that includes Gatekeeper — a policy gateway for Google Workspace APIs (Drive, Gmail, Calendar). This document tells you exactly how to connect to it via MCP.

---

## What is Gatekeeper?

Gatekeeper exposes Google Drive, Gmail, and Calendar as MCP tools. You call them like any other tool, and Gatekeeper enforces access policies between you and Google:

- **Read routes** (list, get, export) are **enabled by default**
- **Write routes** (create, send, update, delete) are **disabled by default** — a human admin must enable them
- Every call requires an API key and is audit-logged
- You cannot bypass disabled routes — they return `403`
- You cannot modify policies, keys, or admin settings — those require HTTP Basic Auth

---

## Prerequisites

Before you start, you need:

1. **The Gatekeeper URL** — e.g., `http://10.0.30.10:8080/mcp/sse` or `http://100.127.113.87:8080/mcp/sse`
2. **An API key** — starts with `gkp_`, provided by the human admin. Example: `gkp_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890`
3. **Which modules are enabled** — Drive, Gmail, Calendar (or a combination)

Ask your admin for these three things if you don't have them.

---

## Configuration

### For Hermes Agent

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

### For Claude Desktop / Cursor / other MCP clients

Edit your MCP config (location varies — typically `claude_desktop_config.json` or similar):

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

### ⚠️ You MUST set `transport: sse`

Gatekeeper uses SSE transport, not Streamable HTTP. If you omit this setting, most MCP clients default to Streamable HTTP and you'll get **405 Method Not Allowed** errors.

In YAML: `transport: sse`
In JSON: `"transport": "sse"`

---

## How to call Gatekeeper tools

Every tool requires an `api_key` parameter. Pass your API key with each call:

```
Tool: drive__files_list
Arguments: { "api_key": "gkp_...", "page_size": 10 }
```

The `api_key` parameter is automatically injected into every tool's schema — you'll see it listed in the tool definition.

---

## Available tools

Tool names follow the pattern: `{module}__{route_with_dots_replaced_by_double_underscore}`

### Drive tools

| Tool name | Maps to route | Default | What it does |
|---|---|---|---|
| `drive__files_list` | drive.files.list | ✅ On | Search and list files |
| `drive__files_get` | drive.files.get | ✅ On | Get file metadata by ID |
| `drive__files_export` | drive.files.export | ✅ On | Export Google Docs to PDF/DOCX/etc |
| `drive__files_list_shared` | drive.files.list_shared | ✅ On | List files shared with you |
| `drive__files_copy` | drive.files.copy | ❌ Off | Copy a file |
| `drive__files_create` | drive.files.create | ❌ Off | Create a new file |
| `drive__files_update` | drive.files.update | ❌ Off | Update file metadata/content |
| `drive__files_delete` | drive.files.delete | ❌ Off | Permanently delete a file |
| `drive__files_trash` | drive.files.trash | ❌ Off | Move a file to trash |
| `drive__permissions_list` | drive.permissions.list | ✅ On | List file permissions |
| `drive__permissions_get` | drive.permissions.get | ✅ On | Get a specific permission |
| `drive__permissions_create` | drive.permissions.create | ❌ Off | Share a file with someone |
| `drive__permissions_delete` | drive.permissions.delete | ❌ Off | Remove a permission |

### Gmail tools

| Tool name | Maps to route | Default | What it does |
|---|---|---|---|
| `gmail__messages_list` | gmail.messages.list | ✅ On | List messages (spam/trash filtered) |
| `gmail__messages_get` | gmail.messages.get | ✅ On | Get a message by ID |
| `gmail__messages_send` | gmail.messages.send | ❌ Off | Send an email |
| `gmail__drafts_list` | gmail.drafts.list | ✅ On | List drafts |
| `gmail__drafts_create` | gmail.drafts.create | ❌ Off | Create a draft |
| `gmail__labels_list` | gmail.labels.list | ✅ On | List all labels |

### Calendar tools

| Tool name | Maps to route | Default | What it does |
|---|---|---|---|
| `calendar__events_list` | calendar.events.list | ✅ On | List events on a calendar |
| `calendar__events_get` | calendar.events.get | ✅ On | Get a specific event |
| `calendar__events_create` | calendar.events.create | ❌ Off | Create an event |
| `calendar__events_update` | calendar.events.update | ❌ Off | Update an event |
| `calendar__events_delete` | calendar.events.delete | ❌ Off | Delete an event |
| `calendar__calendars_list` | calendar.calendars.list | ✅ On | List user's calendars |
| `calendar__calendarlist_list` | calendar.calendarlist.list | ✅ On | List calendar list entries |
| `calendar__freebusy_query` | calendar.freebusy.query | ✅ On | Check free/busy times |

❌ = Disabled by default. If you call a disabled tool, you'll get:
```json
{"error": true, "status": 403, "message": "Route drive.files.create is disabled"}
```
Ask your admin to enable it in the Gatekeeper Admin UI.

---

## Common parameters

### Drive

- `drive__files_list`: `query` (Drive search string), `page_size`, `order_by`
- `drive__files_get`: `file_id`, `fields`
- `drive__files_export`: `file_id`, `mime_type` (e.g., `application/pdf`)

### Gmail

- `gmail__messages_list`: `query` (Gmail search), `page_size`, `label_ids`
- `gmail__messages_get`: `message_id`, `fields`
- `gmail__labels_list`: no required parameters

### Calendar

- `calendar__events_list`: `calendar_id` (use `primary` for default), `time_min`, `time_max`, `page_size`
- `calendar__calendars_list`: no required parameters
- `calendar__calendarlist_list`: `page_size`
- `calendar__freebusy_query`: `time_min`, `time_max`, `calendar_ids` (array)

All tools also accept `api_key` as a parameter.

---

## Error responses

| Status | Meaning | What to do |
|---|---|---|
| 401 | Invalid or missing API key | Check your API key — is it the full key including the `gkp_` prefix? |
| 403 | Route is disabled | Ask the admin to enable the route in the Gatekeeper Admin UI |
| 401 | Google credentials not configured | The admin needs to run `gatekeeper auth` |
| 404 | Route not found | Check the tool name spelling — use double underscores `__` not dots |
| 502 | Google API error | Temporary upstream issue, try again |

---

## Security boundaries

As an agent, you **cannot**:
- Enable/disable routes
- Create, list, or revoke API keys
- Modify policy configurations
- Access the admin UI or API

These require HTTP Basic Auth (admin credentials). This is by design — Gatekeeper is a **policy gateway** that limits what you can do. Only the human administrator can change what's allowed.

---

## Connection troubleshooting

| Symptom | Fix |
|---|---|
| 405 Method Not Allowed | Add `transport: sse` to your MCP config |
| Connection refused | Check the URL — is Gatekeeper running? Try `curl http://HOST:8080/health` |
| "Invalid API key" | Verify the full key (including `gkp_` prefix) is in the `X-Gatekeeper-API-Key` header |
| "Route X is disabled" | Ask your admin to enable the route in the Gatekeeper Admin UI (`/admin/`) |
| "Google credentials not configured" | Tell the admin to run `gatekeeper auth` |
| Connection drops / timeouts | SSE connections can time out — the agent should reconnect automatically. Increase `timeout` in your config (try 120 seconds) |