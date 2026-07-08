# Gatekeeper MCP Setup — For AI Agents

You are an AI agent that has connected to a repository containing **Gatekeeper** — a policy gateway for Google Workspace APIs (Drive, Gmail, Calendar). This document tells you how to set up and use the Gatekeeper MCP server.

**See also:** [AGENT_ERRORS.md](AGENT_ERRORS.md) for the full error recovery playbook, [ARCHITECTURE.md](ARCHITECTURE.md) § Request Flow for design details, [API_REFERENCE.md](API_REFERENCE.md) for the REST API surface.

---

## Setup Decision Tree

When a human asks you to set up Gatekeeper, **do not assume the deployment method**. Ask what environment they want to run it in.

| Option | When to recommend | User needs |
|---|---|---|
| **Docker** (recommended) | User has Docker or Podman | Docker/Podman + Google OAuth credentials |
| **pip / uv** | Quick local install | Python 3.11+ + Google OAuth credentials |
| **Clone + run** | Wants to modify code | git + Python 3.11+ + Google OAuth credentials |
| **systemd service** | 24/7 background service | systemd + one of the above |

### Docker one-liner (fastest)

```bash
docker run -d --name gatekeeper \
  -p 8080:8080 \
  -v gatekeeper-data:/data \
  -e GATEKEEPER_GOOGLE_CLIENT_ID=your_id \
  -e GATEKEEPER_GOOGLE_CLIENT_SECRET=your_secret \
  -e GATEKEEPER_DRIVE_ENABLED=true \
  -e GATEKEEPER_GMAIL_ENABLED=true \
  ghcr.io/brimdor/gatekeeper:latest
```

Then:

```bash
docker exec -it gatekeeper gatekeeper auth
docker exec gatekeeper cat /data/gatekeeper_secrets.json | grep admin_password
docker exec gatekeeper gatekeeper key create --name my-agent
```

### pip one-liner

```bash
pip install aigatekeeper  # or: uv tool install aigatekeeper
cp .env.example .env       # edit with Google OAuth credentials
gatekeeper init
gatekeeper auth
gatekeeper key create --name my-agent
gatekeeper serve
```

### Full setup guide

For the complete step-by-step walkthrough (Google Cloud Console setup, OAuth scopes, admin UI), see **[docs/SETUP.md](SETUP.md)**.

---

## What is Gatekeeper?

Gatekeeper sits between you and Google's APIs. You call MCP tools; Gatekeeper enforces policies:

- Every call requires an **API key** and is audit-logged.
- Some routes may be disabled — calling them returns `403`.
- You **cannot bypass** disabled routes.
- You **cannot modify** policies, keys, or admin settings — those require HTTP Basic Auth.
- **Always call `list_tools` first** — the admin decides which routes are enabled, and tool availability changes when routes are toggled.
- **Disabled routes do NOT appear in `list_tools`.**

For the architecture and request flow, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Step 1 — Get your connection details from the admin

Ask the human administrator for three things:

1. **Gatekeeper URL** — e.g., `http://10.0.30.10:8080/mcp/sse`
2. **API key** — starts with `gkp_`
3. **Which modules are enabled** — Drive, Gmail, Calendar

The API key is required for every tool call.

---

## Step 2 — Add Gatekeeper to your MCP config

### Hermes Agent

```yaml
mcp_servers:
  gatekeeper:
    url: http://10.0.30.10:8080/mcp/sse
    transport: sse
    headers:
      X-Gatekeeper-API-Key: gkp_...
    timeout: 120
    connect_timeout: 15
```

Then restart: `hermes gateway restart`.

### Claude Desktop / Cursor / Windsurf

```json
{
  "mcpServers": {
    "gatekeeper": {
      "url": "http://10.0.30.10:8080/mcp/sse",
      "transport": "sse",
      "headers": {
        "X-Gatekeeper-API-Key": "gkp_..."
      }
    }
  }
}
```

### ⚠️ You MUST set `transport: sse`

Gatekeeper uses SSE transport. Without `transport: sse`, you will get **405 Method Not Allowed** errors.

---

## Step 3 — Verify the connection

