# Gatekeeper — Setup Guide

Complete walkthrough for installing, configuring, and running Gatekeeper on a fresh system.

---

## Deployment Options

Choose your install method based on your environment:

| Method | One-liner | Best when |
|---|---|---|
| **Docker** (recommended) | `docker run -d --name gatekeeper -p 8080:8080 -v gatekeeper-data:/data -e GATEKEEPER_GOOGLE_CLIENT_ID=your_id -e GATEKEEPER_GOOGLE_CLIENT_SECRET=your_secret ghcr.io/brimdor/gatekeeper:latest` | You have Docker installed |
| **Podman** | Same as Docker, replace `docker` with `podman` | You prefer podman/docker daemonless |
| **pip** | `pip install aigatekeeper && gatekeeper serve` | Quick local Python install |
| **uv** | `uv tool install aigatekeeper && gatekeeper serve` | Modern Python tooling |
| **Clone + run** | `git clone https://github.com/brimdor/gatekeeper && cd gatekeeper && gatekeeper serve` | You want to modify or contribute |
| **systemd** | `gatekeeper service install --scope user && gatekeeper service start` | 24/7 background service |
| **install.sh** | `curl -fsSL https://raw.githubusercontent.com/brimdor/gatekeeper/main/install.sh | bash` | Interactive wizard |

After any install above, continue with **Step 2** below for Google OAuth setup.

For agent connection instructions, see **[MCP_SETUP_HUMAN.md](MCP_SETUP_HUMAN.md)**.

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

# Enable the APIs you need (all default to false — you MUST set these to true)
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
GATEKEEPER_CORS_ORIGINS=["http://localhost:8080","http://127.0.0.1:8080"]  # CORS origins
GATEKEEPER_RATE_LIMIT_PER_MINUTE=120                         # Rate limit
GATEKEEPER_API_KEY_PREFIX=gkp_                               # Key prefix
GATEKEEPER_MCP_ENABLED=true                                  # MCP server
GATEKEEPER_MCP_ALLOWED_HOSTS=[]                              # Additional MCP hosts (localhost always allowed)
GATEKEEPER_DISPLAY_TIMEZONE=America/Chicago                  # Timestamp display timezone
GATEKEEPER_ADMIN_USERNAME=admin                               # Admin UI username
GATEKEEPER_GOOGLE_TOKEN_FILE=./google_token.json              # OAuth token file path
GATEKEEPER_DEBUG=false                                       # Debug mode
```

---

## Step 3 — Set up Google OAuth

This is a one-time setup in the Google Cloud Console. You'll configure four things: enable APIs, create OAuth credentials, configure the consent screen (including scopes), and add test users.

### 3a — Create or select a project

1. Go to **[Google Cloud Console](https://console.cloud.google.com/)**
2. Create a new project or select an existing one

### 3b — Enable the Google APIs

1. Go to **[API Library](https://console.cloud.google.com/apis/library)** (☰ menu → **APIs & Services** → **Library**)
2. Search for and enable each API you need:
   - **Google Drive API** — search "Google Drive API" → click **Enable**
   - **Gmail API** — search "Gmail API" → click **Enable**
   - **Google Calendar API** — search "Google Calendar API" → click **Enable**

Enable all three if you want full Gatekeeper coverage. You can skip APIs for modules you've disabled.

### 3c — Create OAuth credentials

1. Go to **[Google Auth platform → Clients](https://console.cloud.google.com/auth/clients)** (☰ menu → **Google Auth platform** → **Clients**)
2. Click **Create Client**
3. Application type: **Desktop app**
4. Give it a name (e.g., "Gatekeeper")
5. Click **Create**
6. Copy the **Client ID** and **Client Secret** into your `.env`:
   ```env
   GATEKEEPER_GOOGLE_CLIENT_ID=123456789-abc.apps.googleusercontent.com
   GATEKEEPER_GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxx
   ```

> **Note**: If you don't see "Google Auth platform" in the menu, use **APIs & Services → Credentials** instead — click **Create Credentials → OAuth 2.0 Client ID**. Google is rolling out the new navigation gradually.

### 3d — Configure the OAuth consent screen and scopes

This step is **critical** — if you skip adding scopes, `gatekeeper auth` will fail with insuffient scope errors.

1. Go to **[Google Auth platform → Branding](https://console.cloud.google.com/auth/branding)** (☰ menu → **Google Auth platform** → **Branding**)
2. If you see "Google Auth platform not configured yet", click **Get Started**:
   - **App name**: enter a name (e.g., "Gatekeeper")
   - **User support email**: choose your email
   - Click **Next**
   - **Audience**: select **External** (so you can add test users)
   - Click **Next**
   - **Contact email**: enter your email
   - Click **Next**
   - Review the policy, check **I agree**, click **Continue**, then **Create**

3. Add the **OAuth scopes** that Gatekeeper needs:
   - Click **Data Access** in the left sidebar (or go to **[Google Auth platform → Data Access](https://console.cloud.google.com/auth/data-access)**)
   - Click **Add or Remove Scopes**
   - Add all of these scopes (or only the ones for modules you've enabled):

   | Module | Scope | What it allows |
   |--------|-------|----------------|
   | **Drive** | `https://www.googleapis.com/auth/drive` | Read and write Drive files |
   | **Gmail** | `https://www.googleapis.com/auth/gmail.modify` | Read, modify, and trash messages |
   | **Gmail** | `https://www.googleapis.com/auth/gmail.send` | Send messages |
   | **Gmail** | `https://www.googleapis.com/auth/gmail.compose` | Create and edit drafts |
   | **Gmail** | `https://www.googleapis.com/auth/gmail.settings.basic` | Manage labels, filters, forwarding |
   | **Calendar** | `https://www.googleapis.com/auth/calendar` | Read and write calendars |
   | **Calendar** | `https://www.googleapis.com/auth/calendar.events` | Read and write events |

   > **How to find each scope**: In the "Add or Remove Scopes" dialog, search by keyword — type "drive" for the Drive scope, "gmail" for Gmail scopes, "calendar" for Calendar scopes. The scopes above are marked as **Sensitive** or **Restricted** by Google, so they'll appear in the Sensitive/Restricted sections.

   - Click **Save**

