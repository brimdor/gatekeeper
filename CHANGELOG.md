# Changelog

All notable changes to Gatekeeper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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