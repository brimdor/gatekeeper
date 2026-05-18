# Gatekeeper Podman Deployment Guide

This document describes how to deploy, operate, and maintain Gatekeeper as a Podman container on a Raspberry Pi (Mario) or any Linux host.

**Audience:** An AI agent or human operator setting up and maintaining Gatekeeper containers. Assumes Podman is installed and the operator has shell access to the target host.

---

## Overview

Gatekeeper runs as a rootless Podman container. Each container serves one user. Multiple users get independent containers with separate:

- Port mappings (e.g., `:8081`, `:8082`)
- Data volumes (SQLite DB, Google OAuth tokens, secrets)
- `.env` configuration files

This is the **pod-per-user** architecture. No application code changes are needed — each instance thinks it is the only instance.

```
Host (Mario)
├── Container: gatekeeper-brimdor (port 8081)
│   └── Volume: gk-brimdor-data → /data (brimdor.db, tokens, secrets)
│
├── Container: gatekeeper-canary (port 8082)
│   └── Volume: gk-canary-data → /data (isolated DB + tokens)
│
└── Container: gatekeeper-alice (port 8083)
    └── Volume: gk-alice-data → /data (alice.db, alice_token.json)
```

---

## Prerequisites on Mario

Verify these are available:

```bash
podman version                       # 4.x or higher
systemctl --user is-system-running   # systemd user services available
loginctl enable-linger $USER         # keep user services alive after logout
```

If `podman` is not installed:

```bash
# Arch Linux (if Mario runs Arch)
sudo pacman -S podman podman-compose

# Raspberry Pi OS / Debian
sudo apt-get install podman podman-compose
```

---

## Step 1: Pull the Gatekeeper Image

The image is hosted in the homelab registry at `10.0.20.11:32309/broville/gatekeeper`:

```bash
# Pull the latest stable image
podman pull --tls-verify=false 10.0.20.11:32309/broville/gatekeeper:latest

# For testing, pull the canary tag
podman pull --tls-verify=false 10.0.20.11:32309/broville/gatekeeper:canary
```

If you need to push images to the registry, use:

```bash
podman push --tls-verify=false your-image 10.0.20.11:32309/broville/gatekeeper:tag
```

**Note:** The `--tls-verify=false` flag is required because the homelab registry uses a self-signed certificate. This is safe within the trusted homelab network.

### Local Build (Alternative)

Clone the repo and build locally if you want to customize:

If you are building the image yourself from source:

```bash
git clone https://github.com/brimdor/gatekeeper.git
cd gatekeeper
podman build -t gatekeeper:latest .
podman build -t gatekeeper:canary .
```

---

## Step 2: Prepare Configuration Per User

Each user needs a `.env` file and a named volume. Create them on the host:

```bash
# Create a directory for Gatekeeper configs
mkdir -p ~/gatekeeper

# Create a .env for each user
# Example: ~/gatekeeper/.env.brimdor
```

### `.env` Template for a Production User

```env
# Server
GATEKEEPER_HOST=0.0.0.0
GATEKEEPER_PORT=8080

# Database (inside the container volume)
GATEKEEPER_DATABASE_URL=sqlite+aiosqlite:////data/gatekeeper.db
GATEKEEPER_GOOGLE_TOKEN_FILE=/data/google_token.json

# Google OAuth — each user has their own credentials
GATEKEEPER_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GATEKEEPER_GOOGLE_CLIENT_SECRET=your-client-secret

# Modules
GATEKEEPER_DRIVE_ENABLED=true
GATEKEEPER_GMAIL_ENABLED=true
GATEKEEPER_CALENDAR_ENABLED=true

# MCP (for AI agent access via Tailscale)
GATEKEEPER_MCP_ENABLED=true
GATEKEEPER_MCP_ALLOWED_HOSTS=["*"]

# Display timezone
GATEKEEPER_DISPLAY_TIMEZONE=America/Chicago
```

### `.env` Template for a Canary Instance

```env
GATEKEEPER_HOST=0.0.0.0
GATEKEEPER_PORT=8080
GATEKEEPER_DATABASE_URL=sqlite+aiosqlite:////data/gatekeeper.db
GATEKEEPER_GOOGLE_TOKEN_FILE=/data/google_token.json

# Can use the same Google creds as production for functionality testing
GATEKEEPER_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GATEKEEPER_GOOGLE_CLIENT_SECRET=your-client-secret

GATEKEEPER_DRIVE_ENABLED=true
GATEKEEPER_GMAIL_ENABLED=true
GATEKEEPER_CALENDAR_ENABLED=true
GATEKEEPER_MCP_ENABLED=true

# More permissive for canary testing
GATEKEEPER_MCP_ALLOWED_HOSTS=["*"]
```

---

## Step 3: Create Named Volumes

