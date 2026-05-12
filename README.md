# Gatekeeper 🔐

Policy gateway for Google Workspace APIs with MCP server integration. Fine-grained control over what AI agents can do with your Google Drive, Gmail, and Calendar.

## Overview

Google's OAuth scopes are all-or-nothing within a service. `gmail.modify` gives full read/write/modify on all of Gmail—there's no way to say "read-only access to this label" or "only create calendar events, don't delete them."

**Gatekeeper** sits between your AI agents and Google's APIs, acting as a policy layer that lets you:

- **Enable/disable individual routes** — turn off `gmail.messages.send` but keep `gmail.messages.list`
- **Cap limits** — restrict `maxResults` to 50, limit recipients to 5
- **Filter data** — exclude SPAM/TRASH labels from Gmail results, block sensitive fields
- **Audit everything** — every request is logged with key, route, status, and timestamp
- **Expose as MCP tools** — agents discover only what you've enabled via the MCP server

```
┌──────────────┐   API Key    ┌──────────────────────────┐   OAuth2    ┌──────────┐
│  AI Agent    │──────────────│       Gatekeeper           │────────────│  Google  │
│  (Nova etc)  │              │                            │            │  APIs    │
│              │   MCP (SSE)  │  ┌────────────────────┐   │            │          │
│              │──────────────│  │   Policy Engine    │   │            └──────────┘
└──────────────┘              │  │  (allow/deny/      │   │
                              │  │   transform)       │   │
                              │  └────────────────────┘   │
                              │                            │
                              │  ┌────────────────────┐   │
                              │  │   Admin WebUI      │   │
                              │  │  /admin (HTMX)     │   │
                              │  └────────────────────┘   │
                              └──────────────────────────┘
```

## Quick Start

```bash
# Install with uv
uv pip install -e .

# Initialize the database and seed default policies
gatekeeper init

# Authorize with Google (opens browser)
gatekeeper auth

# Start the server
gatekeeper serve
```

## Configuration

All configuration is via environment variables (prefix `GATEKEEPER_`) or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEKEEPER_HOST` | `127.0.0.1` | Host to bind to |
| `GATEKEEPER_PORT` | `8080` | Port to bind to |
| `GATEKEEPER_DEBUG` | `false` | Enable debug mode |
| `GATEKEEPER_DATABASE_URL` | `sqlite+aiosqlite:///./gatekeeper.db` | Database URL |
| `GATEKEEPER_SECRET_KEY` | *(auto-generated)* | Secret key for sessions |
| `GATEKEEPER_ENCRYPTION_KEY` | *(auto-generated)* | Fernet key for token encryption |
| `GATEKEEPER_ADMIN_USERNAME` | `admin` | Admin UI username |
| `GATEKEEPER_ADMIN_PASSWORD` | *(auto-generated)* | Admin UI password |
| `GATEKEEPER_API_KEY_PREFIX` | `gkp_` | Prefix for API keys |
| `GATEKEEPER_MCP_ENABLED` | `true` | Enable MCP server |
| `GATEKEEPER_GOOGLE_CLIENT_ID` | *(required)* | Google OAuth client ID |
| `GATEKEEPER_GOOGLE_CLIENT_SECRET` | *(required)* | Google OAuth client secret |
| `GATEKEEPER_GOOGLE_TOKEN_FILE` | `./google_token.json` | Encrypted token file path |
| `GATEKEEPER_DRIVE_ENABLED` | `false` | Enable Drive module |
| `GATEKEEPER_GMAIL_ENABLED` | `false` | Enable Gmail module |
| `GATEKEEPER_CALENDAR_ENABLED` | `false` | Enable Calendar module |
| `GATEKEEPER_CORS_ORIGINS` | `["http://localhost:8080"]` | CORS allowed origins |

## Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the APIs you need: Drive, Gmail, Calendar
4. Go to **APIs & Services → Credentials**
5. Create an **OAuth 2.0 Client ID** (Desktop app type)
6. Copy the Client ID and Client Secret
7. Set environment variables:
   ```bash
   export GATEKEEPER_GOOGLE_CLIENT_ID="your-client-id"
   export GATEKEEPER_GOOGLE_CLIENT_SECRET="your-client-secret"
   ```
8. Run `gatekeeper auth` to authorize

## API Keys

```bash
# Create a key with full access
gatekeeper key create --name "my-agent"

# Create a key with limited module access
gatekeeper key create --name "drive-only" --permissions "drive"

# List keys
gatekeeper key list

# Revoke a key
gatekeeper key revoke --prefix gkp_a1b2c3d4
```

Keys are prefixed with `gkp_` and the full key is only shown once on creation.

