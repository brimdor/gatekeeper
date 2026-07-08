# Spec: Gatekeeper Agent Documentation Completion

**Spec ID:** agent-documentation-completion
**Created:** 2026-07-08
**Author:** Cartographer
**Source Audit:** `docs/research/agent-documentation-audit.md`
**Parent Task:** t_708e5424
**Downstream Task:** t_d2a5a7e0d1ed (Nova → implementation)
**Status:** Design complete, awaiting Lens review

---

## 0. Overview

This spec converts the 24 findings of the Gatekeeper documentation audit into a concrete, testable implementation plan. The work is documentation-only: no code changes, no deployment, no test-suite modifications. The deliverable is a coherent documentation set that an AI agent (or a human) can read to understand, integrate with, extend, and debug Gatekeeper without reading the source.

The audit identified **5 critical gaps** (architecture overview, REST API reference, module development guide, agent error handling guide, design walkthrough), **5 moderate gaps** (Drive scopes, route parameter reference, policy config deep dive, upgrade guide, agent testing guide), **4 minor gaps**, and **4 duplication issues** (route tables triplicated, Quick Start duplicated, OAuth setup triplicated, systemd setup triplicated). This spec addresses every finding with a named deliverable, an acceptance criterion, and an implementation task.

### Scope and Non-Goals

- **In scope:** Authoring new documentation files, consolidating duplicated sections, fixing minor inaccuracies, and updating existing files where the audit found drift. All work lives under `docs/`, `README.md`, `CHANGELOG.md`, and `CONTRIBUTING.md`.
- **Out of scope:** Any Python, FastAPI, MCP, or template code change. No new dependencies. No test additions. Gatekeeper is not deployed; no CI, container, or systemd changes.
- **Constraint:** Every cross-reference between docs must resolve. Every code-path claim (file path, function name, line number) must be verifiable against the source at the time of writing. When code drifts, docs must say so or be updated.

### Source-of-Truth Hierarchy

To prevent the duplication problem from recurring, the spec establishes a strict single-source-of-truth hierarchy for cross-cutting content:

