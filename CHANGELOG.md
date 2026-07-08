1|# Changelog
2|
3|All notable changes to Gatekeeper will be documented in this file.
4|
5|The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),

## [v0.3.0-rc.1] — 2026-07-08 — Canary release candidate

### Added
- 16 new routes for Google Sheets, Docs, and Slides in the Drive module
- Support for multi-host routing in GoogleProxy (base_url override)
- Expanded OAuth scopes for Drive to include spreadsheets, documents, and presentations

6|and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
7|
8|## [0.1.0] - 2025-05-13
9|
10|### Added
11|- Policy gateway for Google Workspace APIs (Drive, Gmail, Calendar)
12|- MCP server integration for AI agent access
13|- Admin web UI and REST API for key management, module toggling, and route policies
14|- Device authorization flow for Google OAuth (`gatekeeper auth`)
15|- API key authentication with bcrypt hashing and prefix matching
16|- Route-level policy engine (enable/disable, request transforms, response filters)
17|- Audit logging for all API requests
18|- Fernet-encrypted Google OAuth token storage
19|- Auto-generated secrets (admin password, encryption key) with persistence
20|- CORS middleware with configurable origins
21|- Rate limiting (configurable per minute)
22|- Multi-arch Docker/Podman support (amd64 + arm64)
23|- Turn-key install script
24|- Comprehensive test suite (196 tests)
25|
26|### Security
27|- Constant-time admin password comparison (`hmac.compare_digest`)
28|- Proper HTTP status codes for all proxy errors (401, 403, 404 instead of 200)
29|- Route policies default to deny — write operations disabled by default
30|
31|### Fixed
32|- OAuth token refresh when expiry is None (was silently using stale tokens)
33|- MCP tool naming redundancy (was `drive__drive_files_list`, now `drive__files_list`)
34|- Admin API key creation now returns the `id` field
35|- Policy error messages no longer double the module prefix
36|- PUT HTTP method support for Gmail drafts.update