Each container needs a persistent volume for its database, tokens, and secrets:

```bash
# Create volumes
podman volume create gk-brimdor-data
podman volume create gk-canary-data
podman volume create gk-alice-data

# Verify
podman volume ls
```

---

## Step 4: First-Run Initialization

Each container must be initialized once to create the database and seed policies. This step also generates:

- **Admin password** — printed to stdout, saved in `gatekeeper_secrets.json`
- **Default API key** — printed once (copy it immediately; it is not stored in plaintext)

Start the container with `gatekeeper init` as the entry point:

```bash
# Initialize brimdor's instance
podman run -it --rm \
  --name gatekeeper-brimdor-init \
  -v gk-brimdor-data:/data \
  --env-file ~/gatekeeper/.env.brimdor \
  10.0.20.11:32309/broville/gatekeeper:latest \
  gatekeeper init
```

**IMPORTANT:** Copy the admin password and default API key from the output. The API key is only shown once.

The same process applies for canary:

```bash
podman run -it --rm \
  --name gatekeeper-canary-init \
  -v gk-canary-data:/data \
  --env-file ~/gatekeeper/.env.canary \
  10.0.20.11:32309/broville/gatekeeper:canary \
  gatekeeper init
```

---

## Step 5: Run the Container

### Production Instance (Brimdor)

```bash
podman run -d \
  --name gatekeeper-brimdor \
  --replace \
  -p 8081:8080 \
  -v gk-brimdor-data:/data \
  --env-file ~/gatekeeper/.env.brimdor \
  10.0.20.11:32309/broville/gatekeeper:latest
```

### Canary Instance

```bash
podman run -d \
  --name gatekeeper-canary \
  --replace \
  -p 8082:8080 \
  -v gk-canary-data:/data \
  --env-file ~/gatekeeper/.env.canary \
  10.0.20.11:32309/broville/gatekeeper:canary
```

### Additional User (e.g., Alice)

```bash
podman run -d \
  --name gatekeeper-alice \
  --replace \
  -p 8083:8080 \
  -v gk-alice-data:/data \
  --env-file ~/gatekeeper/.env.alice \
  10.0.20.11:32309/broville/gatekeeper:latest
```

---

## Step 6: Run Google OAuth Authorization

After the container is running, authorize it with Google:

```bash
# Interactive: the flow prints a URL, user opens it in a browser
podman exec -it gatekeeper-brimdor gatekeeper auth --flow desktop

# On headless host (SSH): prints a URL for manual code exchange
# Open the URL on any device, authorize, paste the redirect URL back
podman exec -it gatekeeper-brimdor gatekeeper auth
```

The OAuth token is saved encrypted inside the container volume (`/data/google_token.json`). It persists across container restarts.

If the device flow is preferred (link + code, no redirect URL to paste):

```bash
podman exec -it gatekeeper-brimdor gatekeeper auth --flow device
```

**Note:** The device flow requires an OAuth client of type "TVs and Limited Input devices", not "Desktop app". If you get `Invalid client type`, use the default desktop flow instead.

---

## Step 7: Verify It Works

### Health Check

```bash
curl http://localhost:8081/health
# Expected: {"status":"ok","version":"0.1.0"}
```

### API Key Quick Test

If you have the API key:

```bash
# List Gmail labels (read-only, should work on a fresh instance)
curl -H "X-Gatekeeper-API-Key: gkp_your_key_here" \
  http://localhost:8081/api/v1/gmail/labels/list
```

### Admin UI

Open in a browser: `http://mario-ip:8081/admin/`

Login with username `admin` and the password from `gatekeeper_secrets.json`.

---

## Step 8: Install systemd Service

For production, run the container as a systemd service so it starts on boot and restarts on failure.

### Option A: systemd Quadlet (Recommended)

Quadlets are native systemd unit files. Create `~/.config/containers/systemd/gatekeeper-brimdor.container`:

```ini
[Unit]
Description=Gatekeeper for Brimdor
After=network-online.target
Wants=network-online.target

[Container]
Image=10.0.20.11:32309/broville/gatekeeper:latest
ContainerName=gatekeeper-brimdor
PublishPort=8081:8080
Volume=gk-brimdor-data:/data
EnvironmentFile=%h/gatekeeper/.env.brimdor
Environment=GATEKEEPER_HOST=0.0.0.0
Environment=GATEKEEPER_PORT=8080

[Service]
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

For canary:

```ini
[Unit]
Description=Gatekeeper Canary for Brimdor
After=network-online.target
Wants=network-online.target

[Container]
Image=10.0.20.11:32309/broville/gatekeeper:canary
ContainerName=gatekeeper-canary
PublishPort=8082:8080
Volume=gk-canary-data:/data
EnvironmentFile=%h/gatekeeper/.env.canary
Environment=GATEKEEPER_HOST=0.0.0.0
Environment=GATEKEEPER_PORT=8080