1. **Health endpoint:** `curl http://HOST:8080/health` should return `{"status":"ok","version":"0.1.0"}`.
2. **Tool discovery:** Call `list_tools` to see what's available. This is your source of truth.
3. **Test a call:** Try `drive__files_list` or `calendar__events_list`.

---

## Discover parameters at runtime

**Do not hard-code parameter lists.** The authoritative parameter schema for each tool comes from `list_tools`. Call it and read the `inputSchema` for the tool you want to use.

For a static reference of all 174 routes, their full schemas, and required OAuth scopes, see [docs/ROUTES.md](ROUTES.md). The runtime schema from `list_tools` is authoritative if the two differ.

---

## How to call tools

Every Gatekeeper tool requires an `api_key` parameter.

### Examples

| Tool | Arguments |
|---|---|
| `drive__files_list` | `{ "api_key": "gkp_...", "page_size": 10 }` |
| `drive__files_get` | `{ "api_key": "gkp_...", "file_id": "1abc..." }` |
| `gmail__messages_list` | `{ "api_key": "gkp_...", "page_size": 5, "q": "is:unread" }` |
| `calendar__events_list` | `{ "api_key": "gkp_...", "calendar_id": "primary" }` |
| `drive__files_create` | `{ "api_key": "gkp_...", "name": "notes.txt", "mime_type": "text/plain" }` |

If a tool returns `403`, that route is disabled. Ask the admin to enable it.

---

## Tool name mapping

Tool names follow the pattern: `{module}__{route_suffix}`

Dots in the route ID become double underscores:

| Route ID | MCP tool name |
|---|---|
| `drive.files.list` | `drive__files_list` |
| `gmail.messages.get` | `gmail__messages_get` |
| `calendar.freebusy.query` | `calendar__freebusy_query` |

Source: `gatekeeper/mcp_server/__init__.py:153-161`.

---

## Available modules

Gatekeeper can expose tools from three modules. Call `list_tools` to see which routes are actually enabled.

- **Drive** — 83 routes (36 enabled by default). See [ROUTES.md](ROUTES.md) for the full list.
- **Gmail** — 53 routes (16 enabled by default).
- **Calendar** — 38 routes (13 enabled by default).

The canonical route table is at [docs/ROUTES.md](ROUTES.md); the REST API reference is at [docs/API_REFERENCE.md](API_REFERENCE.md).

---

## Error responses

Common codes and quick actions:

| Status | Meaning | What to do |
|---|---|---|
| **401** | Missing or invalid API key | Verify the full key including `gkp_` prefix. |
| **403** | Route disabled or key lacks module permission | Call `list_tools` to confirm; ask the admin. |
| **421** | DNS rebinding protection rejected the host | Ask the admin to run `gatekeeper hosts add`. |

For the full error table, retry policy, 421 deep dive, and debugging checklist, see **[AGENT_ERRORS.md](AGENT_ERRORS.md)**.

---

## Security boundaries

As an agent, you **cannot**:

- Enable or disable routes.
- Create, list, or revoke API keys.
- Modify policy configurations.
- Access the admin UI or admin API.

These require HTTP Basic Auth (admin credentials). Gatekeeper is a policy gateway that constrains what you can do.

---

## Connection troubleshooting

| Symptom | Fix |
|---|---|
| 405 Method Not Allowed | Add `transport: sse` to your MCP config |
| Connection refused | Check `curl http://HOST:8080/health` |
| "Invalid API key" | Verify the full key is in the header or `api_key` parameter |
| "Route X is disabled" (403) | Ask the admin to enable the route |
| "Google credentials not configured" | Tell the admin to run `gatekeeper auth` |
| 403 `ACCESS_TOKEN_SCOPE_INSUFFICIENT` | Admin must add missing scopes in Google Cloud Console's **OAuth consent screen → Data Access**, then re-run `gatekeeper auth` |
| Connection drops / timeouts | Increase `timeout` to 120 seconds |
| DNS rebinding / 421 | See [AGENT_ERRORS.md](AGENT_ERRORS.md) §5 or ask the admin to run `gatekeeper hosts add` |

For transport-level details, see `gatekeeper/mcp_server/__init__.py:27-59` and `gatekeeper/mcp_server/transport.py`.