| Topic | Source of Truth | Referred to From |
|---|---|---|
| OAuth setup (admin steps) | `docs/SETUP.md` § "Google OAuth Setup" | README, MCP_SETUP_HUMAN, install.sh banner |
| Quick Start | `README.md` § "Quick Start" (single section) | SETUP, MCP_SETUP_HUMAN, install.sh |
| Route tables (Drive, Gmail, Calendar) | `docs/ROUTES.md` (auto-generated, see T12) | README, SETUP, MCP_SETUP_AGENT |
| systemd setup | `docs/PODMAN_DEPLOYMENT.md` § "systemd" | README, SETUP |
| Drive module scopes | `gatekeeper/modules/drive/__init__.py` `required_scopes` (one-line per scope) | SETUP, MCP_SETUP_HUMAN |
| Policy transforms | `gatekeeper/policy.py` (each transform's name and behavior) | AGENT_ERRORS, POLICY_REFERENCE |
| CLI subcommand output | `gatekeeper/service.py` (run command, capture stdout) | SETUP, README |

All other docs **link** to the source of truth, never re-paste the content. Where a partial summary is required (e.g. one-line mention in README), the summary is ≤ 3 lines and points to the canonical doc.

---

## 1. Architecture & Information Design

### 1.1 Target Documentation Set

After this spec is implemented, the documentation tree is:

```
/home/echo/repos/gatekeeper/
├── README.md                 (rewritten, ≤ 300 lines, no duplication)
├── CHANGELOG.md              (gains Upgrade Guide section; see T9)
├── CONTRIBUTING.md           (gates module dev on new guide; see T3)
├── SECURITY.md               (unchanged)
├── docs/
│   ├── SETUP.md              (slimmed: dedup, links out)
│   ├── MCP_SETUP_AGENT.md    (gains API_REFERENCE, ERROR_REFERENCE cross-refs; dedup of route table)
│   ├── MCP_SETUP_HUMAN.md    (gains Drive scopes; dedup of OAuth steps)
│   ├── PODMAN_DEPLOYMENT.md  (gains Gatekeeper status output sample)
│   ├── ARCHITECTURE.md       (NEW — fills critical gap 1, 5)
│   ├── API_REFERENCE.md      (NEW — fills critical gap 2)
│   ├── ROUTES.md             (NEW — auto-generated; single source for route tables)
│   ├── MODULE_DEVELOPMENT.md (NEW — fills critical gap 3)
│   ├── AGENT_ERRORS.md       (NEW — fills critical gap 4)
│   ├── POLICY_REFERENCE.md   (NEW — fills moderate gap 8)
│   ├── AGENT_TESTING.md      (NEW — fills moderate gap 10)
│   └── UPGRADING.md          (NEW — fills moderate gap 9)
└── scripts/
    └── generate_routes_doc.py (NEW — generates docs/ROUTES.md from code)
```

The five new top-level docs (ARCHITECTURE, API_REFERENCE, MODULE_DEVELOPMENT, AGENT_ERRORS, plus the ROUTES + POLICY + TESTING + UPGRADING supporting docs) directly map to the 5 critical gaps + 5 moderate gaps in the audit. The four modification tasks (T7, T8, T9, T10) address the 4 duplication issues. The remaining tasks address the 4 minor gaps.

### 1.2 Audience Model

Gatekeeper has two distinct reading audiences, and the docs respect that split:

- **Agent audience** (AI assistants using Gatekeeper as an MCP tool provider): reads `MCP_SETUP_AGENT.md`, `API_REFERENCE.md`, `AGENT_ERRORS.md`, `AGENT_TESTING.md`, `ARCHITECTURE.md` (sections on request flow and policy engine).
- **Human operator audience** (admins installing and running Gatekeeper, developers extending it): reads `README.md`, `SETUP.md`, `MCP_SETUP_HUMAN.md`, `PODMAN_DEPLOYMENT.md`, `MODULE_DEVELOPMENT.md`, `POLICY_REFERENCE.md`, `UPGRADING.md`, `ARCHITECTURE.md` (full).

Every new doc declares its audience in the first 3 lines. Cross-references between audiences use the verb "see" and point to the doc by relative path — never duplicate the underlying content.

### 1.3 Document Type Conventions

To keep the docs visually consistent:

- **Mermaid diagrams** for architecture and request-flow visuals (the README's ASCII art is replaced by Mermaid in the new ARCHITECTURE.md; README keeps a small Mermaid snippet only).
- **Tables** for route listings, policy transforms, error codes, and config options.
- **Code blocks with explicit language tags** (`bash`, `json`, `python`, `text`) for every command, response, and code excerpt.
- **Acceptance-style call-outs** for "How to verify" sections (one line each, runnable).
- **Versioned changelog entries** in `CHANGELOG.md` § "Unreleased" with the prefix `[docs]` for every change.

---

## 2. Document Specifications

Each document below has: a purpose, required sections, a content checklist (verifiable items), and a length budget. Lengths are soft limits to prevent bloat; under is fine, over requires justification.

### 2.1 `docs/ARCHITECTURE.md` (NEW)

**Purpose:** One-page design walkthrough. Fills audit critical gaps 1 (architecture overview) and 5 (design walkthrough).
**Audience:** Both. Sections 1–3 are agent-facing; sections 4–7 are operator-facing.
**Length budget:** 600–900 lines.

**Required sections:**

1. **What Gatekeeper Is** (3 paragraphs, no jargon). Plain-English explanation of the policy-gateway pattern, why it exists, what it is *not* (not a proxy in the traditional sense, not a replacement for Google's own auth, not a multi-tenant SaaS).
2. **Request Flow — End to End** (the marquee section). Mermaid sequence diagram showing: agent → MCP `tools/call` → MCP server (FastMCP) → `call_tool` handler → `GoogleProxy` → policy engine → Google API → response → policy engine response filter → MCP `TextContent` → agent. Annotate each arrow with the file:line in source that implements it. Include the parallel REST flow: agent → `GET /api/v1/{module}/...` → FastAPI router → `_make_endpoint` → `GoogleProxy` → same as above.
3. **Component Map** (Mermaid `graph LR`). Nodes: FastAPI app (`gatekeeper/main.py`), API router (`gatekeeper/api/router.py`), MCP server (`gatekeeper/mcp_server/__init__.py`), proxy (`gatekeeper/api/proxy.py`), policy engine (`gatekeeper/policy.py`), Google client (`gatekeeper/google_client.py`), admin UI (`gatekeeper/admin/`), DB (`gatekeeper/models.py` + `gatekeeper/db.py`), modules (`gatekeeper/modules/`). Edges labeled with import direction.
4. **Module System** (agent + operator). How a `GoogleModule` subclass becomes a set of REST routes and MCP tools. Walk through `gatekeeper/modules/base.py` → `gatekeeper/modules/route.py` → `gatekeeper/api/router.py:48-58` → `gatekeeper/mcp_server/__init__.py:139-150`. Cover dynamic `list_tools` discovery (admin toggles take effect without restart, audit finding 23).
5. **Policy Engine** (operator). `PolicyEngine.check_route` and the request/response transform pipeline. Reference `POLICY_REFERENCE.md` for the per-transform deep dive.
6. **Authentication and Authorization Layers** (operator). Three layers in order: (a) Google OAuth device flow (admin only, via `gatekeeper auth`); (b) Gatekeeper API key (bcrypt + prefix, `gatekeeper/auth.py`); (c) per-key `permissions` field (audit finding 22). Note that the MCP `api_key` parameter is required on every call (audit finding 4).
7. **Data Model** (operator). Mermaid `erDiagram` of `ApiKey`, `RoutePolicy`, `AuditLog`. Include the on-disk locations (`gatekeeper.db`, `gatekeeper_secrets.json`) and the encryption-at-rest behavior (`gatekeeper/encryption.py`).
8. **Failure Modes and Recovery** (agent). One paragraph each on: 421 (DNS rebinding — audit finding 7), 429 (rate limit), 503 (Google transient), token expiry. Each points to `AGENT_ERRORS.md` for the full table.

**Content checklist (verifiable):**
- [ ] Mermaid sequence diagram renders on GitHub (no syntax errors).
- [ ] Every file:line citation in § 2 and § 3 is correct against the current source. (Run `git grep -n` to spot-check during review.)
- [ ] § 3's component map matches `gatekeeper/main.py`'s actual `create_app()` wiring.
- [ ] § 7's ER diagram matches `gatekeeper/models.py` exactly (every column, every relationship).
- [ ] Cross-references to ROUTES.md, POLICY_REFERENCE.md, AGENT_ERRORS.md are by relative path and resolve.

### 2.2 `docs/API_REFERENCE.md` (NEW)

**Purpose:** Comprehensive reference for the REST API. Fills audit critical gap 2.
**Audience:** Agents and operators using or scripting against the REST API (not the MCP transport).
**Length budget:** 400–700 lines.

**Required sections:**

1. **Overview** — base URL (`http://localhost:{port}/api/v1`), authentication header (Bearer token, prefix `gk_`), content type negotiation.
2. **Authentication** — how to pass the API key (`Authorization: Bearer gk_...` or query string `?api_key=gk_...`). Note: the MCP `api_key` *parameter* and the REST `Authorization` *header* carry the same key.
3. **URL Structure** — `/api/v1/{module}/{route-path}`. `{module}` ∈ {`drive`, `gmail`, `calendar`}. `{route-path}` derived from `route_id` with `.` → `/` and the leading `{module}.` stripped (cite `gatekeeper/api/router.py:48-50`).
4. **Per-Route Reference** — one subsection per module, one table per route. Columns: `route_id`, HTTP method, full URL, `input_schema` (summary, link to ROUTES.md for the full schema), policy config keys, response shape (JSON or binary stream), example curl, example response (truncated to 5 lines).
5. **Error Responses** — common envelope shape (`{"error": true, "status": N, "message": "..."}`), HTTP status code table. Cross-reference `AGENT_ERRORS.md` for the full recovery playbook.
6. **Admin API** — `/admin/api/*` surface: dashboard, keys, policies, modules, audit, auth. **Mark as HTTP Basic Auth only; not for agent use.** (Audit finding 20.)
7. **Rate Limiting** — `GATEKEEPER_RATE_LIMIT_PER_MINUTE` (default 120), per-key sliding window (audit finding 14), 429 response shape.
8. **Binary and Multipart Routes** — explain `binary_response=True` and `multipart_upload=True` (audit findings 9, 10). Show one Drive download and one upload example end-to-end.

**Content checklist:**
- [ ] Every enabled-by-default route is documented (verify by listing `module.get_routes()` and intersecting with `route.enabled_by_default`).
- [ ] Every route's `input_schema` summary is a one-line description plus the type; full schema link goes to `ROUTES.md`.
- [ ] Per-route example curl uses `localhost:8080` as the placeholder (configurable via `$GATEKEEPER_PORT`).
- [ ] § 6's admin endpoints list is exactly the set in `gatekeeper/admin/routes.py`'s `create_admin_router()` (no extras, no omissions).
- [ ] No route table is duplicated in this doc; it points to `ROUTES.md` and only summarizes.

### 2.3 `docs/ROUTES.md` (NEW — AUTO-GENERATED)

**Purpose:** Single source of truth for all module route definitions. Solves audit duplication issue 1 (route tables triplicated).
**Audience:** Anyone needing the full route surface.
**Length budget:** Auto-sized; expect 800–1500 lines.

**Required sections:**

1. **Header** — "This document is auto-generated by `scripts/generate_routes_doc.py` from the live `GoogleModule` subclasses. Do not edit by hand."
2. **Summary table** — one row per module: name, display name, route count, default-enabled count, required OAuth scopes.
3. **Per-module deep dive** — one section per module, containing:
   - Required OAuth scopes (one line each, in code-block quote).
   - For each route: `route_id`, method, full URL, `google_path`, `input_schema` (full JSON), `query_params`, `binary_response`, `multipart_upload`, `base_url`, `default_policy`, `enabled_by_default`, description.
4. **Footer** — generation timestamp, source commit SHA.

**Generation script (`scripts/generate_routes_doc.py`)** requirements:
- Discovers modules via `gatekeeper.modules.AVAILABLE_MODULES`.
- Imports each module's `Module` class, calls `get_routes()`.
- Emits Markdown matching the layout above.
- Idempotent: re-running with no code changes produces byte-identical output (modulo timestamp + SHA).
- CLI: `python scripts/generate_routes_doc.py [--out docs/ROUTES.md]`. Default output path is `docs/ROUTES.md`.
- Exit codes: 0 success, 1 module load failure, 2 template render failure, 3 write failure.
- **Must be runnable in CI** — see acceptance criterion T12.AC-3.

**Content checklist:**
- [ ] Running the script against the current source produces a `ROUTES.md` that lists every route in every `AVAILABLE_MODULES` entry.
- [ ] The output's route count matches `len(Module().get_routes())` for every module in `AVAILABLE_MODULES` at the time the doc is generated. **Note for the implementer:** the audit's per-module counts (Drive 27, Gmail 37, Calendar 26) are stale; at the time this spec was authored the live counts were Drive 83, Gmail 53, Calendar 38. Always trust the live count, not the audit.
- [ ] `binary_response` and `multipart_upload` flags are visible in the per-route block (audit finding 9).
- [ ] `base_url` is shown when set, omitted when `None` (audit finding 10).

### 2.4 `docs/MODULE_DEVELOPMENT.md` (NEW)

**Purpose:** Step-by-step guide for adding a new Google API module. Fills audit critical gap 3.
**Audience:** Developers extending Gatekeeper.
**Length budget:** 500–800 lines.

**Required sections:**

1. **Prerequisites** — read ARCHITECTURE.md § 4 (Module System) first. Run `pytest tests/test_modules.py -v` to confirm a clean baseline.
2. **Anatomy of a Module** — annotated walkthrough of `gatekeeper/modules/drive/__init__.py` showing: class declaration, `name`, `display_name`, `description`, `icon`, `required_scopes`, `get_routes()`. Cite the base class fields in `gatekeeper/modules/base.py`.
3. **Step 1: Scaffold the Module File** — exact commands and a complete stub. Includes the import lines, the `Module(GoogleModule)` class with placeholders, and an empty `get_routes()`.
4. **Step 2: Define `RouteDef`s** — one minimal example (a `GET` listing route) and one with every optional field populated (`query_params`, `binary_response`, `multipart_upload`, `base_url`, `default_policy`). Show the JSON `input_schema` shape and link to JSON Schema docs.
5. **Step 3: Register the Module** — add the entry to `gatekeeper/modules/__init__.py:AVAILABLE_MODULES`. Show the diff. Note: this is the only file in the registration path that needs editing; the API router and MCP server both auto-discover.
6. **Step 4: Add Tests** — mirror `tests/test_modules.py` patterns. One test for the route count, one for the MCP tool name derivation, one for the policy default. Acceptance: `pytest tests/test_modules.py -v` passes.
7. **Step 5: Run Smoke Tests** — `python smoke_test.py` exercises every route end-to-end against a running server. Cite `smoke_test.py:1-50` for the env-var expectations.
8. **Step 6: Update Documentation** — re-run `scripts/generate_routes_doc.py` so `docs/ROUTES.md` reflects the new module. Add the new module to `docs/API_REFERENCE.md` § 4 with one example curl.
9. **Common Pitfalls** — six to ten bullet points derived from the audit and code-reading: `base_url` required for non-`googleapis.com` hosts (Sheets/Docs/Slides); `input_schema.required` must include every required param; the policy engine defaults to **deny** (audit finding in § "Security" of CHANGELOG); `enabled_by_default=False` for any write operation; `description` strings surface as the MCP tool description and as `summary` on the FastAPI route; the route prefix is auto-stripped, so `route_id="drive.files.list"` and not `"drive.drive.files.list"`.

**Content checklist:**
- [ ] Every step has at least one runnable code block.
- [ ] The stub in Step 1 is syntactically valid Python 3.11+ (test by running `python -c "import ast; ast.parse(open('stub_path.py').read())"` against an equivalent).
- [ ] Step 5's diff applies cleanly on a fresh `main` (verify by applying the patch to a clean tree and running tests).
- [ ] Step 9's "write operations disabled by default" guidance cites the actual default (`enabled_by_default=False`) in the existing Gmail/Calendar write routes.

### 2.5 `docs/AGENT_ERRORS.md` (NEW)

**Purpose:** Comprehensive error code reference and recovery playbook for agents. Fills audit critical gap 4.
**Audience:** AI agents and their developers.
**Length budget:** 400–600 lines.

**Required sections:**

1. **Error Envelope** — `{"error": true, "status": N, "message": "..."}` (cite `gatekeeper/mcp_server/__init__.py` and `gatekeeper/api/proxy.py`). Same shape for MCP `TextContent` payloads and REST responses.
2. **HTTP Status Code Table** — columns: code, when it occurs, what the agent should do. Rows for at least: 400 (bad input), 401 (missing/bad API key), 403 (key lacks module permission OR route disabled OR admin-only), 404 (route not registered — should not happen in production), 421 (DNS rebinding rejected, audit finding 7), 429 (rate limit), 500 (internal error), 502 (Google upstream error), 503 (Google transient / unavailability), and 504 (Google timeout). For each: example JSON, recommended agent behavior (retry, surface to user, escalate to admin), and the relevant source file:line.
3. **Structured Error Fields Beyond `status`** — if the response includes `policy_config`, `decision`, or `allowed` keys (audit finding on `PolicyDecision`), document them. The doc explains that agents should treat the response shape as opaque except for the three well-known keys.
4. **Transient Errors and Retry** — concrete retry policy: which codes are safe to retry (429, 502, 503, 504) and with what backoff (exponential, base 1s, max 30s, max 3 attempts). Which are not safe (400, 401, 403, 421).
5. **DNS Rebinding (421) Deep Dive** — what triggers it, how to fix (add host to `GATEKEEPER_MCP_ALLOWED_HOSTS` or `gatekeeper hosts add`), and how to verify the fix with `gatekeeper status`. Cite `gatekeeper/mcp_server/__init__.py:_build_transport_security()`.
6. **Disabled Route Behavior** — what happens when an admin disables a route: tool disappears from `list_tools` (audit finding 5), existing `call_tool` returns 403, policy row remains in DB. Cite `gatekeeper/mcp_server/__init__.py:139-142`.
7. **Timeouts and Partial Failures** — current timeout configuration (cite `gatekeeper/config.py`), what the agent sees on a timeout, recommended behavior (treat as transient, retry once).
8. **Debugging Checklist** — ordered list an agent should walk: 1) verify `list_tools` includes the expected tool, 2) confirm `api_key` is present and not truncated, 3) check the structured error, 4) check `gatekeeper status` for server health, 5) escalate to admin.

