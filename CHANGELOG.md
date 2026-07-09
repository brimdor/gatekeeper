# Changelog

## [v0.3.2-rc.1] — 2026-07-09 — Forms and Apps Script modules

### Added
- New `forms` module with 10 Google Forms API routes, all default-disabled.
- New `appsscript` module with 16 Google Apps Script API routes, all default-disabled.
- Per-route `base_url` routing to `forms.googleapis.com` and `script.googleapis.com`.
- New settings `GATEKEEPER_FORMS_ENABLED` and `GATEKEEPER_APPSSCRIPT_ENABLED` (default `false`).
- Updated `docs/ROUTES.md`, `docs/API_REFERENCE.md`, `README.md`, and `docs/SETUP.md`.

## [v0.3.1-rc.2] — 2026-07-08 — Canary release candidate

### Fixed
- Fixed 404 on `drive.files.update` by correcting parameter merge logic in the REST router.
- Enabled `drive.files.update` by default to remove redundant admin activation step.
- Improved audit log with `response_message` to clearly distinguish between 403 (denied) and 404 (not found) errors.
- Corrected misnamed test `test_no_policy_returns_404` to `test_no_policy_returns_403`.
- Added regression tests for PATCH/POST/PUT parameter merging and end-to-end validation of file moves in Google Drive.

### Changed
- MCP tools now prefer the `X-Gatekeeper-API-Key` HTTP header for authentication; the `api_key` argument remains as a backward-compatible fallback.
