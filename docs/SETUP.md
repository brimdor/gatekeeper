# Gatekeeper — Setup Guide

Complete walkthrough for installing, configuring, and running Gatekeeper on a fresh system.

---

## Deployment Options

Choose your install method based on your environment:

| Method | One-liner | Best when |
|---|---|---|
| **Docker** (recommended) | `docker run -d --name gatekeeper -p 8080:8080 -v gatekeeper-data:/data -e GATEKEEPER_GOOGLE_CLIENT_ID=your_id -e GATEKEEPER_GOOGLE_CLIENT_SECRET=your_secret ghcr.io/brimdor/gatekeeper:latest` | You have Docker installed |
| **Podman** | Same as Docker, replace `docker` with `podman` | You prefer daemonless containers |
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

This runs an interactive wizard that installs dependencies, asks for Google OAuth credentials, lets you choose APIs, and writes `.env`.

For non-interactive installs (CI, scripts):

```bash
bash install.sh --non-interactive
```

### Option B: Manual (bare metal)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install "gatekeeper @ git+https://github.com/brimdor/gatekeeper"
# Or with pip:
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

The container auto-runs `gatekeeper serve` on port 8080. Data persists in the `/data` volume.

---

## Step 2 — Configure environment

```bash
cp .env.example .env
nano .env   # or your preferred editor
```

### Required settings

```env
GATEKEEPER_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GATEKEEPER_GOOGLE_CLIENT_SECRET=your-client-secret
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
GATEKEEPER_HOST=127.0.0.1
GATEKEEPER_PORT=8080
GATEKEEPER_DATABASE_URL=sqlite+aiosqlite:///./gatekeeper.db
GATEKEEPER_RATE_LIMIT_PER_MINUTE=120
GATEKEEPER_API_KEY_PREFIX=gkp_
GATEKEEPER_MCP_ENABLED=true
GATEKEEPER_MCP_ALLOWED_HOSTS=[]
GATEKEEPER_DISPLAY_TIMEZONE=America/Chicago
GATEKEEPER_ADMIN_USERNAME=admin
GATEKEEPER_GOOGLE_TOKEN_FILE=./google_token.json
GATEKEEPER_DEBUG=false
```

---

## Step 3 — Set up Google OAuth

<!-- Canonical — all other docs link here. -->

This is a one-time setup in the Google Cloud Console.

### 3a — Create or select a project

