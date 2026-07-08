# Gatekeeper MCP Setup — For Humans

This guide walks a **human administrator** through deploying and connecting an AI agent to Gatekeeper via MCP. If you're an AI agent reading this repo, see [MCP_SETUP_AGENT.md](MCP_SETUP_AGENT.md) instead.

---

## Choose your deployment method

| Method | Best for | One-liner |
|---|---|---|
| **Docker** (recommended) | Most users — isolated, reproducible | `docker run -d --name gatekeeper -p 8080:8080 -v gatekeeper-data:/data -e GATEKEEPER_GOOGLE_CLIENT_ID=your_id -e GATEKEEPER_GOOGLE_CLIENT_SECRET=*** ghcr.io/brimdor/gatekeeper:latest` |
| **Podman** | Daemonless containers | Same as Docker, replace `docker` with `podman` |
| **pip** | Quick local install | `pip install aigatekeeper && gatekeeper serve` |
| **uv** | Modern Python tooling | `uv tool install aigatekeeper && gatekeeper serve` |
| **Clone + run** | Developers | `git clone https://github.com/brimdor/gatekeeper && cd gatekeeper && gatekeeper serve` |

### Systemd (after any install above)

```bash
gatekeeper service install --scope user
gatekeeper service enable
gatekeeper service start
```

For the full walkthrough, see **[docs/SETUP.md](SETUP.md)**. For Podman/systemd deployment details, see **[docs/PODMAN_DEPLOYMENT.md](PODMAN_DEPLOYMENT.md)**.

---

## Prerequisites

Before connecting an agent:

1. Gatekeeper server is running (`gatekeeper serve` or systemd)
2. Google OAuth is completed (`gatekeeper auth`)
3. You have at least one API key (`gatekeeper key list`)

Verify with:

```bash
curl http://localhost:8080/health
# {"status":"ok","version":"0.1.0"}
```

---

## OAuth scopes required

Gatekeeper requests scopes based on which modules are enabled. For full coverage, add these scopes to your Google Cloud project's **OAuth consent screen → Data Access**:

| Module | Scope |
|---|---|
| **Drive** | `https://www.googleapis.com/auth/drive` |
| **Drive** | `https://www.googleapis.com/auth/spreadsheets` |
| **Drive** | `https://www.googleapis.com/auth/documents` |
| **Drive** | `https://www.googleapis.com/auth/presentations` |
| **Gmail** | `https://www.googleapis.com/auth/gmail.modify` |
| **Gmail** | `https://www.googleapis.com/auth/gmail.send` |
| **Gmail** | `https://www.googleapis.com/auth/gmail.compose` |
| **Gmail** | `https://www.googleapis.com/auth/gmail.settings.basic` |
| **Calendar** | `https://www.googleapis.com/auth/calendar` |
| **Calendar** | `https://www.googleapis.com/auth/calendar.events` |

The Drive scopes match `gatekeeper/modules/drive/__init__.py:required_scopes` exactly.

> **⚠️ If you skip adding scopes**, most API calls will fail with `403 ACCESS_TOKEN_SCOPE_INSUFFICIENT`. For the full step-by-step OAuth setup, see **[docs/SETUP.md](SETUP.md)** § Set up Google OAuth.

---

## Step 1 — Choose how the agent reaches Gatekeeper

| Agent location | URL to use |
|---|---|
| Same machine | `http://localhost:8080/mcp/sse` |
| LAN | `http://10.0.x.x:8080/mcp/sse` (set `GATEKEEPER_HOST=0.0.0.0`) |
| Tailscale / VPN | `http://100.x.x.x:8080/mcp/sse` |
| Remote / internet | `https://your-domain.com/mcp/sse` (use a reverse proxy with TLS) |

### Allowed hosts configuration

Edit `.env`:

```env
GATEKEEPER_HOST=0.0.0.0
GATEKEEPER_MCP_ALLOWED_HOSTS=["10.0.30.10:8080","100.127.113.87:8080"]
```

Then restart: `gatekeeper service restart`.

Or use the CLI:

```bash
gatekeeper hosts add 10.0.30.10:8080
gatekeeper hosts add 100.127.113.87:8080
```

> **Security**: Only hosts in `GATEKEEPER_MCP_ALLOWED_HOSTS` can connect. Default is `localhost` and `127.0.0.1` only.

---

## Step 2 — Create an API key for the agent

```bash
gatekeeper key create --name nova-agent
# 🔑 Key created: gkp_...
```

Save the key — it's shown only once. Each agent should have its own key.

For module-restricted access:

```bash
gatekeeper key create --name drive-only --permissions drive
```

The `permissions` value is a comma-separated list of module names or `*` for all.

---

## Step 3 — Enable the routes the agent needs

Go to **http://localhost:8080/admin/** and log in:

- **Username**: `admin` (default)
- **Password**: check `gatekeeper_secrets.json`

In the **Modules** page:
- Write routes (create, send, delete, update) are **disabled by default**.
- Read routes (list, get, export) are **enabled by default**.
- Changes take effect immediately — the agent sees new tools on the next `list_tools`.

The canonical route table is at [docs/ROUTES.md](ROUTES.md).

---

## Step 4 — Configure the agent

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

> **⚠️ Critical**: You MUST include `"transport": "sse"`. Without it, you'll get 405 errors.

---

## Step 5 — Verify the connection

After configuring, check that the agent can list Gatekeeper tools. You should see tools like:

- `drive__files_list` (if Drive is enabled)
- `gmail__messages_list` (if Gmail is enabled)
- `calendar__calendars_list` (if Calendar is enabled)

Each tool requires an `api_key` parameter.

### Quick connectivity test

```bash
curl -s http://10.0.30.10:8080/health
# {"status":"ok","version":"0.1.0"}

curl -s http://10.0.30.10:8080/mcp/sse
# Should not return 404 or 405
```

---

## Step 6 — Understand how MCP tools map to routes

| Route ID | MCP tool name |
|---|---|
| `drive.files.list` | `drive__files_list` |
| `gmail.messages.get` | `gmail__messages_get` |
| `calendar.events.create` | `calendar__events_create` |

Dots become double-underscores. Every tool call requires an `api_key` parameter. If a route is disabled, it **will not appear** in `list_tools`.

---

## Security notes

- **API keys are hashed** with bcrypt.
- **Keys can be scoped** to specific modules.
- **All calls are audited**.
- **Keys can be revoked** immediately.
- **Admin routes require HTTP Basic Auth** — agents cannot modify policies, keys, or modules.
- **Disabled routes return 403.**

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Agent gets "Invalid API key" | Verify the full key matches exactly |
| Agent gets 405 Method Not Allowed | Add `transport: sse` to the MCP config |
| Agent gets "Route X is disabled" (403) | Enable the route in the Admin UI |
| Agent can't connect | Check `GATEKEEPER_MCP_ALLOWED_HOSTS` and that Gatekeeper listens on `0.0.0.0` for LAN |
| Tools appear but calls fail with 401 | Run `gatekeeper auth` to refresh the token |
| 403 `ACCESS_TOKEN_SCOPE_INSUFFICIENT` | Add missing scopes in Google Cloud Console, then re-run `gatekeeper auth` |
| MCP tools not appearing | Verify `GATEKEEPER_MCP_ENABLED=true` |
| Connection drops after a while | SSE connections time out — agents reconnect automatically |

For error-handling details, see [docs/AGENT_ERRORS.md](AGENT_ERRORS.md).
