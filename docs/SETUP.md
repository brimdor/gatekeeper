# Gatekeeper — Setup Guide

Complete walkthrough for installing, configuring, and running Gatekeeper on a fresh system.

---

## Prerequisites

- **Python 3.11+** (for bare metal install)
- **A Google Cloud project** with the APIs you need enabled
- **Podman** or **Docker** (for containerized install), **or** `uv`/`pip` (for bare metal)

---

## Step 1 — Install Gatekeeper

### Option A: One-line install with interactive setup (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/brimdor/gatekeeper/main/install.sh | bash
```

This runs an interactive wizard that:
- Installs Python dependencies
- Clones the repo
- Asks for your Google OAuth Client ID and Secret
- Lets you choose which APIs to enable (Drive, Gmail, Calendar)
- Configures host/port
- Writes `.env` with your settings
- Runs `gatekeeper init` and `gatekeeper auth`

For non-interactive installs (CI, scripts):
```bash
bash install.sh --non-interactive
```

### Option B: Manual (bare metal)

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Gatekeeper
uv tool install "gatekeeper @ git+https://github.com/brimdor/gatekeeper"

# Or with pip
pip install git+https://github.com/brimdor/gatekeeper
```

### Option C: Podman/Docker

```bash
git clone https://github.com/brimdor/gatekeeper.git
cd gatekeeper
cp .env.example .env
# Edit .env — see Step 2
podman-compose up -d   # or: docker compose up -d
```

The container auto-runs `gatekeeper serve` on port 8080 with a health check.
Data persists in the `/data` volume (database, tokens, secrets).

---

## Step 2 — Configure environment

```bash
cp .env.example .env
nano .env   # or your preferred editor
```

### Required settings

```env
# Google OAuth credentials (from Step 3)
GATEKEEPER_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GATEKEEPER_GOOGLE_CLIENT_SECRET=your-client-secret

# Enable the APIs you need
GATEKEEPER_DRIVE_ENABLED=true
GATEKEEPER_GMAIL_ENABLED=true
GATEKEEPER_CALENDAR_ENABLED=true
```

### Auto-generated settings (leave blank)

These are generated on first run and saved to `gatekeeper_secrets.json`:

```env
GATEKEEPER_ADMIN_PASSWORD=     # Auto-generated, printed once
GATEKEEPER_SECRET_KEY=         # Session signing
GATEKEEPER_ENCRYPTION_KEY=     # OAuth token encryption at rest
```

### Optional settings

```env
GATEKEEPER_HOST=127.0.0.1                                    # Bind address
GATEKEEPER_PORT=8080                                         # Port
GATEKEEPER_DATABASE_URL=sqlite+aiosqlite:///./gatekeeper.db  # Database
GATEKEEPER_CORS_ORIGINS=["http://localhost:8080"]            # CORS origins
GATEKEEPER_RATE_LIMIT_PER_MINUTE=120                         # Rate limit
GATEKEEPER_API_KEY_PREFIX=gkp_                               # Key prefix
GATEKEEPER_MCP_ENABLED=true                                  # MCP server
GATEKEEPER_DEBUG=false                                       # Debug mode
```

---

## Step 3 — Set up Google OAuth

This is a one-time setup in the Google Cloud Console.