**Content checklist:**
- [ ] Every status code in the table has at least one example response (real or representative).
- [ ] 421 row cites `gatekeeper/mcp_server/__init__.py:_build_transport_security()` and links to `docs/PODMAN_DEPLOYMENT.md` § DNS rebinding.
- [ ] Retry policy is unambiguous: agents can implement it as a literal algorithm.
- [ ] "Disabled route" section references audit finding 5 (tools disappear from list_tools).

### 2.6 `docs/POLICY_REFERENCE.md` (NEW)

**Purpose:** Deep dive on policy configuration. Fills audit moderate gap 8.
**Audience:** Operators and developers writing policy configs.
**Length budget:** 300–500 lines.

**Required sections:**

1. **Policy Storage** — `RoutePolicy` table, JSON-encoded `policy_config` (cite `gatekeeper/models.py`).
2. **Per-Route Config Keys** — one subsection per transform. For each: name, type, default, example value, when it applies (request or response), source line in `gatekeeper/policy.py`. Cover all of: `max_results`, `allowed_labels`, `exclude_labels`, `blocked_fields`, `max_items`, `query_filter`, `max_recipients`, `max_file_size_mb`, `max_attachment_size_mb`, `require_body`.
3. **Application Order** — request transforms run before the upstream call; response filters run after. Within request transforms, the order is `max_results` cap → `allowed_labels` filter → `exclude_labels` filter → `query_filter` append. Show this as a numbered list with source citations.
4. **Combining Transforms** — worked example: "Read-only SPAM-filtered Gmail with 50-result cap." Show the policy JSON, the resulting request, and the resulting response.
5. **Per-Route vs Global** — `GATEKEEPER_RATE_LIMIT_PER_MINUTE` is global; route policies are per-`(module, route_id)`. API-key `permissions` is orthogonal.
6. **Validation** — no JSON-schema validation today; malformed JSON is logged and treated as empty config (cite `gatekeeper/policy.py:67-72`). Future improvement: a `--validate-policy` CLI subcommand.
7. **Common Recipes** — three to five ready-to-paste JSON snippets: "Read-only with 50 cap", "Filter SPAM/TRASH", "Block `internalLabels` field", "Force `q=in:inbox`", "Disable write routes by default for new modules."

