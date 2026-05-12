# Gatekeeper V1 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a policy gateway for Google Workspace APIs (Drive, Gmail, Calendar) that exposes fine-grained, policy-controlled REST and MCP endpoints, with an HTMX admin UI for configuration.

**Architecture:** FastAPI application with SQLite backend. Google OAuth tokens stored encrypted at rest. Agents authenticate via API keys. Each request is validated against route policies before proxying to Google. An MCP server (SSE transport) dynamically exposes enabled routes as tools. Admin UI for enabling/disabling routes, managing API keys, and viewing audit logs.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy (async + aiosqlite), HTMX + Jinja2 + Tailwind CSS (CDN), `mcp` Python SDK (SSE transport), `google-api-python-client`, `bcrypt`, `cryptography` (Fernet for token encryption), `uv` for packaging, Podman (multi-arch amd64+arm64, daemonless).

**Repo:** `github.com/brimdor/gatekeeper` (private, already created)

---

## Design Decisions (locked for v1)

1. **Admin UI:** HTMX + Jinja2 + Tailwind CSS via CDN. No Node build step. Lightweight for RPi.
2. **Google OAuth:** Desktop app flow. One-time manual authorization via `gatekeeper auth` CLI command. Refresh token stored encrypted (Fernet) in SQLite. Single-user only.
3. **MCP Transport:** SSE-over-HTTP on `/mcp` endpoint. Gateway is a persistent service — agents connect remotely. Stdio transport also supported for testing.
4. **v1 Scope:** Drive, Gmail, Calendar modules only. Module system is extensible for future services.
5. **API Key Auth:** Bearer-style keys (`gkp_...` prefix). bcrypt-hashed in DB. Per-key permissions (which modules the key can access).
6. **Token Encryption:** `cryptography.fernet.Fernet` for encrypting Google OAuth refresh tokens at rest. Key derived from `GATEKEEPER_ENCRYPTION_KEY` env var.
7. **Policy Engine:** Per-route enable/disable toggle + JSON policy config. Policies can cap limits, filter labels, block fields, restrict recipients, etc.
8. **Database:** SQLite via aiosqlite. Zero external deps. Perfect for RPi and containers.
9. **TLS:** Recommend reverse proxy (Caddy/nginx) for production. Gateway binds `127.0.0.1` by default.
10. **Container Runtime:** Podman (not Docker). Podman is daemonless, already installed on the development system, and CLI-compatible with Docker. All container references use Podman.

---

## Architecture Diagram

```
┌──────────────┐   API Key    ┌──────────────────────────┐   OAuth2    ┌──────────┐
│  AI Agent    │──────────────│     Gatekeeper           │────────────│  Google  │
│  (Nova etc) │              │                          │            │  APIs    │
│             │   MCP SDK    │  ┌────────────────────┐  │            │          │
│             │──────────────│  │   Policy Engine    │  │            └──────────┘
└──────────────┘   (SSE)     │  │  (allow/deny/      │  │
                             │  │   transform)       │  │
                             │  └────────────────────┘  │
                             │                          │
                             │  ┌────────────────────┐  │
                             │  │   Admin WebUI      │  │
                             │  │  /admin (HTMX)     │  │
                             │  └────────────────────┘  │
                             │                          │
                             │  ┌────────────────────┐  │
                             │  │  MCP Server (SSE)  │  │
                             │  │  /mcp endpoint     │  │
                             │  └────────────────────┘  │
                             └──────────────────────────┘
```

## Request Flow

```
1. Agent → POST /api/v1/gmail/messages/list (with X-Gatekeeper-API-Key header)
2. Gateway: validate API key (bcrypt compare)
3. Gateway: look up route policy for "gmail.messages.list"
4. Gateway: check if route enabled + key has gmail permission
5. Gateway: apply request transforms per policy (cap maxResults, filter labels)
6. Gateway: get valid Google OAuth credentials (refresh if needed)
7. Gateway: call Google API with transformed params
8. Gateway: apply response filters per policy (strip blocked fields, cap arrays)
9. Gateway: log to audit DB (key, route, status)
10. Gateway: return filtered response to agent
```

## MCP Request Flow

```
1. Agent connects to /mcp via SSE
2. Agent calls "tools/list" → gateway returns tool for each enabled route
3. Agent calls "tools/call" with tool name + params → gateway routes to policy engine → Google API
4. Admin toggles route on → next "tools/list" includes it automatically
```

## Project Structure

```
gatekeeper/
├── pyproject.toml
├── README.md
├── Dockerfile            # Containerfile (Podman-compatible)
├── docker-compose.yml    # podman-compose compatible
├── .env.example
├── .gitignore
├── gatekeeper/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, lifespan, CLI entry point
│   ├── config.py               # pydantic-settings config (GATEKEEPER_* env vars)
│   ├── db.py                   # SQLAlchemy async engine + session factory
│   ├── models.py               # ORM models: ApiKey, RoutePolicy, AuditLog, GoogleToken
│   ├── auth.py                 # API key validation middleware
│   ├── policy.py               # Policy engine (route allow/deny/transform)
│   ├── google_client.py        # OAuth credential management (load/refresh/encrypt)
│   ├── encryption.py           # Fernet encrypt/decrypt helpers
│   ├── logging.py              # Audit log writer
│   ├── modules/
│   │   ├── __init__.py         # Module registry (load/enumerate modules)
│   │   ├── base.py             # GoogleModule ABC
│   │   ├── route.py            # RouteDef model
│   │   ├── drive/__init__.py   # DriveModule + route definitions
│   │   ├── gmail/__init__.py   # GmailModule + route definitions
│   │   └── calendar/__init__.py # CalendarModule + route definitions
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py           # Main API router, mounts module sub-routers
│   │   └── proxy.py            # Google API proxy logic (build request, call, filter)
│   ├── mcp_server/
│   │   ├── __init__.py         # MCP server setup, tool registration
│   │   └── transport.py        # SSE transport mount into FastAPI
│   └── admin/
│       ├── __init__.py
│       ├── routes.py           # Admin API endpoints (keys, policies, auth status)
│       ├── ui/
│       │   ├── static/         # CSS, JS (minimal — mostly HTMX + Tailwind CDN)
│       │   │   └── style.css
│       │   └── templates/      # Jinja2 templates
│       │       ├── base.html
│       │       ├── dashboard.html
│       │       ├── modules.html
│       │       ├── routes.html
│       │       ├── api_keys.html
│       │       ├── audit_log.html
│       │       └── auth_status.html
│       └── models.py           # Pydantic models for admin API
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_auth.py
│   ├── test_policy.py
│   ├── test_modules.py
│   ├── test_api.py
│   └── test_mcp.py
└── docs/
    └── plans/
        └── 2025-05-12-gatekeeper-v1.md  # This file
```