4. Add yourself as a **Test User**:
   - Click **Audience** in the left sidebar (or go to **[Google Auth platform → Audience](https://console.cloud.google.com/auth/audience)**)
   - Scroll to **Test users** → click **Add users**
   - Enter your Google account email → click **Save**

> **⚠️ Critical**:
> - If you skip adding scopes, `gatekeeper auth` will only get basic read-only access and most API calls will fail with `403 ACCESS_TOKEN_SCOPE_INSUFFICIENT`.
> - If you skip adding yourself as a Test User, the auth flow will fail with "This app isn't verified" and block you out.
> - After changing scopes or test users, you must re-run `gatekeeper auth` to get a new token with the updated permissions.


---

## Step 4 — Initialize the database

```bash
gatekeeper init
```

This command:
- Creates `gatekeeper.db` (SQLite)
- Seeds route policies for all modules (Drive, Gmail, Calendar)
- Generates an admin password (saved to `gatekeeper_secrets.json`)
- Generates a **default admin API key** — **save it immediately, it's only shown once**

Expected output:
```
🔑 Admin password generated: <password>
   Saved to gatekeeper_secrets.json

============================================================
🔑 Default API Key generated (save this — it won't be shown again):
   gkp_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890
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

Use the built-in command to install and enable the service:

```bash
gatekeeper service install    # Install systemd user service
gatekeeper service enable     # Enable and start the service
gatekeeper service status     # Check status
gatekeeper service logs -f    # Follow logs
```

If you prefer manual setup:

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
| **Modules** | Enable/disable modules (Drive, Gmail, Calendar) and toggle individual routes per module |
| **API Keys** | Create, list, and revoke keys |
| **Audit Log** | Filterable log of all requests |
| **Auth Status** | Google OAuth connection status |

### Default route policy

By default:
- **Read routes are enabled** — list, get, export
- **Write routes are disabled** — send, create, update, delete

Enable write routes in the Modules page (expand a module and toggle individual routes) when you're ready to grant agents write access.

### Available routes

**Drive (27 routes)**
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

**Gmail (37 routes)**
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

**Calendar (26 routes)**
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

### Policy configuration

Each route has a JSON policy config that controls behavior:

| Policy | Applies To | Effect |
|--------|-----------|--------|
| `max_results` | List routes | Caps the number of results returned |
| `allowed_labels` | Gmail list | Only allow these Gmail labels |
| `exclude_labels` | Gmail list | Filter out these Gmail labels |
| `blocked_fields` | Any | Strip these fields from responses |
| `max_items` | Any | Cap array lengths in responses |
| `query_filter` | Drive list | Force a Drive query parameter (e.g., `sharedWithMe`) |
| `max_recipients` | Gmail send/draft | Limit email recipients |
| `max_file_size_mb` | Drive create | Limit upload file size in MB |
| `max_attachment_size_mb` | Gmail send | Limit attachment size in MB |
| `require_body` | Gmail send | Require non-empty email body |

Edit policies via the Admin UI or REST API:
```bash
curl -u admin:password -X PATCH http://localhost:8080/admin/api/routes/1 \
  -H "Content-Type: application/json" \
  -d '{"enabled": false, "policy_config": {"max_results": 25}}'
```

---

## Step 10 — Connect your AI agent

**📖 For detailed MCP setup, see:**
- **Human administrators** → [docs/MCP_SETUP_HUMAN.md](MCP_SETUP_HUMAN.md)
- **AI agents** → [docs/MCP_SETUP_AGENT.md](MCP_SETUP_AGENT.md)

### MCP server (recommended)

Gatekeeper exposes an MCP server at `/mcp/sse`. Add to your agent's config:

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

> **⚠️ You MUST include `"transport": "sse"`.** Without it, you'll get 405 errors from clients that default to Streamable HTTP.

When you enable a route in the Admin UI, the agent discovers it as a new tool. Disabled routes return `403` — they cannot be bypassed.

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
gatekeeper service install                # Install systemd user service
gatekeeper service enable                 # Enable and start the service
gatekeeper service disable                # Stop and disable the service
gatekeeper service restart                # Restart (after config changes)
gatekeeper service status                 # Check service status
gatekeeper service logs                   # View service logs (-f to follow)
gatekeeper hosts list                     # List MCP allowed hosts
gatekeeper hosts add <hostname>           # Add a host (Tailscale, LAN, etc.)
gatekeeper hosts remove <hostname>        # Remove a host
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `gatekeeper` command not found | Open a new terminal or `source ~/.bashrc` — the installer adds `~/.local/bin` to PATH |
| Auth fails with `Invalid client type` | Use the desktop flow (`gatekeeper auth`), not `--flow device`. The device flow requires an OAuth client type of "TVs and Limited Input devices" |
| Auth fails with 401 | Check Client ID/Secret are complete (not truncated) in `.env`. Verify your email is a Test User on the OAuth consent screen |
| Auth fails with "app not verified" | Add your email as a Test User on the OAuth consent screen in Google Cloud Console |
| "Route X is disabled" 403 | Go to Admin UI → Modules → expand the module → enable the route |
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