# Changelog

All notable changes to Gatekeeper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

See [docs/UPGRADING.md](docs/UPGRADING.md) for migration steps associated with each release.

## [Unreleased]

### Added
- Major documentation completion initiative:
  - New architecture and design walkthrough: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
  - New REST API reference: [docs/API_REFERENCE.md](docs/API_REFERENCE.md)
  - New auto-generated route reference: [docs/ROUTES.md](docs/ROUTES.md) and `scripts/generate_routes_doc.py`
  - New module development guide: [docs/MODULE_DEVELOPMENT.md](docs/MODULE_DEVELOPMENT.md)
  - New agent error handling guide: [docs/AGENT_ERRORS.md](docs/AGENT_ERRORS.md)
  - New policy configuration reference: [docs/POLICY_REFERENCE.md](docs/POLICY_REFERENCE.md)
  - New agent testing guide: [docs/AGENT_TESTING.md](docs/AGENT_TESTING.md)
  - New upgrade and migration guide: [docs/UPGRADING.md](docs/UPGRADING.md)
- Rewrote [README.md](README.md) to remove duplicated Quick Start, route tables, OAuth steps, and systemd instructions; added Documentation index.
- Slimmed [docs/SETUP.md](docs/SETUP.md) and linked to canonical sources for OAuth, routes, and systemd.
- Updated [docs/MCP_SETUP_AGENT.md](docs/MCP_SETUP_AGENT.md) and [docs/MCP_SETUP_HUMAN.md](docs/MCP_SETUP_HUMAN.md) with Drive scopes, deduplicated content, and cross-references to new reference docs.
- Added real `gatekeeper status` output samples to [docs/SETUP.md](docs/SETUP.md) and [docs/PODMAN_DEPLOYMENT.md](docs/PODMAN_DEPLOYMENT.md).
- Updated [CONTRIBUTING.md](CONTRIBUTING.md) to link to the module development guide and remind contributors to regenerate `docs/ROUTES.md` after route changes.

## [v0.3.0-rc.1] — 2026-07-08 — Canary release candidate

### Added
- 16 new routes for Google Sheets, Docs, and Slides in the Drive module
- Support for multi-host routing in GoogleProxy (base_url override)
- Expanded OAuth scopes for Drive to include spreadsheets, documents, and presentations

## [0.1.0] - 2025-05-13

### Added
- Policy gateway for Google Workspace APIs (Drive, Gmail, Calendar)
- MCP server integration for AI agent access
- Admin web UI and REST API for key management, module toggling, and route policies
- Device authorization flow for Google OAuth (`gatekeeper auth`)
- API key authentication with bcrypt hashing and prefix matching
- Route-level policy engine (enable/disable, request transforms, response filters)
- Audit logging for all API requests
- Fernet-encrypted Google OAuth token storage
- Auto-generated secrets (admin password, encryption key) with persistence
- CORS middleware with configurable origins
- Rate limiting (configurable per minute)
- Multi-arch Docker/Podman support (amd64 + arm64)
- Turn-key install script
- Comprehensive test suite (196 tests)

### Security
- Constant-time admin password comparison (`hmac.compare_digest`)
- Proper HTTP status codes for all proxy errors (401, 403, 404 instead of 200)
- Route policies default to deny — write operations disabled by default

### Fixed
- OAuth token refresh when expiry is None (was silently using stale tokens)
- MCP tool naming redundancy (was `drive__drive_files_list`, now `drive__files_list`)
- Admin API key creation now returns the `id` field
- Policy error messages no longer double the module prefix
- PUT HTTP method support for Gmail drafts.update