---

## Implementation Tasks

### Phase 1: Foundation

#### Task 1: Initialize project structure and pyproject.toml

**Objective:** Set up the project scaffold with all dependencies defined.

**Acceptance Criteria:**
- [x] `pyproject.toml` valid and `uv pip install -e .` succeeds with zero errors
- [x] `gatekeeper/__init__.py` exports `__version__` and `import gatekeeper; print(gatekeeper.__version__)` outputs `"0.1.0"`
- [x] `gatekeeper/config.py` loads settings from `GATEKEEPER_*` env vars and `ensure_secrets()` generates missing values
- [x] `.gitignore` covers `__pycache__/`, `*.pyc`, `.env`, `*.db`, `gatekeeper_token.json`, `data/`, `.venv/`
- [x] `.env.example` documents every `GATEKEEPER_*` variable with description and default
- [x] `git log` shows initial commit

**Files:**
- Create: `pyproject.toml`
- Create: `gatekeeper/__init__.py`
- Create: `gatekeeper/config.py`
- Create: `.gitignore`
- Create: `.env.example`

**Step 1: Write pyproject.toml with all dependencies**

```toml
[project]
name = "gatekeeper"
version = "0.1.0"
description = "Policy gateway for Google Workspace APIs with MCP server integration"
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
authors = [{ name = "Brimdor" }]
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "google-auth>=2.29",
    "google-auth-oauthlib>=1.2",
    "google-auth-httplib2>=0.2",
    "google-api-python-client>=2.127",
    "sqlalchemy[asyncio]>=2.0",
    "aiosqlite>=0.20",
    "pydantic-settings>=2.2",
    "jinja2>=3.1",
    "bcrypt>=4.1",
    "cryptography>=42.0",
    "httpx>=0.27",
    "python-multipart>=0.0.9",
    "mcp>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "ruff>=0.4",
]

[project.scripts]
gatekeeper = "gatekeeper.main:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 2: Write gatekeeper/__init__.py**

```python
"""Gatekeeper - Policy gateway for Google Workspace APIs."""

__version__ = "0.1.0"
```

**Step 3: Write gatekeeper/config.py**

pydantic-settings class with `env_prefix="GATEKEEPER_"`, fields for:
- host, port, debug, secret_key
- database_url (default: `sqlite+aiosqlite:///./gatekeeper.db`)
- google_client_id, google_client_secret, google_token_file
- admin_username, admin_password (auto-generated if empty)
- mcp_enabled, mcp_port
- api_key_prefix (default: `gkp_`)
- rate_limit_per_minute
- encryption_key (auto-generated if empty)
- drive_enabled, gmail_enabled, calendar_enabled
- cors_origins

`ensure_secrets()` method generates missing secrets on startup.

**Step 4: Write .gitignore**

Standard Python + SQLite + .env + token files.

**Step 5: Write .env.example**

Template with all GATEKEEPER_* vars documented.

**Step 6: Initialize git, commit**

```bash
cd /home/echo/gatekeeper
git init
git add .
git commit -m "init: project scaffold with pyproject.toml"
```

---

#### Task 2: Database layer — SQLAlchemy async models

**Objective:** Set up async SQLAlchemy with SQLite and define all ORM models.

**Acceptance Criteria:**
- [ ] `init_db()` creates a SQLite file with all 4 tables (ApiKey, RoutePolicy, AuditLog, GoogleToken)
- [ ] Fernet encryption round-trips: `encrypt_value("hello")` → decrypt → `"hello"` exactly
- [ ] `derive_fernet_key()` produces a valid 32-byte Fernet key from any 64-char hex string
- [ ] All 4 model classes have correct columns with correct types (verified by a test that creates each and queries it back)
- [ ] `uv run pytest tests/test_config.py tests/test_db.py -v` passes with ≥5 test cases

**Files:**
- Create: `gatekeeper/db.py`
- Create: `gatekeeper/models.py`
- Create: `gatekeeper/encryption.py`
- Create: `tests/conftest.py`
- Create: `tests/test_config.py`
- Create: `tests/test_db.py`

**Step 1: Write gatekeeper/db.py**

Async engine creation with `sqlite+aiosqlite`, `async_sessionmaker`, `Base` class, `init_db()` create-all function, `get_session()` dependency.

**Step 2: Write gatekeeper/models.py**

Four tables:
- `ApiKey`: id, name, key_hash, key_prefix, is_active, created_at, last_used_at, permissions (comma-separated module list or "*")
- `RoutePolicy`: id, module, route, enabled, policy_config (JSON text), description, created_at, updated_at
- `AuditLog`: id, api_key_prefix, module, route, method, path, status_code, response_summary, created_at (indexed)
- `GoogleToken`: id, service (unique), encrypted_token (encrypted JSON blob), updated_at

**Step 3: Write gatekeeper/encryption.py**

Fernet-based encrypt/decrypt helpers. `encrypt_value(plaintext: str, key: bytes) -> str`, `decrypt_value(ciphertext: str, key: bytes) -> str`. Key comes from `settings.encryption_key` (hex string → 32 bytes → Fernet key via base64). Module also provides `derive_fernet_key(hex_key: str) -> bytes`.

**Step 4: Write tests/conftest.py**

In-memory SQLite async session fixture for all tests.

**Step 5: Write tests/test_config.py**

Test that config loads from env vars, `ensure_secrets()` fills in missing values, non-empty secrets are preserved.

**Step 6: Write tests/test_db.py**

Test: create all tables, insert ApiKey round-trip, insert RoutePolicy round-trip, insert AuditLog round-trip, insert GoogleToken round-trip.

**Step 7: Verify with `uv run pytest tests/ -v`**

**Step 8: Commit**

```bash
git add gatekeeper/db.py gatekeeper/models.py gatekeeper/encryption.py tests/
git commit -m "feat: async SQLAlchemy models and encryption helpers"
```

---

#### Task 3: API key authentication module

**Objective:** Implement API key generation, hashing, and request validation.

