# Intelligence Brief: Gatekeeper Agent Documentation Audit and Gap Analysis

## Summary

Gatekeeper has a solid documentation foundation with 7 core doc files (README, SETUP, MCP_SETUP_AGENT, MCP_SETUP_HUMAN, PODMAN_DEPLOYMENT, CONTRIBUTING, SECURITY, CHANGELOG) plus an install script and .env templates. The agent-facing documentation (MCP_SETUP_AGENT.md) is accurate, thorough, and well-structured. However, significant gaps exist: there is no architecture overview, no module development guide, no error handling guide, no REST API reference, no troubleshooting guide specifically for agents, and no changelog-to-upgrade path documentation. Several minor inaccuracies and duplications exist in the current docs.

---

## Evidence

| # | Claim | Source | Confidence |
|---|-------|--------|------------|
| 1 | README.md duplicates the Quick Start section (lines 9-41 and lines 77-110) | README.md direct inspection | Certain |
| 2 | MCP_SETUP_AGENT.md is accurate — tool names, API key requirements, SSE transport, error codes all match the source code | mcp_server/__init__.py lines 85-293; README.md; MCP_SETUP_AGENT.md | Certain |
| 3 | Tool name mapping (`drive.files.list` → `drive__files_list`) is correctly documented and matches the code in mcp_server/__init__.py lines 154-161 | mcp_server/__init__.py | Certain |
| 4 | The `api_key` parameter is indeed required on every MCP tool call — confirmed in code at mcp_server/__init__.py lines 188-199 | mcp_server/__init__.py | Certain |
| 5 | Disabled routes do NOT appear in `list_tools` — confirmed in code at mcp_server/__init__.py lines 139-142 | mcp_server/__init__.py | Certain |
| 6 | SSE transport is required — the MCP server uses FastMCP with SSE app, and `transport.py` confirms this | mcp_server/transport.py; mcp_server/__init__.py lines 296-329 | Certain |
| 7 | DNS rebinding protection is implemented but only documented in PODMAN_DEPLOYMENT.md (line 502-515) and mentioned briefly in README.md. MCP_SETUP_AGENT.md doesn't mention 421 errors | PODMAN_DEPLOYMENT.md; README.md | Certain |
| 8 | The Drive module includes Sheets/Documents/Presentations scopes (`spreadsheets`, `documents`, `presentations`) that are NOT documented in MCP_SETUP_AGENT.md or MCP_SETUP_HUMAN.md scopes tables | drive/__init__.py lines 18-23 | Likely |
| 9 | Route definitions include `binary_response` and `multipart_upload` fields, plus `query_params`, `base_url` for per-route API base URLs — none of these are documented in agent-facing docs | modules/route.py | Likely |
| 10 | The `RouteDef.base_url` field supports per-route Google API base URLs (for Sheets/Docs/Slides APIs) but this capability is not mentioned anywhere in the docs | modules/route.py lines 43-45 | Likely |
| 11 | There is no REST API reference document — the README shows 3 curl examples but no comprehensive endpoint listing | README.md; docs/ directory listing | Certain |
| 12 | SETUP.md is comprehensive (647 lines) but the route tables are duplicated in README.md, SETUP.md, and MCP_SETUP_AGENT.md — creating maintenance burden | All three files | Certain |
| 13 | The `install.sh` script (587 lines) has an interactive wizard mode, but this is only briefly mentioned in SETUP.md line 37-55 | install.sh; SETUP.md | Certain |
| 14 | The `gatekeeper status` CLI command is documented in README and SETUP but its output format is never shown | README.md line 425; SETUP.md line 609 | Likely |
| 15 | There is no architecture overview or "how it works" document — the closest is the ASCII diagram in README.md lines 57-72 | README.md | Certain |
| 16 | There is no module development guide — CONTRIBUTING.md mentions "add new modules under `gatekeeper/modules/`" but provides no detailed walkthrough | CONTRIBUTING.md line 44 | Certain |
| 17 | The `GoogleModule` base class and `RouteDef` dataclass are well-documented in code but there is no guide for adding new modules | modules/base.py; modules/route.py | Likely |
| 18 | No changelog-to-upgrade guide exists — CHANGELOG.md only lists changes, no migration instructions | CHANGELOG.md | Certain |
| 19 | The `service.py` CLI subcommands (install, enable, disable, etc.) are documented in README.md and SETUP.md but systemd unit file creation is duplicated | README.md; SETUP.md lines 297-327 | Likely |
| 20 | MCP_SETUP_AGENT.md correctly states agents cannot modify policies, keys, or admin settings — confirmed by the admin API requiring HTTP Basic Auth | MCP_SETUP_AGENT.md lines 244-250; admin/routes.py | Likely |
| 21 | The `GATEKEEPER_MCP_ALLOWED_HOSTS` env var uses JSON array format in .env.example but the `hosts add/remove` CLI commands exist — docs cover both, which is good | .env.example; README.md lines 196-201; MCP_SETUP_HUMAN.md lines 79-93 | Certain |
| 22 | The `permissions` field on API keys (e.g., `--permissions drive`) is documented but the exact format and valid values are not specified — code shows it's comma-separated module names or `"*"` | models.py line 25; README.md line 211 | Likely |
| 23 | No documentation on what happens when a module is disabled after being enabled (routes become invisible in list_tools, policy data remains in DB) | mcp_server/__init__.py lines 139-142 | Likely |
| 24 | The `calendar.freebusy.query` route is a POST route that is enabled by default — unusual pattern not documented | README.md line 384; SETUP.md line 503 | Likely |