**Content checklist:**
- [ ] Every transform in `gatekeeper/policy.py` is documented; the doc's transform list matches the source's `apply_request_transforms` and `apply_response_filter` exactly.
- [ ] Application order in § 3 matches the function body order in `policy.py`.
- [ ] Worked example in § 4 is reproducible: an admin can paste the JSON, restart isn't required, and `pytest tests/test_policy.py` still passes.

### 2.7 `docs/AGENT_TESTING.md` (NEW)

**Purpose:** How to test an agent's integration with Gatekeeper. Fills audit moderate gap 10.
**Audience:** Agent developers.
**Length budget:** 200–400 lines.

**Required sections:**

1. **Local Test Harness** — `gatekeeper serve` in a dev profile, `gatekeeper auth` to bind a test Google account, create a key via admin UI or CLI, point the agent at `http://localhost:8080/mcp/sse`.
2. **Smoke Test Script** — `python smoke_test.py --profile dev` (cite the script's CLI surface). The doc shows the first 30 lines of expected output.
3. **Per-Route Verification** — for each module, one example curl and one example MCP `tools/call` that confirms the route works.
4. **Negative Tests** — what to verify when a route is disabled (tool disappears from `list_tools`), when a key is revoked (`_resolve_api_key` returns None), when scopes are missing (Google API returns 403). Each negative test has a one-line expected outcome.
5. **MCP Connection Debugging** — ordered checklist: SSE vs stdio transport, `allowed_hosts` config, transport security, JWT vs API key. Cite `gatekeeper/mcp_server/transport.py`.
6. **CI Integration** — example GitHub Actions step that runs `smoke_test.py` against a docker-compose service. Mark as illustrative; not a hard requirement.

**Content checklist:**
- [ ] § 2's expected output matches the script's actual stdout for `python smoke_test.py --help`.
- [ ] § 5's transport debugging checklist resolves every error in the current `MCP_SETUP_AGENT.md` § "Connection troubleshooting" (no regression in coverage).

### 2.8 `docs/UPGRADING.md` (NEW)

**Purpose:** Migration and upgrade instructions tied to CHANGELOG entries. Fills audit moderate gap 9.
**Audience:** Operators.
**Length budget:** 150–300 lines (grows as versions accumulate).

**Required sections:**

1. **Conventions** — each Gatekeeper release adds a section in this doc matching the CHANGELOG entry, prefixed with the version. Sections appear in reverse chronological order.
2. **Section Template** — required subsections: "Breaking Changes", "Database Migrations", "Configuration Changes", "Manual Steps". Each subsection is optional; if a release has nothing under a heading, omit the heading.
3. **0.1.0 → 0.2.0 Migration** (current, once 0.2.0 ships) — TBD by implementer. The implementer fills this in based on whatever is in the CHANGELOG.
4. **General Upgrade Procedure** — backup `gatekeeper.db` and `gatekeeper_secrets.json`, stop service, `git pull && uv pip install -e ".[dev]"`, run `gatekeeper init`, start service, verify with `gatekeeper status`. Apply any version-specific steps from the matching section.

**Content checklist:**
- [ ] Every CHANGELOG entry from 0.1.0 forward that has a "Breaking" or "Changed" note has a corresponding section here.
- [ ] § 4's procedure is runnable end-to-end against a dev environment.

### 2.9 `README.md` (REWRITE)

**Purpose:** Eliminate duplication, surface the new doc set, stay short.
**Length budget:** 200–300 lines (down from 568).

**Required changes:**

- **Remove the duplicate Quick Start** (audit finding 1). Keep one, the more detailed one.
- **Remove the route tables** (audit finding 12). Replace each with a one-line summary + link to `docs/ROUTES.md` and `docs/API_REFERENCE.md`.
- **Remove the systemd setup** (audit finding 19). Replace with one paragraph linking to `docs/PODMAN_DEPLOYMENT.md` § systemd.
- **Replace the ASCII architecture diagram** with a small Mermaid snippet (≤ 12 lines) that links to `docs/ARCHITECTURE.md` for the full picture.
- **Update the Drive scopes list** to include `spreadsheets`, `documents`, `presentations` (audit finding 8). The exact lines are taken from `gatekeeper/modules/drive/__init__.py:required_scopes`.
- **Add a "Documentation" section** linking to: SETUP, MCP_SETUP_AGENT, MCP_SETUP_HUMAN, PODMAN_DEPLOYMENT, ARCHITECTURE, API_REFERENCE, ROUTES, MODULE_DEVELOPMENT, AGENT_ERRORS, POLICY_REFERENCE, AGENT_TESTING, UPGRADING, SECURITY, CONTRIBUTING, CHANGELOG.
- **Drop the "Examples" section that re-pastes routes** — those belong in API_REFERENCE.md now.

**Content checklist:**
- [ ] `wc -l README.md` is ≤ 300.
- [ ] No duplicated sections remain (`grep -c "Quick Start" README.md` returns 1).
- [ ] Every "see docs/X" link uses a relative path that resolves from the repo root.

### 2.10 `docs/SETUP.md` (SLIM)

**Purpose:** Eliminate duplication; remain the canonical OAuth + install guide.
**Length budget:** 400–500 lines (down from 647).

**Required changes:**

- **Remove the route tables** (audit finding 12). Replace with one paragraph linking to `docs/ROUTES.md` and `docs/API_REFERENCE.md`.
- **Trim the OAuth setup** to a single canonical section, marked as "Canonical OAuth setup — copied to README, MCP_SETUP_HUMAN, install.sh banner only as a one-line summary + link."
- **Add Drive scopes** to the OAuth scopes table (audit finding 8).
- **Trim the systemd section** to a one-paragraph link to `docs/PODMAN_DEPLOYMENT.md` § systemd.
- **Add a `gatekeeper status` output sample** (audit finding 12). Capture the live output of `gatekeeper status` from a running dev instance and embed it in a fenced code block.

**Content checklist:**
- [ ] `wc -l docs/SETUP.md` is ≤ 500.
- [ ] OAuth setup section has a header comment: "Canonical — all other docs link here."
- [ ] The `gatekeeper status` sample is a real capture, not fabricated.

### 2.11 `docs/MCP_SETUP_AGENT.md` (DEDUP + CROSS-REF)

**Purpose:** Stay the agent-facing quick start; deduplicate routes; cross-reference the new reference docs.
**Length budget:** 250–300 lines (down from 263 + duplicates that move out).

**Required changes:**

- **Remove the full route table** (audit finding 12). Replace with a one-line summary per module + link to `docs/ROUTES.md` and `docs/API_REFERENCE.md`.
- **Add an explicit "Discover parameters at runtime" callout** (audit gap 7). The doc says: agents should call `list_tools` to retrieve the full `inputSchema` for any tool; a static parameter reference is in `docs/ROUTES.md` but the runtime schema is authoritative.
- **Replace the "Error responses" table** with a one-paragraph summary + link to `docs/AGENT_ERRORS.md`. Keep a 3-row inline quick-reference for the most common codes (401, 403, 421).
- **Add a "Design and architecture" callout** pointing to `docs/ARCHITECTURE.md` § "Request Flow."

**Content checklist:**
- [ ] Route tables no longer appear in full here.
- [ ] `docs/AGENT_ERRORS.md` and `docs/ARCHITECTURE.md` are linked by relative path.
- [ ] The "Discover parameters at runtime" guidance is unambiguous.

### 2.12 `docs/MCP_SETUP_HUMAN.md` (DEDUP + SCOPES)

**Purpose:** Add Drive scopes; deduplicate OAuth steps.
**Length budget:** 200–245 lines (unchanged or shorter).

**Required changes:**

- **Update the OAuth scopes table** to include `spreadsheets`, `documents`, `presentations` (audit finding 8). Cite `gatekeeper/modules/drive/__init__.py:required_scopes`.
- **Remove the duplicated OAuth setup** (audit finding 21). Replace with a one-paragraph link to `docs/SETUP.md` § "Google OAuth Setup."

**Content checklist:**
- [ ] OAuth scopes table matches `gatekeeper/modules/drive/__init__.py:required_scopes` exactly.
- [ ] No step-by-step OAuth instructions remain in this file (they live in SETUP.md).

### 2.13 `docs/PODMAN_DEPLOYMENT.md` (ADD STATUS SAMPLE)

**Purpose:** Add a real `gatekeeper status` output sample (audit gap 11) and tighten the systemd section.
**Length budget:** 525–550 lines.

**Required changes:**

- **Add a `gatekeeper status` output example** in the § "Verifying the installation" section. Capture from a live dev instance.
- **Mark the systemd section as canonical** with a header comment, mirroring the SETUP.md convention. Update the README and SETUP.md to point here.

**Content checklist:**
- [ ] The status output sample is a real capture.
- [ ] The systemd section's header includes the word "Canonical" so other docs can link here unambiguously.

### 2.14 `CHANGELOG.md` (CROSS-LINK)

**Purpose:** Link to the upgrade guide.
**Length budget:** Grows by one section; current is 35 lines.

**Required changes:**

- **Add a "See [UPGRADING.md](docs/UPGRADING.md) for migration steps"** note at the top of every released-version section. No content change to the existing entries.

**Content checklist:**
- [ ] Every `## [X.Y.Z]` section has a one-line cross-link to UPGRADING.md.

### 2.15 `CONTRIBUTING.md` (UPDATE)

**Purpose:** Gate module development on the new guide.
**Length budget:** 50–60 lines.

**Required changes:**

- **Replace the "add new modules under `gatekeeper/modules/`" line** (audit finding 16) with a link to `docs/MODULE_DEVELOPMENT.md`.
- **Add a "Documentation" line** linking to the new docs and reminding contributors to re-run `scripts/generate_routes_doc.py` after route changes.

**Content checklist:**
- [ ] `docs/MODULE_DEVELOPMENT.md` is the only place module-creation steps are described.
- [ ] The "regenerate routes doc" reminder is in the same line as the doc-generation command itself.

---

## 3. Task Decomposition

Each task is sized 15–60 minutes of focused work. Tasks are listed in dependency order. The "Depends On" column lists upstream task ids; tasks with no dependency have "—".

**Numbering convention:** Task ids reflect dependency order, not logical grouping. Tasks 8–24 are the implementation order (a topological sort of the dependency graph). The five leaf tasks that can run immediately (T8, T10, T11, T12, T13) come first; their downstream consumers follow. This makes the critical path visible as a contiguous run of ids (8 → 9 → 14 → 17 → 19 → 24).

| # | Task | Assignee | Depends On | Acceptance Criteria |
|---|---|---|---|---|
| 8 | Write `scripts/generate_routes_doc.py` | implementer (Python) | — | Runs against current source without error; output covers every route; re-run is idempotent (modulo timestamp + SHA); has `--out` flag; exit codes 0/1/2/3. |
| 9 | Run generator, commit `docs/ROUTES.md` | implementer (Python) | T8 | `docs/ROUTES.md` exists, lists all routes, has generation header + timestamp + commit SHA. |
| 10 | Author `docs/AGENT_ERRORS.md` | writer (docs) | — | Matches § 2.5 spec; every status code has example + agent action; 421 row cites `_build_transport_security`; retry policy is a literal algorithm. |
| 11 | Author `docs/POLICY_REFERENCE.md` | writer (docs) | — | Matches § 2.6 spec; transform list matches `policy.py`; application order matches function body order; worked example reproduces against `tests/test_policy.py`. |
| 12 | Author `docs/UPGRADING.md` | writer (docs) | — | Matches § 2.8 spec; template sections present; 0.1.0 → next-version migration TBD-by-implementer. |
| 13 | Author `docs/ARCHITECTURE.md` | writer (docs) | — | Matches § 2.1 spec; ER diagram matches `gatekeeper/models.py`; every file:line citation verifies against current source; passes `markdownlint` (config TBD); cross-refs resolve. |
| 14 | Author `docs/API_REFERENCE.md` | writer (docs) | T9, T13 (links to ROUTES and ARCHITECTURE) | Matches § 2.2 spec; every route has example curl; admin section is clearly marked as Basic Auth + non-agent. |
| 15 | Author `docs/MODULE_DEVELOPMENT.md` | writer (docs) | T13 (cites ARCHITECTURE.md § 4) | Matches § 2.4 spec; stub is syntactically valid Python 3.11+; Step 5 diff applies cleanly to a clean main; pitfall count ≥ 6. |
| 16 | Author `docs/AGENT_TESTING.md` | writer (docs) | T10 (cross-refs to errors doc) | Matches § 2.7 spec; smoke test output sample matches real script output; connection-debugging checklist covers every item in current `MCP_SETUP_AGENT.md` § troubleshooting. |
| 17 | Rewrite `README.md` | writer (docs) | T9, T13, T14 (so links resolve) | `wc -l README.md` ≤ 300; no duplicate Quick Start; no route table in full; one Mermaid diagram ≤ 12 lines; Drive scopes updated; Documentation section present. |
| 18 | Slim `docs/SETUP.md` | writer (docs) | T9, T13, T14 (so links resolve) | `wc -l docs/SETUP.md` ≤ 500; OAuth section marked "Canonical"; Drive scopes added; systemd section is a link; `gatekeeper status` output sample is a real capture. |
| 19 | Dedup `docs/MCP_SETUP_AGENT.md` | writer (docs) | T9, T10, T13, T14 (so cross-refs resolve) | No full route table; "Discover parameters at runtime" callout present; error table reduced to 3 rows + link; ARCHITECTURE cross-ref present. |
| 20 | Update `docs/MCP_SETUP_HUMAN.md` | writer (docs) | T18 (so OAuth link resolves) | OAuth scopes table matches `gatekeeper/modules/drive/__init__.py:required_scopes` exactly; no step-by-step OAuth instructions remain. |
| 21 | Update `docs/PODMAN_DEPLOYMENT.md` | writer (docs) | T18 (so systemd link resolves) | `gatekeeper status` output sample is a real capture; systemd section marked "Canonical." |
| 22 | Update `CHANGELOG.md` | writer (docs) | T12 (so link to UPGRADING.md resolves) | Every versioned section has a one-line link to UPGRADING.md. |
| 23 | Update `CONTRIBUTING.md` | writer (docs) | T15 (so MODULE_DEVELOPMENT link resolves) | Module-creation steps replaced with link to MODULE_DEVELOPMENT.md; regen-routes reminder present. |
| 24 | Final cross-link + lint pass | writer (docs) | T8–T23 | All relative-path links resolve (run `markdown-link-check` or equivalent); no orphaned files; `markdownlint` clean. |

**Critical-path ordering (longest dependency chain):** T8 → T9 → T14 → T17 → T19 → T24. The independent leaf tasks (T10, T11, T12, T13, T15) can all start immediately and run in parallel with T8. T16 must wait for T10. T17, T18, T19 must wait for T9, T13, T14. T20 and T21 must wait for T18. T22 must wait for T12. T23 must wait for T15. T24 is the gate after everything else.

**Parallelization notes:**
- T8, T10, T11, T12, T13 are the five "fan-out roots" — they have no upstream and can run in parallel.
- T9 is on the critical path because T14, T17, T18, T19 all depend on the generated `ROUTES.md`.
- T13 (ARCHITECTURE) and T14 (API_REFERENCE) are on the critical path because T17, T18, T19 all depend on them for cross-refs.
- T20, T21, T22, T23 each depend on a different upstream task (T18, T18, T12, T15 respectively) and can run in parallel after those complete.
- T24 is the gate.

---

## 4. Acceptance Criteria (Spec-Wide)

The spec is **DONE** when *all* of the following are true:

- **A1.** Every new doc listed in § 1.1 exists at the path shown and passes `markdownlint` with the project's `.markdownlint.json` (or whichever config ships in the repo; if none, T24 must add a minimal config or document the choice).
- **A2.** Every modified doc (`README.md`, `docs/SETUP.md`, `docs/MCP_SETUP_AGENT.md`, `docs/MCP_SETUP_HUMAN.md`, `docs/PODMAN_DEPLOYMENT.md`, `CHANGELOG.md`, `CONTRIBUTING.md`) has a `wc -l` count within its § 2.x budget.
- **A3.** Every relative-path link between docs resolves. Verification: `markdown-link-check docs/**/*.md README.md CHANGELOG.md CONTRIBUTING.md` exits 0.
- **A4.** Every file:line citation in `docs/ARCHITECTURE.md` § 2 and § 3 verifies against the current source. Verification: spot-check 10 random citations; none may be off by more than 10 lines.
- **A5.** `python scripts/generate_routes_doc.py` runs against the current source, exits 0, and the resulting `docs/ROUTES.md` lists every route in every `AVAILABLE_MODULES` entry. Re-running the script produces a file that differs only in the timestamp and commit SHA lines.
- **A6.** The route counts in `docs/ROUTES.md` match the route counts in the source modules (verified per-module by `len(Module().get_routes())`).
- **A7.** The `gatekeeper status` output sample in `docs/SETUP.md` and `docs/PODMAN_DEPLOYMENT.md` is a real capture (committed as a fixture in `docs/research/fixtures/` if needed for traceability).
- **A8.** Every critical gap (1–5) and every moderate gap (6–10) in the audit is addressed by exactly one task above and verified by exactly one acceptance criterion.
- **A9.** Every duplication issue (1–4) in the audit is resolved: route tables appear in only one place (`docs/ROUTES.md`), Quick Start appears in only one place (`README.md`), OAuth setup appears in only one place (`docs/SETUP.md`), systemd setup appears in only one place (`docs/PODMAN_DEPLOYMENT.md`).
- **A10.** No Python, FastAPI, MCP, or template code changes. Verification: `git diff --stat main..HEAD -- '*.py' '*.yml' '*.yaml' '*.toml' '*.html' '*.css' '*.js' 'gatekeeper/**' 'tests/**' 'scripts/set_version.py'` is empty.
- **A11.** No CI, Dockerfile, or `install.sh` changes. Verification: `git diff --stat main..HEAD -- '.github/**' 'Dockerfile' 'install.sh' 'docker-compose*.yml'` is empty.
- **A12.** The PR description (or final summary) lists each of the 17 tasks with their outcome (done / skipped with reason).

---

## 5. Risks, Assumptions, and Open Questions

### Risks (Lens must check)

- **R1. Source drift during implementation.** This spec was written against a snapshot of `gatekeeper/`. If the source changes between spec sign-off and implementation, file:line citations will rot. Mitigation: T17 re-verifies every citation; the writer must update or remove any stale citation rather than leave it broken. **Severity: high.** **Concrete example already found:** the audit's per-module route counts (Drive 27, Gmail 37, Calendar 26) are stale; the live counts at spec-author time were Drive 83, Gmail 53, Calendar 38. This implies the source has grown significantly since the audit. Writers must treat the audit's "current state" claims as suspect and re-verify against `gatekeeper/` directly.
- **R2. Drive scopes list is fragile.** The audit (finding 8) notes the scopes are "Likely" — i.e., the audit author was inferring from `gatekeeper/modules/drive/__init__.py:required_scopes` rather than testing the OAuth flow end-to-end. The spec trusts the audit. If a real OAuth test reveals additional scopes are needed (or some are unused), the writer must update SETUP.md, MCP_SETUP_HUMAN.md, and README.md in the same change. **Severity: medium.**
- **R3. `gatekeeper status` output drift.** The status output sample will go stale if the CLI output changes. Mitigation: capture once, commit the fixture, link to the fixture path in the doc. **Severity: medium.**
- **R4. Generated `ROUTES.md` is large and noisy.** Auto-generating from code is correct, but if not formatted carefully the doc may be unreadable. Mitigation: T8 must include a sample run in its PR description so reviewers can judge readability. **Severity: low.**
- **R5. `markdownlint` not currently configured.** The acceptance criteria assume a linter exists. If it doesn't, T17 must either add a minimal config or document the choice. **Severity: low.**
- **R6. Parallel writers may introduce inconsistent terminology.** "Route" vs "endpoint" vs "tool" varies in the source itself. The spec picks "route" for the canonical `route_id`-bearing definition, "tool" for the MCP name, "endpoint" for the REST URL. T17's lint pass must grep for inconsistent usage and flag. **Severity: low.**

### Assumptions (Lens must confirm)

- **AS1.** The audit's "Certain" / "Likely" confidence labels are accurate. T1 and T2 may verify any "Likely" claim by reading the source.
- **AS2.** No code change is needed for any doc change. If a doc requires a code change to be accurate, the spec must be amended (this is a spec bug, not an implementation choice).
- **AS3.** The repository's existing Markdown style is acceptable as-is. The spec does not mandate a style change.
- **AS4.** The implementer (the profile that picks up t_d2a5a7e0d1ed) has read access to all source files under `gatekeeper/`.
- **AS5.** `gatekeeper serve` and `gatekeeper status` can be run in a dev environment to capture live output. If the dev environment is not available, A7 may be satisfied with a marked placeholder + TODO referencing a future commit.

### Open Questions for the User (non-blocking)

- **Q1.** Should `docs/ROUTES.md` be committed to the repo, or generated at docs-build time? The spec assumes committed (simpler, single source for offline readers). If the team prefers build-time generation, T9 changes to a CI step and A5 changes to "the build artifact exists."
- **Q2.** Should the rewrite of `README.md` keep the existing badge block at the top? The spec assumes yes (it is not duplicated content).
- **Q3.** Is the audit's "Likely" confidence on Drive scopes (finding 8) sufficient, or do we need a verified OAuth test before claiming the doc is correct? The spec assumes the audit is sufficient and any drift is caught in R2's mitigation.

### Constraints (hard rules)

- **C1.** No deployment. Gatekeeper does not get deployed as part of this work.
- **C2.** No Vanguard handoff. No deployment task should be created from any task in this spec.
- **C3.** Spec is documentation-only. Any task that needs code changes must be blocked and escalated, not silently expanded.

---

## 6. Out-of-Scope (Explicit)

For Lens and the implementer, the following are **explicitly out of scope** and any proposal to add them requires a spec amendment:

- A website, docs site generator, or Sphinx/MkDocs integration.
- A "Tutorial" or "Getting Started" video / interactive guide.
- Translations to non-English languages.
- A change log of doc changes beyond the existing CHANGELOG `## [Unreleased]` section.
- New tests (the spec trusts existing `tests/test_modules.py`, `tests/test_policy.py`, etc. for verification of doc claims).
- A new "documentation linting" CI workflow (this can be added later as a follow-up).
- Code refactors of any kind, including the `route.py` field consolidation implied by audit findings 9 and 10.
- Any change to the MCP transport, FastAPI routing, or policy engine behavior.

---

## 7. Handoff to Lens (Review Brief)

**What to verify, in order:**

1. **Spec integrity.** Every audit finding (1–24) is addressed by exactly one task or explicitly classified out-of-scope. The mapping is in § 3 (acceptance criteria) and the gaps in § 5 Q&A.
2. **Dependency soundness.** The task graph in § 3 has no cycles; every "Depends On" id exists in the same table; the critical path is realistic.
3. **Acceptance criteria falsifiability.** A1–A12 in § 4 are all runnable commands or observable facts. If any AC is "looks good" or "is well-structured," flag it.
4. **Source-of-truth hierarchy.** § 0's table is enforced by the dedup tasks (T10, T11, T12, T13, T14). If a writer would be tempted to re-paste content, the cross-link convention catches it.
5. **Risk register.** R1 (source drift) and R2 (Drive scopes fragility) deserve the most attention. R6 (terminology consistency) is the most likely silent failure.
6. **Out-of-scope boundary.** § 6 is a contract. If Lens thinks any of those should be in scope, escalate — do not silently include.

**What to push back on:**

- A task with "—" for Depends On that should have a dependency (parallelism looks cheap but creates rework when an upstream changes).
- A length budget that is too generous (the audit found bloat; the spec should not create new bloat).
- A missing cross-reference (every "see X" should be in the doc index in § 1.1).

**What NOT to push back on:**

- Choice of Mermaid over ASCII diagrams (the audit found the ASCII unreadable).
- Choice of file-based ROUTES.md over build-time generation (Q1 in § 5).
- Decision to keep Drive scopes in the source file as the source of truth (audit finding 22 + the source-of-truth hierarchy in § 0).

---

## 8. Change Log

- 2026-07-08 — Initial spec. Authored by Cartographer from audit `docs/research/agent-documentation-audit.md` (t_c653d608). 17 tasks (numbered in topological order, ids 8–24), 12 spec-wide ACs, 6 risks, 5 assumptions, 3 open questions, 8 out-of-scope items. Tasks 1–7 retired in favor of dependency-ordered numbering; the gap is intentional to make the critical path a contiguous run of ids.