**Acceptance Criteria:**
- [ ] `ApiKey.generate_key()` produces keys starting with `gkp_`, 40+ chars total, and the returned hash verifies with `bcrypt.checkpw()`
- [ ] Valid API key passes `validate_api_key()` and returns the ApiKey record with `last_used_at` updated
- [ ] Invalid (nonexistent) API key returns HTTP 401
- [ ] Disabled (`is_active=False`) API key returns HTTP 401
- [ ] Missing `X-Gatekeeper-API-Key` header returns HTTP 401 with message "Missing X-Gatekeeper-API-Key header"
- [ ] `require_admin()` rejects wrong username/password with HTTP 401
- [ ] `require_admin()` accepts correct credentials
- [ ] `uv run pytest tests/test_auth.py -v` passes with ≥7 test cases

**Files:**
- Create: `gatekeeper/auth.py`
- Create: `tests/test_auth.py`

**Step 1: Write gatekeeper/auth.py**

- `ApiKey` model already has `generate_key()` static method for key creation (prefix + random token, bcrypt hash, store hash + prefix)
- `validate_api_key()` FastAPI dependency: reads `X-Gatekeeper-API-Key` header, finds key by prefix match then bcrypt verify, updates `last_used_at`, raises 401 on failure
- `require_admin()` dependency: simple HTTP Basic auth check against `settings.admin_username` / `settings.admin_password`

**Step 2: Write tests/test_auth.py**

Test key generation (raw key format, hash verifiable, prefix matches), test validation (valid key passes, invalid key raises 401, disabled key raises 401, wrong prefix fails).

**Step 3: Run tests, verify all pass**

**Step 4: Commit**

```bash
git add gatekeeper/auth.py tests/test_auth.py
git commit -m "feat: API key authentication and admin auth"
```

---

#### Task 4: Policy engine

**Objective:** Implement route policy evaluation — allow/deny/transform.

**Acceptance Criteria:**
- [ ] `check_route()` returns `PolicyDecision(allowed=True)` when route policy exists and is enabled
- [ ] `check_route()` returns `PolicyDecision(allowed=False, reason="...")` when route is explicitly disabled
- [ ] `check_route()` returns `PolicyDecision(allowed=False, reason="No policy defined")` when no policy exists (default deny)
- [ ] `check_route()` returns `PolicyDecision(allowed=False)` when key lacks module permission (key has "drive" but route is "gmail")
- [ ] `check_route()` returns `PolicyDecision(allowed=True)` when key has permissions="*" (wildcard)
- [ ] `apply_request_transforms()` caps `maxResults` to policy limit (e.g., policy says 50, request has 200 → capped to 50)
- [ ] `apply_request_transforms()` filters `labelIds` to only those in `allowed_labels`
- [ ] `apply_request_transforms()` adds forced `query_filter` parameter
- [ ] `apply_response_filter()` strips `blocked_fields` from response dict
- [ ] `apply_response_filter()` caps array lengths per `max_items` config
- [ ] `uv run pytest tests/test_policy.py -v` passes with ≥10 test cases

**Files:**
- Create: `gatekeeper/policy.py`
- Create: `tests/test_policy.py`

**Step 1: Write gatekeeper/policy.py**

`PolicyEngine` class:
- `check_route(module, route, api_key_permissions)` → `PolicyDecision(allowed, reason, transformed_params)`
  - Check key's module permission (if not "*", check module in allowed list)
  - Look up RoutePolicy from DB
  - If no policy exists: default deny
  - If policy disabled: deny with reason
  - If policy enabled: return allowed with policy config as transforms
- `apply_request_transforms(params, policy_config)` → modified params
  - Cap `maxResults` / `max_results` / `pageSize` to policy limit
  - Filter `labelIds` to `allowed_labels` set
  - Add forced query params from `query_filter`
- `apply_response_filter(response_data, policy_config)` → filtered response
  - Strip `blocked_fields`
  - Cap array lengths via `max_items`

**Step 2: Write tests/test_policy.py**

Test: route allowed when policy enabled, denied when disabled, denied when no policy, denied when key lacks module permission, request transforms cap values, response filter strips fields.

**Step 3: Run tests**

**Step 4: Commit**

```bash
git add gatekeeper/policy.py tests/test_policy.py
git commit -m "feat: policy engine with request transforms and response filters"
```

---

#### Task 5: Module system — base classes and registration

**Objective:** Create the extensible module system that Drive, Gmail, Calendar plug into.

**Acceptance Criteria:**
- [ ] `load_module("drive")` returns a `DriveModule` instance with `name == "drive"`
- [ ] `load_module("gmail")` returns a `GmailModule` instance with `name == "gmail"`
- [ ] `load_module("calendar")` returns a `CalendarModule` instance with `name == "calendar"`
- [ ] `load_module("nonexistent")` returns `None`
- [ ] `load_enabled_modules(["drive", "calendar"])` returns exactly 2 module instances (gmail not loaded)
- [ ] Each module's `get_routes()` returns a non-empty list of `RouteDef` objects where every route_id starts with the module name
- [ ] Each module's `get_default_policies()` returns a dict keyed by route_id with `{enabled, config}` structure
- [ ] Each module's `get_mcp_tools()` returns valid MCP tool definitions with `name`, `description`, and `inputSchema` fields
- [ ] `RouteDef` validation: `route_id`, `method`, `google_path` are all required and non-empty
- [ ] `uv run pytest tests/test_modules.py -v` passes with ≥8 test cases

**Files:**
- Create: `gatekeeper/modules/__init__.py`
- Create: `gatekeeper/modules/base.py`
- Create: `gatekeeper/modules/route.py`
- Create: `tests/test_modules.py`

**Step 1: Write gatekeeper/modules/route.py**

`RouteDef` pydantic model:
- `route_id`: str (e.g. "gmail.messages.list")
- `method`: str (GET/POST/PUT/DELETE)
- `google_path`: str (e.g. "/gmail/v1/users/me/messages")
- `description`: str
- `input_schema`: dict (JSON Schema for MCP tool inputSchema)
- `default_policy`: dict (default policy config)
- `enabled_by_default`: bool

**Step 2: Write gatekeeper/modules/base.py**

`GoogleModule` ABC:
- `name`, `display_name`, `description`, `icon`, `required_scopes`
- `get_routes()` → list[RouteDef] (abstract)
- `get_default_policies()` → dict mapping route_id to {enabled, config}
- `get_mcp_tools()` → generates MCP tool definitions from routes