1. Go to **[Google Cloud Console](https://console.cloud.google.com/)**
2. Create a new project or select an existing one

### 3b — Enable the Google APIs

1. Go to **[API Library](https://console.cloud.google.com/apis/library)**
2. Enable each API you need:
   - **Google Drive API**
   - **Gmail API**
   - **Google Calendar API**

### 3c — Create OAuth credentials

1. Go to **[Google Auth platform → Clients](https://console.cloud.google.com/auth/clients)** (or **APIs & Services → Credentials**)
2. Click **Create Client**
3. Application type: **Desktop app**
4. Copy the **Client ID** and **Client Secret** into your `.env`

### 3d — Configure the OAuth consent screen and scopes

1. Go to **[Google Auth platform → Branding](https://console.cloud.google.com/auth/branding)** and start the consent screen setup:
   - **App name**: "Gatekeeper"
   - **User support email**: your email
   - **Audience**: **External**
   - **Contact email**: your email
2. Add the OAuth scopes Gatekeeper needs:

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
   | **Forms** | `https://www.googleapis.com/auth/forms.body` |
   | **Forms** | `https://www.googleapis.com/auth/forms.body.readonly` |
   | **Forms** | `https://www.googleapis.com/auth/forms.responses.readonly` |
   | **Apps Script** | `https://www.googleapis.com/auth/script.projects` |
   | **Apps Script** | `https://www.googleapis.com/auth/script.projects.readonly` |
   | **Apps Script** | `https://www.googleapis.com/auth/script.deployments` |
   | **Apps Script** | `https://www.googleapis.com/auth/script.deployments.readonly` |
   | **Apps Script** | `https://www.googleapis.com/auth/script.processes` |
   | **Apps Script** | `https://www.googleapis.com/auth/script.metrics` |

   The Drive scopes match `gatekeeper/modules/drive/__init__.py:required_scopes`.
   The Forms and Apps Script scopes match their module `required_scopes` and are requested only when their module flags are enabled.

3. Add yourself as a **Test User** on the **Audience** page.

> **⚠️ Critical**:
> - If you skip adding scopes, most API calls will fail with `403 ACCESS_TOKEN_SCOPE_INSUFFICIENT`.
> - If you skip adding yourself as a Test User, auth will fail with "This app isn't verified."
> - After changing scopes or test users, re-run `gatekeeper auth` to refresh the token.

---

## Step 4 — Initialize the database

```bash
gatekeeper init
```

This creates `gatekeeper.db`, seeds route policies, generates an admin password (saved to `gatekeeper_secrets.json`), and generates a **default admin API key** — **save it immediately**.

---

## Step 5 — Authorize with Google

### Desktop flow (recommended)

```bash
gatekeeper auth
```

Opens your browser automatically. Credentials are saved encrypted to `google_token.json`.

### SSH / headless environments

`gatekeeper auth` detects headless environments and uses a manual code exchange:

1. It prints a Google authorization URL
2. Open the URL on any device
3. After authorizing, copy the full redirect URL
4. Paste it into the terminal prompt

### Device flow (alternative)

```bash
gatekeeper auth --flow device
```

> **Note**: The device flow requires an OAuth client type of **"TVs and Limited Input devices"**. If you get `Invalid client type`, use the desktop flow instead.

---

## Step 6 — Start the server

### Bare metal

```bash
gatekeeper serve
gatekeeper serve --host 0.0.0.0 --port 9090
```

### Systemd (recommended for production)

Use the built-in command:

```bash
gatekeeper service install    # Install systemd user service
gatekeeper service enable     # Enable and start the service
gatekeeper service status     # Check status
```

For full systemd details, see [docs/PODMAN_DEPLOYMENT.md](PODMAN_DEPLOYMENT.md) § Canonical systemd setup.

### Podman/Docker

```bash
podman-compose up -d         # Start
podman-compose logs -f       # Logs
podman-compose down          # Stop
```

---

## Step 7 — Verify it's running

```bash
curl http://localhost:8080/health
# Expected: {"status":"ok","version":"0.1.0"}

gatekeeper status
```

Example `gatekeeper status` output:

```text
==================================================
  Gatekeeper Status
==================================================
  Version:      0.1.0
  Host:         127.0.0.1
  Port:         8080
  Debug:        False
  Database:     sqlite+aiosqlite:///./gatekeeper.db
  MCP Enabled:  True
  Modules:
    Drive:      ❌
    Gmail:      ❌
    Calendar:   ❌
  Google OAuth: ❌ Not configured
  Admin User:   admin
  Service:      ❌ Not installed (run: gatekeeper service install)
==================================================
```

---

## Step 8 — Create API keys

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

Keys are prefixed with `gkp_`. The full key is shown once on creation. The `permissions` value is a comma-separated list of module names or `*` for all.

---

## Step 9 — Configure routes and policies

Open the Admin UI at **http://localhost:8080/admin/** with HTTP Basic Auth:

- **Username**: `admin`
- **Password**: from `gatekeeper_secrets.json`

| Page | Purpose |
|---|---|
| **Dashboard** | Overview — requests, keys, auth status |
| **Modules** | Enable/disable modules and individual routes |
| **API Keys** | Create, list, revoke keys |
| **Audit Log** | Filterable request log |
| **Auth Status** | Google OAuth connection status |

### Default route policy

- **Read routes are enabled** — list, get, export
- **Write routes are disabled** — send, create, update, delete

Enable write routes in the Modules page when you are ready to grant agents write access.

### Available routes

Gatekeeper currently exposes **174 routes** across Drive, Gmail, and Calendar. The canonical route table is auto-generated at [docs/ROUTES.md](ROUTES.md). See [docs/API_REFERENCE.md](API_REFERENCE.md) for example requests and error handling.

### Policy configuration

For the full list of policy transforms and recipes, see [docs/POLICY_REFERENCE.md](POLICY_REFERENCE.md).

---

## Step 10 — Connect your AI agent

- **Human administrators** → [docs/MCP_SETUP_HUMAN.md](MCP_SETUP_HUMAN.md)
- **AI agents** → [docs/MCP_SETUP_AGENT.md](MCP_SETUP_AGENT.md)

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

All four files are in `.gitignore`.

---

## CLI reference

```bash
gatekeeper serve
gatekeeper init
gatekeeper auth
gatekeeper auth --flow device
gatekeeper key create --name my-agent
gatekeeper key list
gatekeeper key revoke --prefix gkp_a1b2
gatekeeper status
gatekeeper service install
gatekeeper service enable
gatekeeper service status
gatekeeper service logs
gatekeeper hosts list
gatekeeper hosts add <hostname>
gatekeeper hosts remove <hostname>
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `gatekeeper` command not found | Open a new terminal or `source ~/.bashrc` |
| Auth fails with `Invalid client type` | Use `gatekeeper auth` (desktop flow) |
| Auth fails with 401 | Check Client ID/Secret are complete in `.env` |
| Auth fails with "app not verified" | Add yourself as a Test User |
| "Route X is disabled" 403 | Enable the route in the Admin UI |
| Token refresh not working | Re-run `gatekeeper auth` |
| CORS errors in browser | Add origin to `GATEKEEPER_CORS_ORIGINS` |
| Admin UI asks for password | Username: `admin`; password in `gatekeeper_secrets.json` |

---

## Security checklist

- [ ] `.env` and `gatekeeper_secrets.json` are not in version control
- [ ] Google OAuth consent screen is in **Testing** mode
- [ ] Only your email is a Test User
- [ ] Write routes are **disabled by default** — enable only when needed
- [ ] API keys are scoped per agent
- [ ] CORS origins are specific, not `*`
- [ ] `GATEKEEPER_HOST` is `127.0.0.1` unless behind a reverse proxy
- [ ] Running behind a reverse proxy with TLS in production
- [ ] Rate limiting is configured