[Service]
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now gatekeeper-brimdor
systemctl --user enable --now gatekeeper-canary
```

Verify:

```bash
systemctl --user status gatekeeper-brimdor
journalctl --user -u gatekeeper-brimdor -f
```

### Option B: podman generate systemd

Alternatively, generate systemd units from a running container:

```bash
podman generate systemd --new --name gatekeeper-brimdor > ~/.config/systemd/user/gatekeeper-brimdor.service
systemctl --user daemon-reload
systemctl --user enable --now gatekeeper-brimdor
```

This captures the full `podman run` command as a systemd `ExecStart`. It is simpler but less declarative than Quadlets.

---

## Container Lifecycle

### Upgrade a Container

```bash
# Pull the new image
podman pull 10.0.20.11:32309/broville/gatekeeper:latest

# Stop and replace the container
podman stop gatekeeper-brimdor
podman rm gatekeeper-brimdor

# Start with the new image (data volume persists)
podman run -d \
  --name gatekeeper-brimdor \
  -p 8081:8080 \
  -v gk-brimdor-data:/data \
  --env-file ~/gatekeeper/.env.brimdor \
  10.0.20.11:32309/broville/gatekeeper:latest
```

For systemd-managed containers, just pull the new image and restart:

```bash
podman pull 10.0.20.11:32309/broville/gatekeeper:latest
systemctl --user restart gatekeeper-brimdor
```

### View Logs

```bash
# Running container
podman logs gatekeeper-brimdor
podman logs -f gatekeeper-brimdor  # follow

# systemd-managed
journalctl --user -u gatekeeper-brimdor
journalctl --user -u gatekeeper-brimdor -f
```

### Backup

```bash
# Backup the data volume
podman volume export gk-brimdor-data -o ~/backups/brimdor-gatekeeper-$(date +%Y%m%d).tar

# Restore
podman volume rm gk-brimdor-data
podman volume import gk-brimdor-data ~/backups/brimdor-gatekeeper-20250101.tar
```

### Clean Up

```bash
# Stop and remove a container
podman stop gatekeeper-brimdor
podman rm gatekeeper-brimdor

# Remove volume (WARNING: deletes all data)
podman volume rm gk-brimdor-data
```

---

## Updating the Image

When a new version of Gatekeeper is built and pushed to the registry:

```bash
# On Mario
podman pull 10.0.20.11:32309/broville/gatekeeper:latest

# Check for canary tag
podman pull 10.0.20.11:32309/broville/gatekeeper:canary

# Restart services to pick up new images
systemctl --user restart gatekeeper-brimdor
```

---

## Agent Connections

AI agents connect to Gatekeeper via MCP over SSE. The connection details depend on which port the container exposes:

| User | Host | Port | MCP URL |
|---|---|---|---|
| Brimdor (prod) | Mario Tailscale IP | 8081 | `http://100.x.x.x:8081/mcp/sse` |
| Canary | Mario Tailscale IP | 8082 | `http://100.x.x.x:8082/mcp/sse` |
| Alice | Mario Tailscale IP | 8083 | `http://100.x.x.x:8083/mcp/sse` |

Each agent needs:
1. The MCP URL for their user's container
2. An API key created via the admin UI or `gatekeeper key create`
3. The module scopes (Drive, Gmail, Calendar)

---

## Troubleshooting

### Container won't start

Check logs:

```bash
podman logs gatekeeper-brimdor
```

Common issues:
- **Port already in use**: Change the host port mapping
- **Volume missing**: Create it with `podman volume create gk-brimdor-data`
- **Missing .env**: Verify `--env-file` path is correct and the file exists
- **Permission denied**: Rootless Podman runs as the current user. Ensure the user has write access to the volume directory

### Health check fails

```bash
podman exec gatekeeper-brimdor curl -s http://127.0.0.1:8080/health
```

If the container health check returns connection refused, the application may have failed to start. Check for Python import errors in the container logs.

### MCP returns 421 Misdirected Request

The SSE transport has DNS rebinding protection. The Host header must match a configured allowed host:

```bash
# When connecting from outside the container, pass the correct Host header
curl -N -H "Host: localhost:8081" http://127.0.0.1:8081/mcp/sse
```

If connecting via reverse proxy, add the proxy hostname to `GATEKEEPER_MCP_ALLOWED_HOSTS`:

```env
GATEKEEPER_MCP_ALLOWED_HOSTS=["gatekeeper.brimdor.local"]
```

### Auth shows "not configured"

Run the Google OAuth flow:

```bash
podman exec -it gatekeeper-brimdor gatekeeper auth
```

This requires an interactive terminal. If running in a headless environment, the flow will print a URL for manual code exchange.