---

## Gaps

### Critical Gaps (no documentation exists)

1. **Architecture Overview** — No document explains the full system architecture: how the FastAPI app, policy engine, proxy layer, MCP server, admin UI, and Google OAuth flow all fit together. The README ASCII diagram (lines 57-72) is the closest thing but lacks detail. An agent reading the codebase has no single document to understand the request flow from MCP tool call → policy engine → Google API proxy → response.

2. **REST API Reference** — No comprehensive endpoint listing for the REST API. Only 3 curl examples in the README. The admin REST API (`/admin/api/routes/{id}`) is shown in one curl example. Agents using the REST API (not MCP) have no reference.

3. **Module Development Guide** — CONTRIBUTING.md mentions adding modules under `gatekeeper/modules/` but provides no walkthrough. The `GoogleModule` base class, `RouteDef` definition, how to register a module, and how routes get discovered are all undocumented externally.

4. **Error Handling Guide for Agents** — MCP_SETUP_AGENT.md has a small error table (lines 230-238) but it's incomplete. Missing: what to do on 421 (DNS rebinding), 429 (rate limit), 503 (Google API temporarily unavailable), timeout behavior, and how to interpret structured error JSON responses from the proxy.

5. **Design Walkthrough** — No single document provides a "full walkthrough" of the Gatekeeper design. The closest is reading README → SETUP → MCP_SETUP_HUMAN → MCP_SETUP_AGENT sequentially, but these are task-oriented guides, not a cohesive design document. The task specifically calls out this gap.

### Moderate Gaps (partially covered but insufficient)

6. **Drive scopes documentation** — The Drive module requires Sheets/Documents/Presentations scopes (`spreadsheets`, `documents`, `presentations`) in addition to the `drive` scope, but these are not listed in the OAuth scopes tables in MCP_SETUP_HUMAN.md or SETUP.md. Only `https://www.googleapis.com/auth/drive` is listed.

7. **Route parameter reference** — The `input_schema` for each route is defined in code (e.g., drive/__init__.py has 1545 lines of RouteDef) but is not documented externally. MCP_SETUP_AGENT.md lists route names but not their parameters. An agent calling `drive__files_list` must discover parameters from the MCP tool schema at runtime (which works), but there is no static reference.

8. **Policy configuration deep dive** — The policy engine (`policy.py`) supports a rich set of transforms (max_results, allowed_labels, exclude_labels, blocked_fields, max_items, query_filter, max_recipients, max_file_size_mb, max_attachment_size_mb, require_body) but there is no documentation on how these are applied, what the priority order is, or how to combine them.

9. **Upgrade/migration guide** — CHANGELOG.md exists but has no migration instructions. No doc covers how to upgrade from one version to the next (database migrations, config changes, etc.).