**Step 3: Write gatekeeper/modules/__init__.py**

Module registry:
- `AVAILABLE_MODULES` dict mapping name → import path
- `load_module(name)` → dynamically import and instantiate
- `load_enabled_modules(enabled_list)` → load and return list
- `get_loaded_modules()` → dict of currently loaded modules

**Step 4: Write tests/test_modules.py**

Test: module loading, unknown module returns None, loading all available modules, get_default_policies returns correct structure, get_mcp_tools generates valid tool defs.

**Step 5: Run tests**

**Step 6: Commit**

```bash
git add gatekeeper/modules/ tests/test_modules.py
git commit -m "feat: extensible module system with route definitions"
```

---

### Phase 2: Google Modules

#### Task 6: Drive module

**Objective:** Implement the Google Drive route definitions.

**Acceptance Criteria:**
- [ ] `DriveModule` has `name == "drive"`, `display_name == "Google Drive"`, `icon == "📁"`
- [ ] `get_routes()` returns exactly 5 `RouteDef` objects
- [ ] All 5 route_ids start with `"drive."`: `drive.files.list`, `drive.files.get`, `drive.files.export`, `drive.files.list_shared`, `drive.files.copy`
- [ ] `drive.files.copy` has `enabled_by_default == False` (write operation)
- [ ] All other routes have `enabled_by_default == True` (read operations)
- [ ] Every route has a non-empty `input_schema` dict with at least `"type": "object"` and `"properties"`
- [ ] Every route has a non-empty `description` string
- [ ] `required_scopes` includes `drive.readonly`
- [ ] `get_default_policies()` returns 5 entries matching the 5 routes
- [ ] Module imports cleanly: `from gatekeeper.modules.drive import Module`

**Files:**
- Create: `gatekeeper/modules/drive/__init__.py`

**Step 1: Write DriveModule**

Routes (all read-only by default):
- `drive.files.list` — List/search files (GET, policy: max_results=50)
- `drive.files.get` — Get file metadata by ID (GET)
- `drive.files.export` — Export Google Workspace doc to MIME type (GET)
- `drive.files.list_shared` — List files shared with user (GET, policy: max_results=50, query_filter="sharedWithMe=true")
- `drive.files.copy` — Copy a file (POST, enabled_by_default=False — write operation)

Required scopes: `https://www.googleapis.com/auth/drive.readonly` (and `drive` for copy)

Each route has a full `input_schema` (JSON Schema) and `default_policy`.

**Step 2: Commit**

```bash
git add gatekeeper/modules/drive/
git commit -m "feat: Google Drive module with 5 route definitions"
```

---

#### Task 7: Gmail module

**Objective:** Implement the Gmail route definitions.

**Acceptance Criteria:**
- [ ] `GmailModule` has `name == "gmail"`, `display_name == "Google Gmail"`, `icon == "📧"`
- [ ] `get_routes()` returns exactly 6 `RouteDef` objects
- [ ] All 6 route_ids start with `"gmail."`: `gmail.messages.list`, `gmail.messages.get`, `gmail.messages.send`, `gmail.drafts.list`, `gmail.drafts.create`, `gmail.labels.list`
- [ ] Write operations (`gmail.messages.send`, `gmail.drafts.create`) have `enabled_by_default == False`
- [ ] Read operations have `enabled_by_default == True`
- [ ] `gmail.messages.list` default policy includes `allowed_labels` and `exclude_labels` containing `"SPAM"` and `"TRASH"`
- [ ] `gmail.messages.send` default policy includes `max_recipients` constraint
- [ ] `required_scopes` includes `gmail.readonly`, `gmail.send`, `gmail.compose`
- [ ] Every route has non-empty `input_schema` and `description`
- [ ] Module imports cleanly: `from gatekeeper.modules.gmail import Module`

**Files:**
- Create: `gatekeeper/modules/gmail/__init__.py`

**Step 1: Write GmailModule**

Routes:
- `gmail.messages.list` — List messages (GET, policy: max_results=50, allowed_labels, exclude_labels=["SPAM","TRASH"])
- `gmail.messages.get` — Get message by ID (GET)
- `gmail.messages.send` — Send email (POST, enabled_by_default=False, policy: max_recipients=5)
- `gmail.drafts.list` — List drafts (GET, policy: max_results=50)
- `gmail.drafts.create` — Create draft (POST, enabled_by_default=False, policy: max_recipients=5)
- `gmail.labels.list` — List all labels (GET)

Required scopes: `gmail.readonly`, `gmail.send`, `gmail.compose`

**Step 2: Commit**

```bash
git add gatekeeper/modules/gmail/
git commit -m "feat: Gmail module with 6 route definitions"
```

---

#### Task 8: Calendar module

**Objective:** Implement the Google Calendar route definitions.

**Acceptance Criteria:**
- [ ] `CalendarModule` has `name == "calendar"`, `display_name == "Google Calendar"`, `icon == "📅"`
- [ ] `get_routes()` returns exactly 8 `RouteDef` objects
- [ ] All 8 route_ids start with `"calendar."`
- [ ] Write operations (`events.create`, `events.update`, `events.delete`) have `enabled_by_default == False`
- [ ] Read operations have `enabled_by_default == True`
- [ ] `calendar.events.list` default policy includes `max_results` cap
- [ ] `required_scopes` includes `calendar.readonly` and `calendar.events`
- [ ] Every route has non-empty `input_schema` and `description`
- [ ] Module imports cleanly: `from gatekeeper.modules.calendar import Module`

**Files:**
- Create: `gatekeeper/modules/calendar/__init__.py`

**Step 1: Write CalendarModule**

Routes:
- `calendar.events.list` — List events in a calendar (GET, policy: max_results=50)
- `calendar.events.get` — Get event by ID (GET)
- `calendar.events.create` — Create event (POST, enabled_by_default=False)
- `calendar.events.update` — Update event (PATCH, enabled_by_default=False)
- `calendar.events.delete` — Delete event (DELETE, enabled_by_default=False)
- `calendar.calendars.list` — List user's calendars (GET)
- `calendar.calendarlist.list` — List calendar entries (GET)
- `calendar.freebusy.query` — Free/busy query (POST)

Required scopes: `calendar.readonly` (read routes), `calendar.events` (write routes)

**Step 2: Commit**

