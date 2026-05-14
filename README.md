# Gatekeeper 🔐

[![CI](https://github.com/brimdor/gatekeeper/actions/workflows/ci.yml/badge.svg)](https://github.com/brimdor/gatekeeper/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

**Policy gateway for Google Workspace APIs** — fine-grained control over what AI agents can do with your Google Drive, Gmail, and Calendar. Exposes enabled routes as MCP tools so agents discover and call only what you allow.

## Why Gatekeeper?

Google's OAuth scopes are all-or-nothing. `gmail.modify` gives full read/write/delete on everything. There's no way to say "read-only this label" or "create events but never delete them."

Gatekeeper sits between your AI agents and Google's APIs, acting as a policy layer:

- **Enable/disable individual routes** — turn off `gmail.messages.send` but keep `gmail.messages.list`
- **Cap limits** — restrict `maxResults` to 50, limit recipients to 5
- **Filter data** — exclude SPAM/TRASH from Gmail, block sensitive fields
- **Audit everything** — every request logged with key, route, status, timestamp
- **MCP server** — agents discover only enabled routes as tools, auto-updating when you toggle routes in the admin UI

```
┌──────────────┐   API Key    ┌──────────────────────────┐   OAuth2    ┌──────────┐
│  AI Agent    │──────────────│       Gatekeeper           │────────────│  Google  │
│  (Nova etc)  │              │                            │            │  APIs    │
│              │   MCP (SSE)  │  ┌────────────────────┐   │            └──────────┘
│              │──────────────│  │   Policy Engine    │   │
└──────────────┘              │  │  (allow/deny/      │   │
                              │  │   transform)       │   │
                              │  └────────────────────┘   │
                              │                            │
                              │  ┌────────────────────┐   │
                              │  │   Admin WebUI      │   │
                              │  │  /admin (mobile)   │   │
                              │  └────────────────────┘   │
                              └──────────────────────────┘
```

For the full step-by-step walkthrough, see **[Setup Guide](docs/SETUP.md)**.

## Quick Start

### Option 1: One-line install (recommended)

The install script walks you through setup interactively — Google OAuth, module selection, server config:

```bash
curl -fsSL https://raw.githubusercontent.com/brimdor/gatekeeper/main/install.sh | bash
```

### Option 2: Install with uv

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Gatekeeper
uv tool install "gatekeeper @ git+https://github.com/brimdor/gatekeeper"
```

### Option 3: Install with pip

```bash
pip install git+https://github.com/brimdor/gatekeeper
```

### Option 4: Podman/Docker

```bash
git clone https://github.com/brimdor/gatekeeper.git
cd gatekeeper
cp .env.example .env
# Edit .env with your Google OAuth credentials and module preferences
podman-compose up -d
```

## Setup

### 1. Configure environment

```bash
# Create .env from template
cp .env.example .env

# Edit with your settings — at minimum set:
# - GATEKEEPER_GOOGLE_CLIENT_ID
# - GATEKEEPER_GOOGLE_CLIENT_SECRET
# - GATEKEEPER_DRIVE_ENABLED=true  (or gmail/calendar)
nano .env
```

### 2. Google OAuth Setup

Gatekeeper supports two OAuth authorization flows:

#### Desktop Browser (recommended — works locally and over SSH)

```bash
gatekeeper auth
```

- **On a machine with a display**: Opens your browser automatically. Authorize, close the tab, done.
- **Over SSH / headless**: Prints a Google authorization URL. Open it on any device, authorize, then paste the redirect URL back into the terminal. Works seamlessly over SSH.

#### Device Authorization (alternative for headless servers)

```bash
gatekeeper auth --flow device
```

This displays a URL and a code. Open the URL on **any device** (phone, laptop, tablet), enter the code, and authorize. No browser on the server needed — perfect for headless machines and containers.

> **Note**: The device flow requires an OAuth client of type **"TVs and Limited Input devices"**, not "Desktop app". If you get `Invalid client type`, use the desktop flow or create a separate client.

#### Google Cloud Setup (one-time)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the APIs you need: Drive, Gmail, Calendar
4. Go to **APIs & Services → Credentials**
5. Create an **OAuth 2.0 Client ID** (Desktop app type)
6. Copy the Client ID and Client Secret to your `.env`:
   ```bash
   GATEKEEPER_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GATEKEEPER_GOOGLE_CLIENT_SECRET=your-client-secret
   ```
7. Go to **OAuth consent screen** → add your email as a test user
8. Run `gatekeeper auth`
   ```bash
   gatekeeper auth
   ```
   
   On first run, Gatekeeper generates:
   - An admin password (saved in `gatekeeper_secrets.json`)
   - An encryption key for OAuth token storage
   - Default API key (`default-admin`)
   
   ⚠️ **Save the admin password** — it's printed once during setup.

### 3. Start the server

```bash
gatekeeper serve
```

Or install as a systemd service:

```bash
gatekeeper service install    # Install systemd user service
gatekeeper service enable     # Enable and start the service
gatekeeper service disable    # Stop and disable the service
gatekeeper service status     # Check status
gatekeeper service logs       # View logs (-f to follow)
gatekeeper service restart    # Restart after config changes
```

### 4. Configure MCP access (for remote/SSH)

By default, MCP only accepts connections from localhost. To allow access from Tailscale, LAN, or other hosts:

```bash
gatekeeper hosts list              # View allowed hosts
gatekeeper hosts add 100.127.113.87 # Add Tailscale IP
gatekeeper hosts add myserver.local # Add hostname
gatekeeper hosts remove 100.127.113.87  # Remove a host
```

### 5. Create an API key for your agent

```bash
# Create a key with full access
gatekeeper key create --name my-agent

# Create a key with limited module access
gatekeeper key create --name drive-reader --permissions drive

# List keys
gatekeeper key list

# Revoke a key
gatekeeper key revoke --prefix gkp_a1b2c3d4
```

Keys are prefixed with `gkp_` and the full key is only shown once on creation.

## Admin UI

Access the admin UI at `http://localhost:8080/admin/` with HTTP Basic Auth. The UI is mobile-responsive — works on phones, tablets, and desktops.

| Page | Purpose |
|------|---------|
| **Dashboard** | Overview — requests, keys, auth status |
| **Modules** | Enable/disable modules (Drive, Gmail, Calendar) and toggle individual routes |
| **API Keys** | Create, list, and revoke keys |
| **Audit Log** | Filterable log of all requests |
| **Auth Status** | Google OAuth connection status |

## Using with AI Agents

Gatekeeper connects to AI agents via MCP (Model Context Protocol) — exposing enabled routes as discoverable tools that agents can call directly. Write routes (send, create, delete) are disabled by default; only a human admin can enable them.

**📖 Setup guides:**
- **For humans** → [docs/MCP_SETUP_HUMAN.md](docs/MCP_SETUP_HUMAN.md) — configure Gatekeeper, create API keys, enable routes
- **For AI agents** → [docs/MCP_SETUP_AGENT.md](docs/MCP_SETUP_AGENT.md) — how to connect, call tools, handle errors, security boundaries

> **If you are an AI agent** reading this repository: open [docs/MCP_SETUP_AGENT.md](docs/MCP_SETUP_AGENT.md) for complete setup instructions including config examples, tool reference, and usage patterns.

### Quick start: Connect your agent

```json
{
  "mcpServers": {
    "gatekeeper": {
      "url": "http://localhost:8080/mcp/sse",
      "transport": "sse",
      "headers": {
        "X-Gatekeeper-API-Key": "gkp_your_api_key_here"
      }
    }
  }
}
```

> **⚠️ You MUST include `"transport": "sse"`.** Gatekeeper uses SSE transport. Without this, you'll get 405 errors.

Every tool requires an `api_key` parameter. Disabled routes return `403` — they cannot be bypassed.

### REST API

```bash
# List Gmail messages
curl -H "X-Gatekeeper-API-Key: gkp_your_key" \
  http://localhost:8080/api/v1/gmail/messages/list

# Get a Drive file
curl -H "X-Gatekeeper-API-Key: gkp_your_key" \
  http://localhost:8080/api/v1/drive/files/get?fileId=1abc...

# Create a calendar event
curl -H "X-Gatekeeper-API-Key: gkp_your_key" \
  -H "Content-Type: application/json" \
  -d '{"summary":"Meeting","start":{"dateTime":"2025-01-15T10:00:00"}}' \
  http://localhost:8080/api/v1/calendar/events/create
```

## Module Reference

### Drive (27 routes)

| Route | Method | Default | Policy |
|-------|--------|---------|--------|
| `drive.about.get` | GET | ✅ On | — |
| `drive.files.list` | GET | ✅ On | max_results=50 |
| `drive.files.get` | GET | ✅ On | — |
| `drive.files.export` | GET | ✅ On | — |
| `drive.files.list_shared` | GET | ✅ On | max_results=50, query_filter=sharedWithMe |
| `drive.files.generate_ids` | GET | ✅ On | — |
| `drive.changes.list` | GET | ✅ On | — |
| `drive.changes.get_start_page_token` | GET | ✅ On | — |
| `drive.comments.list` | GET | ✅ On | — |
| `drive.comments.get` | GET | ✅ On | — |
| `drive.revisions.list` | GET | ✅ On | — |
| `drive.revisions.get` | GET | ✅ On | — |
| `drive.permissions.list` | GET | ✅ On | — |
| `drive.permissions.get` | GET | ✅ On | — |
| `drive.drives.list` | GET | ✅ On | — |
| `drive.drives.get` | GET | ✅ On | — |
| `drive.files.copy` | POST | ❌ Off | — |
| `drive.files.create` | POST | ❌ Off | max_file_size_mb |
| `drive.files.update` | PATCH | ❌ Off | — |
| `drive.files.delete` | DELETE | ❌ Off | — |
| `drive.files.trash` | POST | ❌ Off | — |
| `drive.files.empty_trash` | DELETE | ❌ Off | — |
| `drive.comments.create` | POST | ❌ Off | — |
| `drive.drives.create` | POST | ❌ Off | — |
| `drive.permissions.create` | POST | ❌ Off | max_recipients=5 |
| `drive.permissions.update` | PATCH | ❌ Off | — |
| `drive.permissions.delete` | DELETE | ❌ Off | — |

### Gmail (37 routes)

| Route | Method | Default | Policy |
|-------|--------|---------|--------|
| `gmail.messages.list` | GET | ✅ On | max_results=50, allowed_labels, exclude SPAM/TRASH |
| `gmail.messages.get` | GET | ✅ On | — |
| `gmail.messages.send` | POST | ❌ Off | max_recipients=5, max_attachment_size_mb=10, require_body |
| `gmail.messages.modify` | POST | ❌ Off | — |
| `gmail.messages.trash` | POST | ❌ Off | — |
| `gmail.messages.untrash` | POST | ❌ Off | — |
| `gmail.messages.delete` | DELETE | ❌ Off | — |
| `gmail.messages.batch_modify` | POST | ❌ Off | — |
| `gmail.messages.batch_delete` | POST | ❌ Off | — |
| `gmail.messages.attachments.get` | GET | ✅ On | — |
| `gmail.drafts.list` | GET | ✅ On | max_results=50 |
| `gmail.drafts.get` | GET | ✅ On | — |
| `gmail.drafts.create` | POST | ❌ Off | max_recipients=5 |
| `gmail.drafts.update` | PUT | ❌ Off | — |
| `gmail.drafts.send` | POST | ❌ Off | max_recipients=5 |
| `gmail.drafts.delete` | DELETE | ❌ Off | — |
| `gmail.threads.list` | GET | ✅ On | — |
| `gmail.threads.get` | GET | ✅ On | — |
| `gmail.threads.modify` | POST | ❌ Off | — |
| `gmail.threads.trash` | POST | ❌ Off | — |
| `gmail.threads.untrash` | POST | ❌ Off | — |
| `gmail.threads.delete` | DELETE | ❌ Off | — |
| `gmail.history.list` | GET | ✅ On | — |
| `gmail.labels.list` | GET | ✅ On | — |
| `gmail.labels.get` | GET | ✅ On | — |
| `gmail.labels.create` | POST | ❌ Off | — |
| `gmail.labels.update` | PATCH | ❌ Off | — |
| `gmail.labels.delete` | DELETE | ❌ Off | — |
| `gmail.filters.list` | GET | ❌ Off | — |
| `gmail.filters.get` | GET | ❌ Off | — |
| `gmail.filters.create` | POST | ❌ Off | — |
| `gmail.filters.update` | PATCH | ❌ Off | — |
| `gmail.filters.delete` | DELETE | ❌ Off | — |
| `gmail.settings.forwarding_addresses.list` | GET | ❌ Off | — |
| `gmail.settings.forwarding_addresses.get` | GET | ❌ Off | — |
| `gmail.settings.forwarding_addresses.create` | POST | ❌ Off | — |
| `gmail.settings.forwarding_addresses.delete` | DELETE | ❌ Off | — |

### Calendar (26 routes)

| Route | Method | Default | Policy |
|-------|--------|---------|--------|
| `calendar.events.list` | GET | ✅ On | max_results=50 |
| `calendar.events.get` | GET | ✅ On | — |
| `calendar.events.create` | POST | ❌ Off | — |
| `calendar.events.update` | PATCH | ❌ Off | — |
| `calendar.events.delete` | DELETE | ❌ Off | — |
| `calendar.events.quick_add` | POST | ❌ Off | — |
| `calendar.events.move` | POST | ❌ Off | — |
| `calendar.calendars.list` | GET | ✅ On | — |
| `calendar.calendarlist.list` | GET | ✅ On | max_results=50 |
| `calendar.calendarlist.get` | GET | ✅ On | — |
| `calendar.calendarlist.insert` | POST | ❌ Off | — |
| `calendar.calendarlist.update` | PUT | ❌ Off | — |
| `calendar.calendarlist.delete` | DELETE | ❌ Off | — |
| `calendar.calendars.get` | GET | ✅ On | — |
| `calendar.calendars.create` | POST | ❌ Off | — |
| `calendar.calendars.update` | PUT | ❌ Off | — |
| `calendar.calendars.delete` | DELETE | ❌ Off | — |
| `calendar.calendars.clear` | POST | ❌ Off | — |
| `calendar.acl.list` | GET | ✅ On | — |
| `calendar.acl.get` | GET | ✅ On | — |
| `calendar.acl.create` | POST | ❌ Off | — |
| `calendar.acl.delete` | DELETE | ❌ Off | — |
| `calendar.colors.get` | GET | ✅ On | — |
| `calendar.freebusy.query` | POST | ✅ On | — |
| `calendar.settings.list` | GET | ✅ On | — |
| `calendar.settings.get` | GET | ✅ On | — |

## Policy Configuration

Each route has a JSON policy config that controls behavior:

| Policy | Applies To | Effect |
|--------|-----------|--------|
| `max_results` | List routes | Caps the number of results returned |
| `allowed_labels` | Gmail list | Only allow these Gmail labels |
| `exclude_labels` | Gmail list | Filter out these Gmail labels |
| `blocked_fields` | Any | Strip these fields from responses |
| `max_items` | Any | Cap array lengths in responses |
| `query_filter` | Drive list | Force a Drive query parameter |
| `max_recipients` | Gmail send/draft | Limit email recipients |
| `max_file_size_mb` | Drive create | Limit upload file size |
| `max_attachment_size_mb` | Gmail send | Limit attachment size |
| `require_body` | Gmail send | Require non-empty email body |

Edit policies via the admin UI or REST API:

```bash
curl -u admin:password -X PATCH http://localhost:8080/admin/api/routes/1 \
  -H "Content-Type: application/json" \
  -d '{"enabled": false, "policy_config": {"max_results": 25}}'
```

## CLI Reference

```bash
gatekeeper serve                          # Start the server
gatekeeper serve --host 0.0.0.0 --port 9090  # Custom host/port
gatekeeper init                           # Initialize database and seed policies
gatekeeper auth                           # Google OAuth (desktop flow — opens browser)
gatekeeper auth --flow device             # Google OAuth (device flow — for SSH/headless)
gatekeeper key create --name my-agent     # Create an API key
gatekeeper key create --name drv --permissions drive  # Scoped key
gatekeeper key list                       # List all keys
gatekeeper key revoke --prefix gkp_a1b2   # Revoke a key
gatekeeper status                         # Show configuration status
gatekeeper service install                # Install systemd user service
gatekeeper service uninstall              # Remove systemd user service
gatekeeper service enable                 # Enable and start the service
gatekeeper service disable                 # Stop and disable the service
gatekeeper service restart                # Restart the service
gatekeeper service status                 # Show service status
gatekeeper service logs                   # Show service logs (-f to follow)
gatekeeper hosts list                     # List MCP allowed hosts
gatekeeper hosts add <hostname>           # Add a host (Tailscale, LAN, etc.)
gatekeeper hosts remove <hostname>        # Remove a host
```

## Configuration

All configuration via environment variables (prefix `GATEKEEPER_`) or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEKEEPER_HOST` | `127.0.0.1` | Host to bind to (`0.0.0.0` in containers) |
| `GATEKEEPER_PORT` | `8080` | Port to bind to |
| `GATEKEEPER_DEBUG` | `false` | Enable debug mode |
| `GATEKEEPER_DATABASE_URL` | `sqlite+aiosqlite:///./gatekeeper.db` | Database URL |
| `GATEKEEPER_SECRET_KEY` | *(auto-generated)* | Secret key for sessions |
| `GATEKEEPER_ENCRYPTION_KEY` | *(auto-generated)* | Fernet key for Google token encryption |
| `GATEKEEPER_ADMIN_USERNAME` | `admin` | Admin UI username |
| `GATEKEEPER_ADMIN_PASSWORD` | *(auto-generated)* | Admin UI password |
| `GATEKEEPER_API_KEY_PREFIX` | `gkp_` | Prefix for API keys |
| `GATEKEEPER_MCP_ENABLED` | `true` | Enable MCP server |
| `GATEKEEPER_MCP_ALLOWED_HOSTS` | `[]` (localhost/127.0.0.1 always allowed) | JSON array of additional hosts for MCP connections (use `gatekeeper hosts add` CLI) |
| `GATEKEEPER_RATE_LIMIT_PER_MINUTE` | `120` | Rate limit per minute per API key |
| `GATEKEEPER_GOOGLE_CLIENT_ID` | *(required)* | Google OAuth client ID |
| `GATEKEEPER_GOOGLE_CLIENT_SECRET` | *(required)* | Google OAuth client secret |
| `GATEKEEPER_GOOGLE_TOKEN_FILE` | `./google_token.json` | Encrypted token file path |
| `GATEKEEPER_DRIVE_ENABLED` | `false` | Enable Drive module |
| `GATEKEEPER_GMAIL_ENABLED` | `false` | Enable Gmail module |
| `GATEKEEPER_CALENDAR_ENABLED` | `false` | Enable Calendar module |
| `GATEKEEPER_DISPLAY_TIMEZONE` | `America/Chicago` | IANA timezone for timestamp display |
| `GATEKEEPER_CORS_ORIGINS` | `["http://localhost:8080","http://127.0.0.1:8080"]` | CORS allowed origins |

**Auto-generated secrets** are persisted in `gatekeeper_secrets.json` so they survive restarts. This file is created with `chmod 600` permissions. **Add it to `.gitignore`** (already in the default `.gitignore`).

## Container Deployment (Podman)

```bash
# Build
podman build -t gatekeeper .

# Create .env
cp .env.example .env
# Edit .env with your credentials

# Run with compose
podman-compose up -d

# Or run directly
podman run -d \
  --name gatekeeper \
  -p 8080:8080 \
  -v gatekeeper-data:/data \
  --env-file .env \
  gatekeeper
```

The `/data` volume persists the SQLite database, Google token, and secrets across container restarts.

**Raspberry Pi**: The Dockerfile supports `linux/arm64` — Podman will build the correct architecture automatically with `--platform linux/arm64`.

## Security

- **TLS**: Use a reverse proxy (Caddy/nginx) for HTTPS in production
- **API Keys**: bcrypt-hashed, prefix-based lookup, revocable
- **Token Encryption**: Google OAuth refresh tokens encrypted at rest with Fernet
- **Secret Persistence**: Auto-generated secrets stored in `gatekeeper_secrets.json` (chmod 600)
- **Network**: Binds `127.0.0.1` by default — only accessible locally unless configured otherwise
- **MCP Host Allowlist**: DNS rebinding protection; only `localhost` and `127.0.0.1` by default — add Tailscale/LAN hosts via `gatekeeper hosts add`
- **CORS**: Configurable via `GATEKEEPER_CORS_ORIGINS`
- **Admin Auth**: HTTP Basic Auth with auto-generated credentials

## Development

```bash
# Clone and install dev dependencies
git clone https://github.com/brimdor/gatekeeper.git
cd gatekeeper
uv pip install -e ".[dev]"

# Run tests
uv run pytest tests/ -v

# Run linter
uv run ruff check gatekeeper/
uv run ruff format --check gatekeeper/ tests/

# Run locally
uv run gatekeeper serve
```

## Architecture

```
gatekeeper/
├── gatekeeper/
│   ├── __init__.py           # Version
│   ├── main.py               # FastAPI app, CLI, lifespan
│   ├── config.py             # Pydantic settings + secret persistence
│   ├── db.py                 # Async SQLite setup
│   ├── models.py             # SQLAlchemy models
│   ├── encryption.py         # Fernet encrypt/decrypt
│   ├── auth.py               # API key auth + admin auth
│   ├── policy.py             # Policy engine (allow/deny/transform)
│   ├── google_client.py     # Google OAuth desktop + device flow
│   ├── logging.py            # Audit logging
│   ├── service.py            # Systemd service management
│   ├── api/
│   │   ├── router.py          # Dynamic FastAPI router from modules
│   │   └── proxy.py           # Policy-enforced Google API proxy
│   ├── admin/
│   │   ├── routes.py          # Admin REST API
│   │   ├── models.py          # Pydantic response models
│   │   └── ui/
│   │       ├── __init__.py    # Jinja2 template rendering
│   │       ├── static/style.css
│   │       └── templates/     # Mobile-responsive admin dashboard
│   ├── mcp_server/
│   │   ├── __init__.py        # FastMCP SSE server
│   │   └── transport.py       # SSE transport config
│   └── modules/
│       ├── __init__.py         # Module registry
│       ├── base.py            # GoogleModule base class
│       ├── route.py           # ModuleRoute definition
│       ├── drive/             # Drive module (27 routes)
│       ├── gmail/             # Gmail module (37 routes)
│       └── calendar/          # Calendar module (26 routes)
├── tests/                      # Test suite
├── Dockerfile                  # Multi-arch Podman/Docker build
├── docker-compose.yml          # Podman Compose config
├── install.sh                  # One-line install script
├── .env.example                # Environment template
└── pyproject.toml              # Package configuration
```

## License

MIT