## Admin UI

Access the admin UI at `http://localhost:8080/admin/` with HTTP Basic Auth (username from `GATEKEEPER_ADMIN_USERNAME`, password printed on first `gatekeeper init`).

The UI provides:
- **Dashboard** — overview of requests, keys, and auth status
- **Modules** — enable/disable Drive, Gmail, Calendar
- **Routes** — toggle individual routes and configure policies
- **API Keys** — create, list, and revoke keys
- **Audit Log** — searchable log of all requests
- **Auth Status** — Google OAuth connection status

## Using with AI Agents

Gatekeeper exposes an MCP server (SSE transport) at `/mcp`. Configure your agent to connect:

```json
{
  "mcpServers": {
    "gatekeeper": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "X-Gatekeeper-API-Key": "gkp_your_key_here"
      }
    }
  }
}
```

When you enable a route in the admin UI, the agent automatically discovers it as a new tool. Disable it, and the tool disappears.

## Module Reference

### Drive (5 routes)

| Route | Method | Default | Policy |
|-------|--------|---------|--------|
| `drive.files.list` | GET | ✅ On | max_results=50 |
| `drive.files.get` | GET | ✅ On | — |
| `drive.files.export` | GET | ✅ On | — |
| `drive.files.list_shared` | GET | ✅ On | max_results=50, query_filter=sharedWithMe=true |
| `drive.files.copy` | POST | ❌ Off | — |

### Gmail (6 routes)

| Route | Method | Default | Policy |
|-------|--------|---------|--------|
| `gmail.messages.list` | GET | ✅ On | max_results=50, allowed_labels, exclude SPAM/TRASH |
| `gmail.messages.get` | GET | ✅ On | — |
| `gmail.messages.send` | POST | ❌ Off | max_recipients=5 |
| `gmail.drafts.list` | GET | ✅ On | max_results=50 |
| `gmail.drafts.create` | POST | ❌ Off | max_recipients=5 |
| `gmail.labels.list` | GET | ✅ On | — |

### Calendar (8 routes)

| Route | Method | Default | Policy |
|-------|--------|---------|--------|
| `calendar.events.list` | GET | ✅ On | max_results=50 |
| `calendar.events.get` | GET | ✅ On | — |
| `calendar.events.create` | POST | ❌ Off | — |
| `calendar.events.update` | PATCH | ❌ Off | — |
| `calendar.events.delete` | DELETE | ❌ Off | — |
| `calendar.calendars.list` | GET | ✅ On | — |
| `calendar.calendarlist.list` | GET | ✅ On | max_results=50 |
| `calendar.freebusy.query` | POST | ✅ On | — |

## Policy Configuration

Each route has a JSON policy config that controls:

- **max_results** — cap the number of results returned
- **allowed_labels** — only allow these Gmail labels
- **exclude_labels** — filter out these Gmail labels
- **blocked_fields** — strip these fields from responses
- **max_items** — cap array lengths in responses
- **query_filter** — force a Drive query parameter
- **max_recipients** — limit email recipients

Edit policies via the admin UI or the REST API:
```bash
curl -u admin:password -X PATCH http://localhost:8080/admin/api/routes/1 \
  -H "Content-Type: application/json" \
  -d '{"enabled": false, "policy_config": {"max_results": 25}}'
```

## Container Deployment (Podman)

```bash
# Build
podman build -t gatekeeper .

# Run with compose
podman-compose up -d

# Or run directly
podman run -d \
  -p 8080:8080 -p 8081:8081 \
  -v ./data:/data \
  -e GATEKEEPER_GOOGLE_CLIENT_ID="$GATEKEEPER_GOOGLE_CLIENT_ID" \
  -e GATEKEEPER_GOOGLE_CLIENT_SECRET="$GATEKEEPER_GOOGLE_CLIENT_SECRET" \
  gatekeeper
```

The `data/` directory persists the SQLite database and Google token across container restarts.

For Raspberry Pi: the Dockerfile supports `linux/arm64` — Podman will build the correct architecture automatically.

## Security

- **TLS**: Use a reverse proxy (Caddy/nginx) for HTTPS in production
- **API Keys**: bcrypt-hashed, prefix-based lookup, revocable
- **Token Encryption**: Google OAuth refresh tokens encrypted at rest with Fernet
- **Network**: Binds `127.0.0.1` by default — only accessible locally unless explicitly configured
- **CORS**: Configurable via `GATEKEEPER_CORS_ORIGINS`
- **Admin Auth**: HTTP Basic Auth with auto-generated credentials

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
uv run pytest tests/ -v

# Run linter
uv run ruff check gatekeeper/
```

## License

MIT