```bash
git add gatekeeper/modules/calendar/
git commit -m "feat: Calendar module with 8 route definitions"
```

---

### Phase 3: Core Gateway

#### Task 9: Google OAuth client and credential management

**Objective:** Implement the one-time auth flow and automatic token refresh.

**Acceptance Criteria:**
- [ ] `GoogleCredentialManager.load_credentials()` returns `None` when no token file exists (no crash)
- [ ] `GoogleCredentialManager.load_credentials()` returns valid `Credentials` object from an existing token file
- [ ] `GoogleCredentialManager.refresh_if_needed()` silently returns valid credentials when not expired
- [ ] `GoogleCredentialManager.refresh_if_needed()` calls refresh and persists new token when expired
- [ ] `GoogleCredentialManager.refresh_if_needed()` returns `None` when no credentials exist at all
- [ ] `start_auth_flow()` opens browser, captures redirect, exchanges auth code for tokens, and saves encrypted token file
- [ ] Token file on disk contains encrypted data (not plaintext JSON — verified by reading file and checking it's not valid JSON)
- [ ] Encryption round-trip: credentials saved → loaded back → identical refresh_token
- [ ] `google_client.py` has a `credential_manager` singleton instance
- [ ] `uv run pytest tests/test_google_client.py -v` passes with ≥5 test cases

**Files:**
- Create: `gatekeeper/google_client.py`
- Create: `tests/test_google_client.py`

**Step 1: Write gatekeeper/google_client.py**

`GoogleCredentialManager`:
- `load_credentials()` → load from JSON file (encrypted at rest via `encryption.py`)
- `refresh_if_needed()` → refresh expired tokens using `google.auth.transport.requests.Request`
- `get_credentials()` → return valid creds, refreshing if needed
- `_save_credentials()` → persist refreshed token to file (encrypted)
- `start_auth_flow()` → run the desktop OAuth flow: start local HTTP server on random port, open browser to Google consent screen, capture redirect with auth code, exchange for tokens, save encrypted
- Scoped per-service: if only Drive is enabled, only request Drive scopes

`credential_manager` singleton instance.

**Step 2: Write conftest fixture for mocked Google OAuth**

Mock `Request` and `Credentials` for unit tests.

**Step 3: Test: token load, refresh, save cycle with mocked credentials**

**Step 4: Commit**

```bash
git add gatekeeper/google_client.py tests/test_google_client.py
git commit -m "feat: Google OAuth client with desktop flow and auto-refresh"
```

---

#### Task 10: API proxy layer

**Objective:** Implement the request proxy that calls Google APIs through the policy engine.

**Acceptance Criteria:**
- [ ] `GET /api/v1/gmail/messages/list` with valid API key and enabled route returns proxied Google API data (with mocked Google)
- [ ] Request with invalid API key returns HTTP 401
- [ ] Request with key lacking module permission returns HTTP 403 with reason message
- [ ] Request to disabled route returns HTTP 403 with "route is disabled" reason
- [ ] Request with `maxResults=200` to a route with `max_results=50` policy gets capped to 50 in the outgoing call
- [ ] Response containing a `blocked_fields` entry gets that field stripped before returning
- [ ] Every proxied request (success or failure) creates an `AuditLog` row in the database
- [ ] `uv run pytest tests/test_api.py -v` passes with ≥7 test cases

**Files:**
- Create: `gatekeeper/api/__init__.py`
- Create: `gatekeeper/api/router.py`
- Create: `gatekeeper/api/proxy.py`
- Create: `tests/test_api.py`

**Step 1: Write gatekeeper/api/proxy.py**

`GoogleProxy` class:
- `__init__(credential_manager, policy_engine)`
- `async call_google(module, route, params, api_key_record, request)` — the main proxy method:
  1. Load RouteDef from module
  2. Check policy via `policy_engine.check_route(module.name, route.route_id, api_key_record.permissions)`
  3. If denied: return 403 with reason
  4. Apply request transforms via `policy_engine.apply_request_transforms(params, policy_config)`
  5. Get Google credentials
  6. Build Google API request (using `httpx.AsyncClient` directly against REST endpoints)
  7. Execute request
  8. Apply response filter via `policy_engine.apply_response_filter(response, policy_config)`
  9. Log to audit log
  10. Return filtered response

**Step 2: Write gatekeeper/api/router.py**

Dynamic FastAPI router that mounts module sub-routers:
- For each loaded + enabled module, create a sub-router at `/api/v1/{module_name}/`
- Endpoints call `GoogleProxy.call_google()` with the authenticated API key

**Step 3: Write tests with mocked Google API responses**

Test: successful proxy returns data, policy denied returns 403, request transforms applied, response filters applied, audit log written.

**Step 4: Commit**

```bash
git add gatekeeper/api/ tests/test_api.py
git commit -m "feat: API proxy layer with policy-enforced Google API calls"
```

---

#### Task 11: Audit logging

**Objective:** Implement request audit logging to SQLite.

**Acceptance Criteria:**
- [ ] `log_request()` inserts an `AuditLog` row with all required fields populated
- [ ] `log_request()` truncates `response_summary` to 200 characters (longer strings are cut, not errored)
- [ ] `log_request()` does not raise an exception even if the DB operation fails (errors are logged, not propagated)
- [ ] Every successful and failed proxied request creates exactly one audit log entry
- [ ] Audit log entries have accurate `api_key_prefix`, `module`, `route`, `method`, `path`, and `status_code`

**Files:**
- Create: `gatekeeper/logging.py`

**Step 1: Write gatekeeper/logging.py**

`log_request()` async function:
- Takes: api_key_prefix, module, route, method, path, status_code, response_summary
- Creates AuditLog row in DB
- Truncates response_summary to 200 chars
- Catches and logs DB errors without failing the request

**Step 2: Integrate into api/proxy.py**

Call `log_request()` after every proxied request (success or failure).

**Step 3: Commit**

```bash
git add gatekeeper/logging.py
git commit -m "feat: audit logging for all gateway requests"
```

---

#### Task 12: FastAPI application assembly and CLI

**Objective:** Wire everything together — FastAPI app, lifespan, CLI entry point.

**Acceptance Criteria:**
- [ ] `gatekeeper init` creates the SQLite DB file and seeds default RoutePolicy rows for all enabled module routes
- [ ] `gatekeeper serve` starts uvicorn and `GET /health` returns `{"status": "ok", "version": "0.1.0"}`
- [ ] `gatekeeper serve` prints admin credentials and a default API key to stdout on first run (when no keys exist)
- [ ] `gatekeeper key create --name test` generates a key starting with `gkp_` and prints the full key (only shown once)
- [ ] `gatekeeper key list` shows key prefix and name for all keys
- [ ] `gatekeeper key revoke --prefix gkp_xxxx` deactivates the key
- [ ] `gatekeeper status` prints config summary without errors
- [ ] `gatekeeper auth` prints instructions for the OAuth flow (does not hang in headless environments)
- [ ] CORS middleware configured per `GATEKEEPER_CORS_ORIGINS`
- [ ] Admin routes mounted at `/admin/`
- [ ] API routes mounted at `/api/v1/`
- [ ] MCP endpoint mounted at `/mcp` (if `GATEKEEPER_MCP_ENABLED=true`)

**Files:**
- Create: `gatekeeper/main.py`

**Step 1: Write gatekeeper/main.py**

- `create_app()` factory function:
  - FastAPI app with lifespan
  - Lifespan: `init_db()`, load enabled modules, seed default RoutePolicies, register API routers, mount admin UI
  - CORS middleware (from settings)
  - Mount `/api/v1/` router
  - Mount `/admin/` routes
  - Mount `/mcp` SSE endpoint (if MCP enabled)
  - Health check: `GET /health` → `{"status": "ok", "version": "0.1.0"}`
  - Startup: if no API keys exist, generate a default admin key and print it to stdout

- `cli()` function (entry point):
  - argparse CLI with subcommands:
    - `gatekeeper serve` — start uvicorn server
    - `gatekeeper auth` — run the Google OAuth desktop flow
    - `gatekeeper key create --name <name> [--permissions <modules>]` — generate a new API key
    - `gatekeeper key list` — list API key prefixes and names
    - `gatekeeper key revoke --prefix <prefix>` — revoke an API key
    - `gatekeeper init` — initialize DB and seed default policies
    - `gatekeeper status` — show config summary

**Step 2: Verify app boots with `uv run gatekeeper serve`**

**Step 3: Commit**

```bash
git add gatekeeper/main.py
git commit -m "feat: FastAPI app assembly, lifespan, and CLI entry point"
```

---

### Phase 4: MCP Server

#### Task 13: MCP server with SSE transport

**Objective:** Expose enabled routes as MCP tools via SSE-over-HTTP.

**Acceptance Criteria:**
- [ ] Connecting to `/mcp` via SSE establishes a connection without error
- [ ] `tools/list` returns only tools for routes that are currently enabled in the RoutePolicy table
- [ ] Disabling a route via admin API and calling `tools/list` again excludes that tool
- [ ] Enabling a previously disabled route and calling `tools/list` includes that tool (dynamic discovery)
- [ ] Each tool name follows the pattern `{module}__{route_id_with_underscores}` (e.g., `gmail__messages_list`)
- [ ] Each tool has a valid `inputSchema` matching the RouteDef's `input_schema`
- [ ] `tools/call` with a valid tool name and API key returns proxied Google API data (with mocked Google)
- [ ] `tools/call` with an invalid API key returns an error
- [ ] `tools/call` to a tool whose route is disabled returns an error
- [ ] `uv run pytest tests/test_mcp.py -v` passes with ≥5 test cases

**Files:**
- Create: `gatekeeper/mcp_server/__init__.py`
- Create: `gatekeeper/mcp_server/transport.py`
- Create: `tests/test_mcp.py`

**Step 1: Write gatekeeper/mcp_server/__init__.py**

- `create_mcp_server(gateway_app)` — creates an MCP server instance
- Scans all enabled modules and routes
- For each enabled route policy, registers an MCP tool:
  - Tool name: `{module}__{route_id}` with dots replaced by underscores
  - Tool description: from RouteDef.description
  - Tool inputSchema: from RouteDef.input_schema
  - Tool handler: validates API key from MCP context, calls `GoogleProxy.call_google()`, returns result

- Dynamic tool list: when `tools/list` is called, only return tools for currently enabled routes

**Step 2: Write gatekeeper/mcp_server/transport.py**

- Mount MCP SSE server onto the FastAPI app at `/mcp`
- Use `mcp` SDK's SSE transport
- API key passed in MCP request metadata: `{"api_key": "gkp_..."}`

**Step 3: Write tests/test_mcp.py**

Test: MCP server returns enabled tools, tool call routes through policy engine, disabled routes not in tool list.

**Step 4: Commit**

```bash
git add gatekeeper/mcp_server/ tests/test_mcp.py
git commit -m "feat: MCP server with SSE transport and dynamic tool discovery"
```

---

### Phase 5: Admin WebUI

#### Task 14: Admin API endpoints

**Objective:** REST API endpoints for managing the gateway.

**Acceptance Criteria:**
- [ ] `GET /admin/api/dashboard` returns JSON with `total_requests`, `active_keys`, `enabled_routes`, and `auth_status` fields
- [ ] `POST /admin/api/keys` with `{"name": "test", "permissions": "*"}` creates a key and returns the raw key (which starts with `gkp_`)
- [ ] `GET /admin/api/keys` lists all keys without exposing `key_hash` or the full raw key
- [ ] `DELETE /admin/api/keys/{key_id}` deactivates the key (sets `is_active=False`)
- [ ] `GET /admin/api/modules` lists all three modules with their enabled status
- [ ] `POST /admin/api/modules/drive/toggle` flips the enabled status of Drive and returns the new status
- [ ] `PATCH /admin/api/routes/{route_id}` with `{"enabled": false}` disables the route and persists to DB
- [ ] `GET /admin/api/audit?module=gmail` returns only audit log entries where `module=gmail`
- [ ] `GET /admin/api/auth/status` returns `{"connected": false}` when no Google credentials are stored
- [ ] All admin endpoints require HTTP Basic Auth; unauthenticated requests return HTTP 401
- [ ] `uv run pytest tests/test_admin_api.py -v` passes with ≥10 test cases

**Files:**
- Create: `gatekeeper/admin/__init__.py`
- Create: `gatekeeper/admin/routes.py`
- Create: `gatekeeper/admin/models.py` (Pydantic request/response models)

**Step 1: Write gatekeeper/admin/models.py**

Pydantic models:
- `ApiKeyCreate(name: str, permissions: str = "*")`, `ApiKeyResponse(...)`, `ApiKeyCreated(name, key_prefix, raw_key)`
- `RoutePolicyUpdate(enabled: bool | None, policy_config: dict | None, description: str | None)`
- `RoutePolicyResponse(id, module, route, enabled, policy_config, description)`
- `AuditLogResponse(...)`
- `AuthStatus(connected: bool, service: str, scopes: list[str])`

**Step 2: Write gatekeeper/admin/routes.py**

Admin router at `/admin/api/`:
- All endpoints require `require_admin()` dependency
- Dashboard, keys CRUD, modules toggle, routes update, audit log, auth status

**Step 3: Commit**

```bash
git add gatekeeper/admin/ 
git commit -m "feat: admin API endpoints for keys, policies, audit, auth"
```

---

#### Task 15: Admin WebUI — Base template and dashboard

**Objective:** HTMX + Jinja2 + Tailwind CSS admin interface.

**Acceptance Criteria:**
- [ ] `GET /admin/` returns valid HTML with a `<title>` containing "Gatekeeper"
- [ ] Page includes Tailwind CSS via CDN (`<script src="https://cdn.tailwindcss.com">`)
- [ ] Page includes HTMX via CDN (`<script src="https://unpkg.com/htmx.org">`)
- [ ] Sidebar navigation includes links to: Dashboard, Modules, Routes, API Keys, Audit Log, Auth Status
- [ ] Dashboard page shows stat cards for: total requests, active keys, enabled routes, auth status
- [ ] Dashboard shows module cards for Drive, Gmail, Calendar with enabled/disabled badges
- [ ] Page uses dark theme (dark background, light text — not white background)
- [ ] Jinja2 template inheritance: `dashboard.html` extends `base.html`
- [ ] `$ curl -s http://localhost:8080/admin/ | head -20` returns HTML without errors

**Files:**
- Create: `gatekeeper/admin/ui/templates/base.html`
- Create: `gatekeeper/admin/ui/templates/dashboard.html`
- Create: `gatekeeper/admin/ui/static/style.css`

**Step 1–6:** Write templates, static CSS, mount in FastAPI, verify dashboard loads.

**Step 7: Commit**

```bash
git add gatekeeper/admin/ui/
git commit -m "feat: admin WebUI base template and dashboard"
```

---

#### Task 16: Admin WebUI — Module and route management pages

**Objective:** UI for enabling/disabling modules and configuring route policies.

**Acceptance Criteria:**
- [ ] `GET /admin/modules` renders a page showing all 3 modules (Drive, Gmail, Calendar) as cards
- [ ] Each module card shows: icon, display name, description, enabled badge (green/disabled or red/disabled)
- [ ] Clicking a module toggle switch sends `POST /admin/api/modules/{module}/toggle` via HTMX and updates the badge
- [ ] Module cards show the required Google scopes for that module
- [ ] `GET /admin/routes` renders a page with a table of route policies
- [ ] Route table has a dropdown filter to show routes for a specific module
- [ ] Each route row shows: module name, route ID, description, enabled toggle, expandable policy config
- [ ] Clicking "Edit Policy" expands inline JSON editor textarea with current policy config
- [ ] Saving policy config sends `PATCH /admin/api/routes/{route_id}` and the table updates without full page reload (HTMX)
- [ ] Disabling a route toggles the badge and persists to the database

**Files:**
- Create: `gatekeeper/admin/ui/templates/modules.html`
- Create: `gatekeeper/admin/ui/templates/routes.html`

**Steps:** Write templates with HTMX interactivity. Commit.

---

#### Task 17: Admin WebUI — API key management and audit log pages

**Objective:** UI for creating/revoking API keys and viewing audit logs.

**Acceptance Criteria:**
- [ ] `GET /admin/keys` renders a page with a table of all API keys
- [ ] Table columns: name, prefix, active status, permissions, last used timestamp, created timestamp
- [ ] "Create Key" button opens inline form with name input and permissions dropdown
- [ ] Creating a key shows the raw key in a copyable box with a warning: "This is the only time the full key will be shown."
- [ ] Copy button copies the raw key to clipboard
- [ ] "Revoke" button triggers confirm dialog and sends `DELETE /admin/api/keys/{id}` on confirm
- [ ] `GET /admin/audit` renders a page with an audit log table
- [ ] Audit log columns: timestamp, key prefix, module, route, method, path, status code
- [ ] Filter options: key prefix dropdown, module dropdown, date range (from/to)
- [ ] Applying filters uses HTMX to swap the table body without full page reload
- [ ] Pagination works (20 entries per page, next/previous links)

**Files:**
- Create: `gatekeeper/admin/ui/templates/api_keys.html`
- Create: `gatekeeper/admin/ui/templates/audit_log.html`

**Steps:** Write templates with HTMX interactivity. Commit.

---

#### Task 18: Admin WebUI — Auth status page

**Objective:** Page showing Google OAuth connection status and reconnect button.

**Acceptance Criteria:**
- [ ] `GET /admin/auth` renders a page showing Google OAuth connection status
- [ ] When connected: shows green "Connected" badge, last refresh time, and scopes granted
- [ ] When disconnected: shows red "Disconnected" badge and instructions to run `gatekeeper auth` CLI command
- [ ] Page shows per-module scope requirements (which scopes each enabled module needs)
- [ ] "Reconnect" button visible when connected; shows `gatekeeper auth` instructions when disconnected (since re-auth requires CLI)
- [ ] Page uses same base template and dark theme as other admin pages

**Files:**
- Create: `gatekeeper/admin/ui/templates/auth_status.html`

**Steps:** Write template. Commit.

---

### Phase 6: Containerization, Docs, and Deployment

#### Task 19: Podman container setup and compose

**Objective:** Multi-arch Podman image and podman-compose.yml for easy deployment (RPi compatible).

**Acceptance Criteria:**
- [ ] `podman build -t gatekeeper .` completes without error
- [ ] `podman run --rm gatekeeper gatekeeper --help` outputs CLI help text
- [ ] `podman-compose up -d` starts the container and `podman-compose ps` shows the service as running
- [ ] `curl http://localhost:8080/health` returns `{"status": "ok", "version": "0.1.0"}`
- [ ] Podman image builds for `linux/amd64` (verified on current system)
- [ ] Containerfile uses multi-stage build to minimize final image size
- [ ] Volume mount at `/data` persists the SQLite DB and Google token across container restarts
- [ ] `.dockerignore` excludes `.git`, `.venv`, `__pycache__`, `*.pyc`, `.env`, `data/`

**Files:**
- Create: `Dockerfile` (Podman-compatible Containerfile)
- Create: `docker-compose.yml` (podman-compose compatible)
- Create: `.dockerignore`

**Step 1: Write Dockerfile**

Multi-stage build:
- Stage 1: `python:3.11-slim` bookworm, install uv, copy project, `uv pip install .`
- Multi-arch: supports both `linux/amd64` and `linux/arm64` (RPi)
- Expose port 8080
- Volume: `/data` for SQLite DB and Google token file
- Entry point: `gatekeeper serve --host 0.0.0.0 --port 8080`

**Step 2: Write docker-compose.yml**

```yaml
services:
  gatekeeper:
    build: .
    ports:
      - "8080:8080"
      - "8081:8081"  # MCP SSE
    volumes:
      - ./data:/data
    environment:
      - GATEKEEPER_DATABASE_URL=sqlite+aiosqlite:////data/gatekeeper.db
      - GATEKEEPER_GOOGLE_TOKEN_FILE=/data/google_token.json
      - GATEKEEPER_SECRET_KEY=${GATEKEEPER_SECRET_KEY}
      - GATEKEEPER_ENCRYPTION_KEY=${GATEKEEPER_ENCRYPTION_KEY}
      - GATEKEEPER_GOOGLE_CLIENT_ID=${GATEKEEPER_GOOGLE_CLIENT_ID}
      - GATEKEEPER_GOOGLE_CLIENT_SECRET=${GATEKEEPER_GOOGLE_CLIENT_SECRET}
    restart: unless-stopped
```

**Step 3: Write .dockerignore**

Standard Python ignores + data/, .env

**Step 4: Build and test with Podman**

```bash
podman build -t gatekeeper .
podman run --rm gatekeeper gatekeeper --help
```

**Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: multi-arch Podman container setup with compose"
```

---

#### Task 20: README documentation

**Objective:** Complete README with setup, configuration, and usage instructions.

**Acceptance Criteria:**
- [ ] README contains all 12 sections listed in the plan
- [ ] Quick Start section: running the 4 commands (`uv pip install`, `gatekeeper init`, `gatekeeper auth`, `gatekeeper serve`) produces a running gateway
- [ ] Configuration section documents every `GATEKEEPER_*` env var with type, default, and description
- [ ] Google OAuth Setup section has step-by-step instructions for creating a Google Cloud project, enabling APIs, and getting client ID/secret
- [ ] Module Reference section lists every route in all 3 modules with description, method, default policy, and enabled_by_default status
- [ ] Security section covers: TLS recommendation, API key management, token encryption, network binding, CORS
- [ ] README has at least one architecture diagram (ASCII or code block)
- [ ] Container/deployment section references Podman (not Docker)

**Files:**
- Modify: `README.md`

**Steps:** Write comprehensive README. Commit.

---

#### Task 21: Integration testing and end-to-end verification

**Objective:** Full-stack integration test — API, admin UI, MCP, and policy enforcement all working together.

**Acceptance Criteria:**
- [ ] `uv pip install -e ".[dev]"` completes without errors
- [ ] `gatekeeper init` creates the database file and seeds all default route policies
- [ ] `gatekeeper serve` starts without errors and binds to the configured host:port
- [ ] `GET /health` returns `{"status": "ok", "version": "0.1.0"}`
- [ ] `GET /admin/` returns valid HTML with the dashboard (HTTP 200)
- [ ] Admin login with generated credentials succeeds (HTTP 200)
- [ ] Admin login with wrong credentials fails (HTTP 401)
- [ ] `GET /mcp` establishes an SSE connection
- [ ] `gatekeeper key create --name integration-test` succeeds and prints a key starting with `gkp_`
- [ ] `GET /api/v1/gmail/messages/list` with the created API key returns either proxied data or a meaningful error (not a 500)
- [ ] `uv run pytest tests/ -v` passes with all test cases green (zero failures)
- [ ] SQLite database file exists and contains seeded RoutePolicy rows for all module routes
- [ ] **E2E: Create API key via admin API, use it to call a route, verify audit log entry exists in DB**
- [ ] **E2E: Disable a route via admin API, attempt call returns 403, re-enable, call succeeds (with mocked Google)**
- [ ] **E2E: Admin UI pages all render without JavaScript errors (HTML validity check)**
- [ ] **E2E: HTMX interactions work: toggle module enable/disable, toggle route enable/disable, create API key — each verified via `httpx` test client**
- [ ] **E2E: MCP `tools/list` returns only tools for enabled routes; disabling a route removes it from next `tools/list` call**
- [ ] **E2E: Policy enforcement end-to-end: request with `maxResults=200` to route with `max_results=50` policy returns data capped at 50**

**Files:**
- Create: `tests/test_e2e.py`

**Steps:**
1. Install deps, init DB, start server
2. Verify all endpoints listed above
3. Write and run E2E test suite (`tests/test_e2e.py`)
4. Fix any issues found
5. Final commit

---

#### Task 22: Push to GitHub and tag release

**Objective:** Push to brimdor/gatekeeper and tag the v0.1.0-alpha.1 release.

**Acceptance Criteria:**
- [ ] `git remote -v` shows `origin` pointing to `github.com:brimdor/gatekeeper`
- [ ] `git push origin main` succeeds and all commits are visible on GitHub
- [ ] `git tag v0.1.0-alpha.1` and `git push origin v0.1.0-alpha.1` creates a release tag
- [ ] Repository is private (only visible to collaborators)
- [ ] All 22 task commits are present in `git log --oneline`
- [ ] `.env.example` is present but `.env` is NOT committed (verified by absence in `git ls-files`)

**Steps:** Add remote, push, tag, verify.

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 | 1–5 | Foundation: project, DB, auth, policy, modules |
| 2 | 6–8 | Google modules: Drive, Gmail, Calendar |
| 3 | 9–12 | Core: OAuth client, proxy, audit, app assembly |
| 4 | 13 | MCP server with SSE transport |
| 5 | 14–18 | Admin WebUI: API, dashboard, modules, routes, keys, auth |
| 6 | 19–22 | Podman, docs, E2E testing, push & tag |

**Total: 22 tasks**, each with measurable acceptance criteria, independently testable.