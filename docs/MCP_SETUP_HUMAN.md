# Gatekeeper MCP Setup — For Humans

This guide walks a **human administrator** through connecting an AI agent to Gatekeeper via MCP. If you're an AI agent reading this repo, see [MCP_SETUP_AGENT.md](MCP_SETUP_AGENT.md) instead.

---

## Prerequisites

Before connecting an agent, Gatekeeper must be running and authenticated with Google:

1. Gatekeeper server is running (`gatekeeper serve` or systemd)
2. Google OAuth is completed (`gatekeeper auth`)
3. You have at least one API key (`gatekeeper key list`)

### OAuth scopes required

Gatekeeper requests scopes based on which modules are enabled. For full coverage (all three modules), the following 7 scopes must be added to your Google Cloud project's **OAuth consent screen → Data Access**:

| Module | Scope | What it allows |
|--------|-------|----------------|
| **Drive** | `https://www.googleapis.com/auth/drive` | Read and write Drive files |
| **Gmail** | `https://www.googleapis.com/auth/gmail.modify` | Read, modify, and trash messages |
| **Gmail** | `https://www.googleapis.com/auth/gmail.send` | Send messages |
| **Gmail** | `https://www.googleapis.com/auth/gmail.compose` | Create and edit drafts |
| **Gmail** | `https://www.googleapis.com/auth/gmail.settings.basic` | Manage labels, filters, forwarding |
| **Calendar** | `https://www.googleapis.com/auth/calendar` | Read and write calendars |
| **Calendar** | `https://www.googleapis.com/auth/calendar.events` | Read and write events |

> **⚠️ If you skip adding scopes** to the consent screen, `gatekeeper auth` will succeed but you'll only get basic read-only access. Most API calls will then fail with `403 ACCESS_TOKEN_SCOPE_INSUFFICIENT`. See [SETUP.md](SETUP.md#3d--configure-the-oauth-consent-screen-and-scopes) for detailed setup instructions.

Verify with a health check:
```bash
curl http://localhost:8080/health
# {"status":"ok","version":"0.1.0"}
```

---

## Step 1 — Choose how the agent reaches Gatekeeper

Gatekeeper binds to `127.0.0.1:8080` by default. Choose based on where the agent runs:

| Agent location | URL to use | How |
|---|---|---|
| Same machine | `http://localhost:8080/mcp/sse` | Default — no config needed |
| LAN (different machine) | `http://10.0.x.x:8080/mcp/sse` | Set `GATEKEEPER_HOST=0.0.0.0` in `.env` and add the IP to `GATEKEEPER_MCP_ALLOWED_HOSTS` |
| Tailscale / VPN | `http://100.x.x.x:8080/mcp/sse` | Same as LAN — add the Tailscale IP to allowed hosts |
| Remote / internet | `https://your-domain.com/mcp/sse` | Use a reverse proxy with TLS |

### Allowed hosts configuration

For LAN/Tailscale access, edit `.env`:
```env
GATEKEEPER_HOST=0.0.0.0
GATEKEEPER_MCP_ALLOWED_HOSTS=["localhost:8080","127.0.0.1:8080","10.0.30.10:8080","100.127.113.87:8080"]
```

Then restart: `gatekeeper service restart` (or `systemctl --user restart gatekeeper`)

Or use the CLI:
```bash
gatekeeper hosts add 10.0.30.10:8080
gatekeeper hosts add 100.127.113.87:8080
```

> **Security**: Only the hosts in `GATEKEEPER_MCP_ALLOWED_HOSTS` can connect. This prevents DNS rebinding attacks. Default is `localhost` and `127.0.0.1` only.

---

## Step 2 — Create an API key for the agent

```bash
gatekeeper key create --name nova-agent
# 🔑 Key created: gkp_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890
```

Save this key — it's shown only once. Each agent should have its own key so you can revoke access individually.

For a read-only agent (no write/delete routes):
```bash
gatekeeper key create --name readonly-agent --permissions drive,gmail,calendar
```

---

