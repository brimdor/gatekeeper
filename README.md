# Gatekeeper 🔐

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
                              │  │  /admin (HTMX)     │   │
                              │  └────────────────────┘   │
                              └──────────────────────────┘
```

## Quick Start

### Option 1: One-line install (recommended)

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

#### Device Authorization (recommended — works anywhere)

```bash
gatekeeper auth
```

This displays a URL and a code. Open the URL on **any device** (phone, laptop, tablet), enter the code, and authorize. No browser on the server needed — perfect for headless machines and containers.

#### Desktop Browser (local machine only)

```bash
gatekeeper auth --flow desktop
```

Opens a browser on the local machine and captures the redirect automatically. Use this when you're running Gatekeeper on your desktop.

#### Google Cloud Setup (one-time)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the APIs you need: Drive, Gmail, Calendar
4. Go to **APIs & Services → Credentials**
5. Create an **OAuth 2.0 Client ID** (Desktop app type)
6. Copy the Client ID and Client Secret to your `.env`:
   ```bash
   GATEKEEPER_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GATEKEEPER_GOOGLE_CLIENT_SECRET=GOCSPX-your-secret
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

### 4. Create an API key for your agent

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

Access the admin UI at `http://localhost:8080/admin/` with HTTP Basic Auth.

| Page | Purpose |
|------|---------|
| **Dashboard** | Overview — requests, keys, auth status |
| **Modules** | Enable/disable Drive, Gmail, Calendar |
| **Routes** | Toggle individual API routes and configure policies |
| **API Keys** | Create, list, and revoke keys |
| **Audit Log** | Searchable log of all requests |
| **Auth Status** | Google OAuth connection status |

## Using with AI Agents

### MCP Server (recommended)

Gatekeeper exposes an MCP server at `/mcp/sse`. Connect your agent:

```json
{
  "mcpServers": {
    "gatekeeper": {
      "url": "http://localhost:8080/mcp/sse",
      "headers": {
        "Authorization": "Bearer gkp_your_api_key_here"
      }
    }
  }
}
```

When you enable a route in the admin UI, the agent automatically discovers it as a new tool. Disable it, and the tool disappears on the next `list_tools` call.

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

### Drive (5 routes)

| Route | Method | Default | Policy |
|-------|--------|---------|--------|
| `drive.files.list` | GET | ✅ On | max_results=50 |
| `drive.files.get` | GET | ✅ On | — |
| `drive.files.export` | GET | ✅ On | — |
| `drive.files.list_shared` | GET | ✅ On | max_results=50, query_filter |
| `drive.files.copy` | POST | ❌ Off | — |

### Gmail (6 routes)

| Route | Method | Default | Policy |
|-------|--------|---------|--------|
| `gmail.messages.list` | GET | ✅ On | max_results=50, exclude SPAM/TRASH |
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

Edit policies via the admin UI or REST API:

```bash
curl -u admin:password -X PATCH http://localhost:8080/admin/api/routes/1 \
  -H "Content-Type: application/json" \
  -d '{"enabled": false, "policy_config": {"max_results": 25}}'
```

## CLI Reference

```bash
gatekeeper serve              # Start the server
gatekeeper init               # Initialize database and seed policies
gatekeeper auth               # Google OAuth — device flow (link + code, works anywhere)
gatekeeper auth --flow desktop # Google OAuth — desktop flow (opens browser locally)
gatekeeper key create --name NAME [--permissions PERMS]   # Create API key
gatekeeper key list           # List API keys
gatekeeper key revoke --prefix PREFIX   # Revoke a key
gatekeeper status             # Show configuration status
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
| `GATEKEEPER_GOOGLE_CLIENT_ID` | *(required)* | Google OAuth client ID |
| `GATEKEEPER_GOOGLE_CLIENT_SECRET` | *(required)* | Google OAuth client secret |
| `GATEKEEPER_GOOGLE_TOKEN_FILE` | `./google_token.json` | Encrypted token file path |
| `GATEKEEPER_DRIVE_ENABLED` | `false` | Enable Drive module |
| `GATEKEEPER_GMAIL_ENABLED` | `false` | Enable Gmail module |
| `GATEKEEPER_CALENDAR_ENABLED` | `false` | Enable Calendar module |
| `GATEKEEPER_CORS_ORIGINS` | `[\"http://localhost:8080\"]` | CORS allowed origins |

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
│   ├── google_client.py      # Google OAuth desktop flow
│   ├── logging.py             # Audit logging
│   ├── api/
│   │   ├── router.py         # Dynamic FastAPI router from modules
│   │   └── proxy.py          # Policy-enforced Google API proxy
│   ├── admin/
│   │   ├── routes.py          # Admin REST API
│   │   ├── models.py          # Pydantic response models
│   │   └── ui/
│   │       ├── __init__.py    # Jinja2 template rendering
│   │       ├── static/style.css
│   │       └── templates/     # HTMX + Tailwind dashboard
│   ├── mcp_server/
│   │   ├── __init__.py        # FastMCP SSE server
│   │   └── transport.py       # SSE transport config
│   └── modules/
│       ├── __init__.py         # Module registry
│       ├── base.py            # GoogleModule base class
│       ├── route.py           # ModuleRoute definition
│       ├── drive/             # Drive module (5 routes)
│       ├── gmail/             # Gmail module (6 routes)
│       └── calendar/          # Calendar module (8 routes)
├── tests/                      # 78 tests
├── Dockerfile                  # Multi-arch Podman/Docker build
├── docker-compose.yml          # Podman Compose config
├── install.sh                  # One-line install script
├── .env.example                # Environment template
└── pyproject.toml              # Package configuration
```

## License

MIT