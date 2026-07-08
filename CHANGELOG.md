# Changelog

## [v0.3.1-rc.2] — 2026-07-08 — Canary release candidate

### Fixed
- Fixed 404 on `drive.files.update` by correcting parameter merge logic in the REST router.
- Enabled `drive.files.update` by default to remove redundant admin activation step.
- Improved audit log with `response_message` to clearly distinguish between 403 (denied) and 404 (not found) errors.
- Corrected misnamed test `test_no_policy_returns_404` to `test_no_policy_returns_403`.
- Added regression tests for PATCH/POST/PUT parameter merging and end-to-end validation of file moves in Google Drive.

### Changed
- MCP tools now prefer the `X-Gatekeeper-API-Key` HTTP header for authentication; the `api_key` argument remains as a backward-compatible fallback.