## Step 3 — Enable the routes the agent needs

Go to **http://localhost:8080/admin/** and log in with your admin credentials.

- **Username**: `admin` (default)
- **Password**: check `gatekeeper_secrets.json` in your Gatekeeper directory

In the **Routes** page:
- Write routes (create, send, delete, update) are **disabled by default** — enable only what the agent needs
- Read routes (list, get, export) are **enabled by default**
- Changes take effect immediately — the agent sees new tools on next `list_tools`

---

## Step 4 — Configure the agent

### Claude Desktop / Cursor / Windsurf

Edit your MCP config file (location varies by app):

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

Then restart your agent's gateway:
```bash
hermes gateway restart
```

> **⚠️ Critical**: You MUST include `"transport": "sse"` (or `transport: sse` in YAML). Many MCP clients default to Streamable HTTP transport, which sends POST requests to the SSE endpoint and gets 405 errors. Gatekeeper's MCP server uses SSE transport.

---

## Step 5 — Verify the connection

After configuring, check that the agent can list Gatekeeper tools. You should see tools like:

- `drive__files_list` (if Drive is enabled)
- `gmail__messages_list` (if Gmail is enabled)
- `calendar__calendars_list` (if Calendar is enabled)

Each tool requires an `api_key` parameter — the agent passes it with every call.

### Quick connectivity test

```bash
# Test the SSE endpoint
curl -s http://10.0.30.10:8080/health
# {"status":"ok","version":"0.1.0"}

# Test the MCP endpoint (should return HTML or SSE stream)
curl -s http://10.0.30.10:8080/mcp/sse
# Should not return 404 or 405
```

---

## Step 6 — Understand how MCP tools map to routes

Gatekeeper converts each enabled route into an MCP tool. The naming convention:

| Route ID | MCP tool name |
|---|---|
| `drive.files.list` | `drive__files_list` |
| `gmail.messages.get` | `gmail__messages_get` |
| `calendar.events.create` | `calendar__events_create` |

Dots become double-underscores, and the module name is the prefix.

Every tool call requires an `api_key` parameter:
```json
{
  "name": "drive__files_list",
  "arguments": {
    "api_key": "gkp_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890",
    "page_size": 10
  }
}
```

If a route is disabled in the admin UI, the tool still appears in `list_tools` but calling it returns:
```json
{"error": true, "status": 403, "message": "Route calendar.events.create is disabled"}
```

---

## Security notes

- **API keys are hashed** — Gatekeeper stores bcrypt hashes, not plaintext keys
- **Keys can be scoped** — `--permissions drive` limits a key to Drive routes only
- **All calls are audited** — every request is logged with the key prefix, route, and status
- **Keys can be revoked** — `gatekeeper key revoke --prefix gkp_aBcDeFgH` immediately blocks the key
- **Admin routes require HTTP Basic Auth** — agents cannot modify policies, keys, or modules
- **Disabled routes return 403** — even if the tool exists, blocked routes refuse to execute

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Agent gets "Invalid API key" | Check that the key matches exactly (copy from `gatekeeper key list` output — only the prefix is stored) |
| Agent gets 405 Method Not Allowed | You're missing `transport: sse` in the config — Gatekeeper uses SSE, not Streamable HTTP |
| Agent gets "Route X is disabled" (403) | Go to Admin UI → Routes → enable the route |
| Agent can't connect | Check `GATEKEEPER_MCP_ALLOWED_HOSTS` includes the agent's origin; verify Gatekeeper is listening on the right interface (`0.0.0.0` for LAN) |
| Tools appear but calls fail with 401 | Google OAuth token may need refresh — run `gatekeeper auth` again |
| 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT | Missing OAuth scopes. Add the required scopes in the Google Cloud Console's **OAuth consent screen → Data Access** (see the scopes table above), then re-run `gatekeeper auth` |
| MCP tools not appearing | Verify `GATEKEEPER_MCP_ENABLED=true` in `.env` (default is true) |
| Connection drops after a while | SSE connections can time out — this is normal, the agent reconnects automatically |