10. **Testing guide for agents** — No documentation on how to test an agent's integration with Gatekeeper. What to verify, what common failure modes look like, how to debug MCP connection issues beyond "check transport: sse."

### Minor Gaps (nice to have)

11. **Admin API documentation** — The admin routes (`/admin/api/`) are used internally by the UI but not documented for external consumption. The PATCH example in SETUP.md is the only reference.

12. **`gatekeeper status` output format** — The CLI command is referenced but its output is never shown, making it hard for agents to parse programmatically.

13. **API key permissions format** — The `--permissions` flag accepts comma-separated module names but the valid values and format are not explicitly documented.

14. **Rate limiting behavior** — `GATEKEEPER_RATE_LIMIT_PER_MINUTE=120` is mentioned but the actual rate limiting implementation (per-key, sliding window, etc.) and error response format are not documented.

---

## Duplications / Maintenance Issues

1. **Route tables are triplicated** — The full route tables (Drive 27 routes, Gmail 37 routes, Calendar 26 routes) appear in README.md, SETUP.md, and MCP_SETUP_AGENT.md (with slight variations). Any route change requires updating three files.

2. **Quick Start is duplicated** — README.md has two "Quick Start" sections (lines 9-41 and lines 77-110) with overlapping Docker/pip/uv instructions.

3. **OAuth setup instructions are duplicated** — Google OAuth steps appear in README.md (lines 129-166), SETUP.md (lines 136-275), and MCP_SETUP_HUMAN.md (lines 44-58).

4. **Systemd service instructions are duplicated** — README.md (lines 182-190), SETUP.md (lines 293-327), and PODMAN_DEPLOYMENT.md (lines 295-377) all cover systemd setup.

---

## Recommendations

1. **Create an Architecture Overview document** (`docs/ARCHITECTURE.md`) — A single-page design walkthrough covering: FastAPI app structure, request flow (MCP → policy engine → proxy → Google API), module system, MCP server registration, admin UI, and data model. This directly addresses gap #5 (the "full walkthrough" called out in the task).

2. **Create a REST API Reference** (`docs/API_REFERENCE.md`) — Auto-generate or manually document all `/api/v1/*` endpoints with request/response formats, auth requirements, and error codes.

3. **Create a Module Development Guide** (`docs/MODULE_DEVELOPMENT.md`) — Step-by-step walkthrough of creating a new module: inheriting from `GoogleModule`, defining `RouteDef`s, registering in `AVAILABLE_MODULES`, testing, and adding documentation.

4. **Create an Error Handling Guide for Agents** (`docs/AGENT_ERRORS.md`) — Comprehensive error code reference, recovery strategies, and common troubleshooting patterns. Should include: 401, 403, 404, 421, 429, 502, 503, timeout handling, and structured error JSON format.

5. **Deduplicate route tables** — Create a single source of truth (perhaps `docs/ROUTES.md` auto-generated from code) and include it by reference in README, SETUP, and MCP docs. Alternatively, remove the full tables from README and link to the canonical source.

6. **Add missing Drive scopes** — Update the OAuth scopes tables in SETUP.md and MCP_SETUP_HUMAN.md to include `spreadsheets`, `documents`, and `presentations` scopes required by the Drive module.

7. **Deduplicate Quick Start** — Remove the first Quick Start section (lines 9-41) from README.md and keep the second, more detailed one. Or move the first to a one-liner and expand the second.

8. **Add route parameter reference** — Either document all route parameters in a static reference document, or add a section to MCP_SETUP_AGENT.md explaining that agents should use `list_tools` to discover parameters dynamically (which is already the correct behavior but should be explicitly stated).

---

## Confidence Assessment

- **Accurate and complete docs**: MCP_SETUP_AGENT.md, MCP_SETUP_HUMAN.md, SETUP.md (with the gaps noted above)
- **Accurate but duplicated docs**: README.md (contains everything but is too long at 568 lines and has duplications)
- **Accurate and unique**: PODMAN_DEPLOYMENT.md, SECURITY.md, CONTRIBUTING.md, CHANGELOG.md
- **Missing entirely**: Architecture overview, REST API reference, module development guide, agent error handling guide, upgrade guide