1. Go to **[Google Cloud Console](https://console.cloud.google.com/)**
2. Create a new project (or select an existing one)
3. Enable the APIs you need:
   - **Drive API** → Library → search "Google Drive API" → Enable
   - **Gmail API** → Library → search "Gmail API" → Enable
   - **Calendar API** → Library → search "Google Calendar API" → Enable
4. Go to **APIs & Services → Credentials**
5. Click **Create Credentials → OAuth 2.0 Client ID**
6. Application type: **Desktop app**
7. Copy the **Client ID** and **Client Secret** into your `.env`:
   ```env
   GATEKEEPER_GOOGLE_CLIENT_ID=123456789-abc.apps.googleusercontent.com
   GATEKEEPER_GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxx
   ```
8. Go to **OAuth consent screen**:
   - Set publishing status to **Testing** (not Production)
   - Add your Google account email as a **Test User**
   - This is required — Google blocks access until you add yourself

> **⚠️ Important**: If you skip adding yourself as a Test User, the auth flow will fail with a "This app isn't verified" error that blocks you out.

---

## Step 4 — Initialize the database

```bash
gatekeeper init
```

This command:
- Creates `gatekeeper.db` (SQLite)
- Seeds route policies for all modules (Drive, Gmail, Calendar)
- Generates a **default admin API key** — **save it immediately, it's only shown once**

Expected output:
```
============================================================
🔑 Default API Key generated (save this — it won't be shown again):
   gkp_a1b2c3d4e5f6...
============================================================
✅ Database initialized and default policies seeded.
```

---

## Step 5 — Authorize with Google

### Desktop flow (recommended — local machine with browser)

```bash
gatekeeper auth
```

Opens your browser automatically. Authorize Gatekeeper to access your Google data, then close the tab. Credentials are saved encrypted to `google_token.json`.

### SSH / headless environments

If you're running Gatekeeper on a remote server over SSH (no display), `gatekeeper auth` automatically detects this and uses a manual code exchange:

1. It prints a Google authorization URL
2. Open that URL on **any device** (your laptop, phone, tablet)
3. After authorizing, your browser redirects to `http://localhost?code=...` (the page won't load — that's expected)
4. Copy the **full URL** from your browser's address bar
5. Paste it into the terminal prompt

### Device flow (alternative for headless servers)

If you prefer the link+code flow (no redirect URL to paste):

```bash
gatekeeper auth --flow device
```

1. Gatekeeper prints a URL and a device code
2. Open the URL on **any device** (phone, laptop, tablet)
3. Enter the code and authorize
4. Credentials are saved encrypted to `google_token.json`

> **Note**: The device flow requires an OAuth client of type **"TVs and Limited Input devices"** (not "Desktop app") in Google Cloud Console. If you get `Invalid client type`, use the default desktop flow instead, or create a separate "TVs and Limited Input devices" client.

> **Troubleshooting**: If auth fails with 401, verify your Client ID and Client Secret are complete in `.env` (not truncated) and your email is a Test User on the OAuth consent screen.

---

## Step 6 — Start the server

### Bare metal

```bash
gatekeeper serve
```

Runs on `http://localhost:8080` by default. Override with `--host` and `--port`:
```bash
gatekeeper serve --host 0.0.0.0 --port 9090
```

### Systemd (recommended for production)

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/gatekeeper.service << 'EOF'
[Unit]
Description=Gatekeeper Policy Gateway
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/your/gatekeeper
ExecStart=/path/to/gatekeeper serve
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now gatekeeper
```

Check status: `systemctl --user status gatekeeper`
View logs: `journalctl --user -u gatekeeper -f`

### Podman/Docker

```bash
podman-compose up -d         # Start
podman-compose logs -f       # Logs
podman-compose down          # Stop
```

---

## Step 7 — Verify it's running

```bash
# Health check
curl http://localhost:8080/health
# Expected: {"status":"ok","version":"0.1.0"}

# Configuration status
gatekeeper status
```

---

## Step 8 — Create API keys

The default key from `gatekeeper init` works, but you should create per-agent keys:

```bash
# Full access
gatekeeper key create --name my-agent

# Drive-only access
gatekeeper key create --name drive-reader --permissions drive

# List keys
gatekeeper key list

# Revoke a compromised key
gatekeeper key revoke --prefix gkp_a1b2c3d4
```

Keys are prefixed with `gkp_` and the full key is only shown once on creation.

---

## Step 9 — Configure routes and policies

Open the Admin UI: **http://localhost:8080/admin/**

Login credentials:
- **Username**: `admin` (from `GATEKEEPER_ADMIN_USERNAME`)
- **Password**: check `gatekeeper_secrets.json` for the auto-generated password (or whatever you set in `.env`)

The Admin UI provides:

| Page | Purpose |
|------|---------|
| **Dashboard** | Overview — requests, keys, auth status |
| **Modules** | Enable/disable Drive, Gmail, Calendar |
| **Routes** | Toggle individual API routes and configure policies |
| **API Keys** | Create, list, and revoke keys |
| **Audit Log** | Searchable log of all requests |
| **Auth Status** | Google OAuth connection status |

### Default route policy

By default:
- **Read routes are enabled** — list, get, export
- **Write routes are disabled** — send, create, update, delete

Enable write routes in the Routes page when you're ready to grant agents write access.

### Available routes

**Drive (5 routes)**
| Route | Method | Default | Policy |
|-------|--------|---------|--------|
| `drive.files.list` | GET | ✅ On | max_results=50 |
| `drive.files.get` | GET | ✅ On | — |
| `drive.files.export` | GET | ✅ On | — |
| `drive.files.list_shared` | GET | ✅ On | max_results=50, query_filter |
| `drive.files.copy` | POST | ❌ Off | — |

**Gmail (6 routes)**
| Route | Method | Default | Policy |
|-------|--------|---------|--------|
| `gmail.messages.list` | GET | ✅ On | max_results=50, exclude SPAM/TRASH |
| `gmail.messages.get` | GET | ✅ On | — |
| `gmail.messages.send` | POST | ❌ Off | max_recipients=5 |
| `gmail.drafts.list` | GET | ✅ On | max_results=50 |
| `gmail.drafts.create` | POST | ❌ Off | max_recipients=5 |
| `gmail.labels.list` | GET | ✅ On | — |

**Calendar (8 routes)**
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

### Policy configuration

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

Edit policies via the Admin UI or REST API:
```bash
curl -u admin:password -X PATCH http://localhost:8080/admin/api/routes/1 \
  -H "Content-Type: application/json" \
  -d '{"enabled": false, "policy_config": {"max_results": 25}}'
```

---

## Step 10 — Connect your AI agent

### MCP server (recommended)

Add to your agent's config:

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

When you enable a route in the Admin UI, the agent automatically discovers it as a new tool. Disable it and the tool disappears on the next `list_tools` call.

### REST API (direct calls)

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

---

## File layout after setup

```
your-directory/
├── .env                        # Your configuration (secrets — never commit)
├── gatekeeper_secrets.json     # Auto-generated: admin password, encryption key
├── google_token.json           # OAuth token (encrypted at rest)
├── gatekeeper.db               # SQLite database
└── (gatekeeper source if cloned)
```

All four files are in `.gitignore` — they never get committed to version control.

---

## CLI reference

```bash
gatekeeper serve                          # Start the server
gatekeeper serve --host 0.0.0.0 --port 9090  # Custom host/port
gatekeeper init                           # Initialize database and seed policies
gatekeeper auth                           # Google OAuth (desktop flow — opens browser)
gatekeeper auth --flow device             # Google OAuth (device flow — for headless servers)
gatekeeper key create --name my-agent     # Create an API key
gatekeeper key create --name drv --permissions drive  # Scoped key
gatekeeper key list                       # List all keys
gatekeeper key revoke --prefix gkp_a1b2   # Revoke a key
gatekeeper status                         # Show configuration status
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `gatekeeper` command not found | Open a new terminal or `source ~/.bashrc` — the installer adds `~/.local/bin` to PATH |
| Auth fails with `Invalid client type` | Use the desktop flow (`gatekeeper auth`), not `--flow device`. The device flow requires an OAuth client type of "TVs and Limited Input devices" |
| Auth fails with 401 | Check Client ID/Secret are complete (not truncated) in `.env`. Verify your email is a Test User on the OAuth consent screen |
| Auth fails with "app not verified" | Add your email as a Test User on the OAuth consent screen in Google Cloud Console |
| "Route X is disabled" 403 | Go to Admin UI → Routes → enable the route |
| Token refresh not working | Re-run `gatekeeper auth` to refresh. v0.1.0 fixes the expiry persistence bug |
| Podman build fails on ARM | Ensure buildx is available: `podman buildx build --platform linux/arm64,linux/amd64 .` |
| CORS errors in browser | Add your frontend origin to `GATEKEEPER_CORS_ORIGINS` in `.env` |
| Admin UI asks for password | Default username: `admin`, password: check `gatekeeper_secrets.json` |

---

## Security checklist

- [ ] `.env` and `gatekeeper_secrets.json` are not in version control (`.gitignore`)
- [ ] Google OAuth consent screen is in **Testing** mode (not Production)
- [ ] Only your email is a Test User on the OAuth consent screen
- [ ] Write routes (send, create, update, delete) are **disabled by default** — enable only when needed
- [ ] API keys are scoped per agent, not shared
- [ ] CORS origins are specific, not `*`
- [ ] `GATEKEEPER_HOST` is `127.0.0.1` unless you're behind a reverse proxy
- [ ] Running behind a reverse proxy (nginx, Caddy) with TLS in production
- [ ] Rate limiting is configured (`GATEKEEPER_RATE_LIMIT_PER_MINUTE`)