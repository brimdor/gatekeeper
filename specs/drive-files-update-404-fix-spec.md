# Blueprint: Fix 404 on `PATCH /api/v1/drive/files/update`

## Overview

The `drive.files.update` route has two independent defects that, combined with its `enabled_by_default=False` flag, make a successful PATCH effectively impossible for any REST caller who needs to move a file between folders (`addParents`/`removeParents`). The headline symptom reported by the user — a 404 in the audit log — is almost certainly a FastAPI-native 404 produced by a request that did not match the registered route shape, but the spec treats the underlying PATCH/POST/PUT param-merge bug and the misnamed test as the load-bearing fixes. We will:

1. Fix the PATCH handler so query params are preserved (and merge with the JSON body) — matching the behavior Google requires for `addParents`/`removeParents`.
2. Apply the same merge to POST and PUT for consistency.
3. Make `drive.files.update` enabled by default (it is a basic CRUD verb that an admin who flipped on the Drive module almost certainly wants).
4. Rename the misnamed test and tighten its assertion to cover the status code.
5. Enrich the audit log so 404 vs 403 is unambiguous in the future.

## Architecture

### Components

- **REST router** (`gatekeeper/api/router.py`) — generates per-method endpoints for every module route. The PATCH/POST/PUT branches each parse params from a single source.
- **Google proxy** (`gatekeeper/api/proxy.py`) — applies policy, normalizes param keys, splits `query_params` (e.g. `addParents`) from `body_params`, and forwards to Google.
- **Policy engine** (`gatekeeper/policy.py`) — returns 403 (never 404) for unknown or disabled routes. Returns `No policy defined` when no `RoutePolicy` row exists.
- **Route registry** (`gatekeeper/modules/drive/__init__.py`) — declares `drive.files.update` with `enabled_by_default=False` and `query_params=["addParents", "removeParents"]`.
- **Seeding** (`gatekeeper/main.py`) — `seed_default_policies()` honors `enabled_by_default` per route.
- **Audit log** (`gatekeeper/logging.py` → `log_request`) — currently logs `status_code` only; the response body is dropped after the first 200 chars for successes and dropped entirely for denials.
- **Tests** (`tests/test_api.py`) — `test_no_policy_returns_404` is misnamed and asserts 403 behavior.

### Data Flow (post-fix)

1. REST caller hits `PATCH /api/v1/drive/files/update?addParents=folderA&removeParents=folderB` with a JSON body containing `{file_id, name}`.
2. Router PATCH endpoint merges `dict(request.query_params)` with the parsed JSON body (query params as base, JSON body overriding on key collision) — the result includes `file_id`, `name`, `add_parents`, `remove_parents`.
3. Proxy normalizes keys to camelCase: `add_parents` → `addParents`, `remove_parents` → `removeParents`.
4. Proxy splits on `route.query_params = ["addParents", "removeParents"]`: those go to `query_params`, the rest to `body_params`.
5. Proxy calls Google `PATCH /drive/v3/files/{fileId}?addParents=folderA&removeParents=folderB` with `{name}` in the JSON body.
6. Google returns 200; proxy forwards status + filtered body to the caller and logs to the audit table.

### Tech Stack

- Python 3.x, FastAPI, SQLAlchemy (async), httpx (Google client). No new dependencies.

## Interface Definitions

### PATCH/POST/PUT param collection (post-fix contract)

```python
async def _collect_params(request: Request) -> dict:
    """Merge URL query params with the JSON body.

    Precedence: JSON body keys win on collision (so callers can override a
    query string with an explicit body field). Query params survive when the
    body is missing, unparsable, or doesn't include them.
    """
    query = dict(request.query_params)
    try:
        body = await request.json()
    except Exception:
        return query
    if not isinstance(body, dict):
        return query
    return {**query, **body}
```

Behavior matrix:

| Request shape | Pre-fix PATCH | Post-fix PATCH |
|---|---|---|
| `?addParents=A` only (no body) | `{}` — BUG | `{add_parents: "A"}` |
| JSON `{file_id, name}` only | `{file_id, name}` | `{file_id, name}` |
| Both query and JSON | query dropped — BUG | merged (body wins on key overlap) |
| No body, no query | `{}` | `{}` |

### `RouteDef.enabled_by_default` change

- `gatekeeper/modules/drive/__init__.py` — `drive.files.update` flips to `enabled_by_default=True`. Existing deployments with a seeded `RoutePolicy` row at `enabled=False` will need an explicit admin enable OR a one-line migration; the spec calls this out as a deployment note.

### Audit log enrichment

`gatekeeper/logging.log_request(...)` gains an optional `response_message: str | None = None` argument. The proxy passes `decision.reason` for denials and a truncated body for 4xx/5xx forwards. Persisted column: new nullable `response_message TEXT` on the audit log table (or fall back to stuffing it into `response_summary` if a migration is undesirable — see Task 5).

## Task Breakdown

| # | Task | Assignee | Depends On | Acceptance Criteria |
|---|------|----------|------------|---------------------|
| 1 | Fix PATCH/POST/PUT param merge in router | implementer | — | See Task 1 spec |
| 2 | Enable `drive.files.update` by default | implementer | — | See Task 2 spec |
| 3 | Rename and tighten `test_no_policy_returns_404` | implementer | — | See Task 3 spec |
| 4 | Add regression tests for PATCH/POST/PUT merge behavior | implementer | #1 | See Task 4 spec |
| 5 | Enrich audit log with response message | implementer | — | See Task 5 spec |
| 6 | Add end-to-end PATCH-move test against a fake Google server | implementer | #1, #2 | See Task 6 spec |

Tasks 1–3 are the headline fixes and ship together. Tasks 4–6 harden the surface. Tasks 1, 2, 3, 5 can be implemented in parallel; 4 depends on 1; 6 depends on 1 + 2.

## Task Specifications

## Task 1: Fix PATCH/POST/PUT param merge in router

### Objective

Stop silently dropping URL query parameters in PATCH, POST, and PUT handlers. The PATCH handler must fall back to `dict(request.query_params)` (matching POST/PUT) and, when a JSON body is present, merge the two with the body taking precedence on key collision.

### Files to Create/Modify

- `gatekeeper/api/router.py` — replace the three near-identical try/except blocks for PATCH (lines 146-168), POST (lines 98-120), PUT (lines 122-144) with a shared helper `_collect_params(request)` (defined at module top). PATCH currently has the worst bug (`params = {}` fallback); POST and PUT have the same silent-drop when both query and body are sent. DELETE and GET already read only query params and are unchanged.
- `tests/test_api.py` — see Task 4.

### Acceptance Criteria

- [ ] `_collect_params(request)` exists at module top, is an `async def`, and is reused by POST, PUT, PATCH.
- [ ] PATCH fallback is no longer `params = {}`; it returns `dict(request.query_params)` when the body is unparsable.
- [ ] When the body parses to a `dict`, the returned dict contains every query param and every body key; overlapping keys use the body value.
- [ ] When the body parses to a non-dict (e.g. a JSON list), the function returns the query params unchanged.
- [ ] DELETE and GET branches are not modified.
- [ ] `python -m py_compile gatekeeper/api/router.py` succeeds.
- [ ] No new imports are introduced (the helper uses only `Request`).

### Deliverable Location

`gatekeeper/api/router.py`

### Expected Effort

Small (15–30 min). Single-file refactor with a clear pattern to copy.

## Task 2: Enable `drive.files.update` by default

### Objective

Stop requiring explicit admin action to enable a basic CRUD verb. Once a deployment has flipped on `settings.DRIVE_ENABLED`, an admin almost always wants to update files.

### Files to Create/Modify

- `gatekeeper/modules/drive/__init__.py` — `drive.files.update` RouteDef at line 304: `enabled_by_default=False` → `enabled_by_default=True`.
- `docs/` — add a one-paragraph release note explaining the flip and the migration path for existing deployments (see Deployment Notes below).

### Acceptance Criteria

- [ ] `enabled_by_default=True` on the `drive.files.update` RouteDef.
- [ ] No other RouteDef is changed.
- [ ] The other `enabled_by_default=False` routes in the Drive module (`files.delete`, `files.trash`, `files.create` for multipart) remain opt-in — these are higher-risk and the spec does not change their default.
- [ ] A release note or migration doc exists at `docs/drive-files-update-default-on.md` (or appended to `CHANGELOG.md`) that says: "Existing deployments seeded before this change will have a `RoutePolicy` row at `enabled=False`. Run `gatekeeper policy enable drive.files.update` or delete the row so `seed_default_policies()` recreates it at `enabled=True`."

### Deliverable Location

`gatekeeper/modules/drive/__init__.py` + migration doc.

### Expected Effort

Trivial (5 min code + 10 min doc).

## Task 3: Rename and tighten the misnamed test

### Objective

`tests/test_api.py::TestApiProxy::test_no_policy_returns_404` is misnamed: the docstring says 403, the assertion only checks `body["error"] is True`, and the function name lies about the status code.

### Files to Create/Modify

- `tests/test_api.py` — rename `test_no_policy_returns_404` to `test_no_policy_returns_403`. Add `assert result.status_code == 403` and `assert body["status"] == 403` to the existing assertions.
- No other test files touched.

### Acceptance Criteria

- [ ] Method is renamed to `test_no_policy_returns_403` (snake_case, no hyphenated numerals).
- [ ] The new test asserts `result.status_code == 403` and `body["status"] == 403`.
- [ ] The existing `assert body["error"] is True` remains.
- [ ] `pytest tests/test_api.py -k "no_policy"` passes.
- [ ] No other test method or fixture is renamed.

### Deliverable Location

`tests/test_api.py`

### Expected Effort

Trivial (5 min).

## Task 4: Regression tests for PATCH/POST/PUT merge

### Objective

Lock in the new merge behavior so the bug does not regress.

### Files to Create/Modify

- `tests/test_api.py` — add a new `TestParamMerge` (or extend `TestApiProxy`) class with at least the cases in the matrix below.
- `tests/conftest.py` — add a `client` fixture that builds an in-process FastAPI app using `create_api_router()` and a stub `validate_api_key` dependency, if it does not already exist. If it does, reuse it.

### Test matrix (all run against the live router, not the proxy)

| Test name | Method | Path | Query | Body | Expected `params` dict after handler |
|---|---|---|---|---|---|
| `test_patch_query_only_no_body` | PATCH | `/api/v1/drive/files/update` | `addParents=A&removeParents=B` | — | `{add_parents: "A", remove_parents: "B"}` |
| `test_patch_body_only_no_query` | PATCH | `/api/v1/drive/files/update` | — | `{file_id: "x", name: "y"}` | `{file_id: "x", name: "y"}` |
| `test_patch_body_and_query_merge` | PATCH | `/api/v1/drive/files/update` | `addParents=A` | `{file_id: "x", name: "y"}` | `{add_parents: "A", file_id: "x", name: "y"}` |
| `test_patch_body_overrides_query` | PATCH | `/api/v1/drive/files/update` | `addParents=URL` | `{add_parents: "BODY"}` | `{add_parents: "BODY"}` |
| `test_patch_malformed_json_falls_back_to_query` | PATCH | `/api/v1/drive/files/update` | `addParents=A` | `<not json>` | `{add_parents: "A"}` |
| `test_post_query_only_no_body` | POST | `/api/v1/gmail/messages/send` | `threadId=t1` | — | `{thread_id: "t1"}` |
| `test_put_body_and_query_merge` | PUT | `/api/v1/drive/files/update` | `addParents=A` | `{file_id: "x"}` | `{add_parents: "A", file_id: "x"}` |

To capture the `params` dict without actually calling Google, stub `GoogleProxy.call_google` to return whatever it was called with — a `unittest.mock.AsyncMock` returning a fixed `JSONResponse` is sufficient. The assertion is then on the `params` argument the proxy was invoked with.

### Acceptance Criteria

- [ ] All seven tests above are present and pass.
- [ ] `pytest tests/test_api.py` runs the new class without modifying any existing test in a way that breaks.
- [ ] No test relies on hitting the real Google API (it is offline CI-safe).

### Deliverable Location

`tests/test_api.py`

### Expected Effort

Small (30–60 min) — mostly fixture plumbing.

## Task 5: Enrich audit log with response message

### Objective

Make future "is this 404 or 403?" investigations answerable from the audit log alone, instead of requiring live server logs.

### Files to Create/Modify

- `gatekeeper/logging.py` — extend `log_request(...)` signature with `response_message: str | None = None`. Pass it through to whatever persistence layer is used.
- `gatekeeper/api/proxy.py` — at the 403 denial site (line ~80-93), pass `response_message=decision.reason`. At the 404 sites (lines ~100-108 and ~116-120), pass `response_message=<the literal "Module not found" / "Route not found" string>`. At the 401/413/400/502/500 sites, pass the message.
- **Persistence choice** (implementation decision — see Risks below): either
  - **(a)** add a nullable `response_message TEXT` column to the audit log table (requires a migration), or
  - **(b)** append the message to the existing `response_summary` field with a delimiter, e.g. `f"{summary} | {message}"` for denials, where `summary` is the existing 200-char body snippet.
  The spec recommends (a) for clean querying; (b) is acceptable as a smaller-blast-radius fallback if the implementer judges a migration too costly this cycle.

### Acceptance Criteria

- [ ] `log_request` accepts and persists `response_message` (either as a new column or appended to `response_summary`).
- [ ] 403 denials record the `decision.reason` string.
- [ ] 404 (module/route not found) records the literal "Module not found" / "Route not found" string.
- [ ] 5xx and 502 record the exception message.
- [ ] A new test asserts that a 403 denial produces a row whose persisted `response_message` (or `response_summary` suffix) contains the word "policy" or "disabled" or "defined" — pick whichever matches the actual reason.
- [ ] If a new column is added, a migration script is added under the project's migration directory.

### Deliverable Location

`gatekeeper/logging.py`, `gatekeeper/api/proxy.py`, plus a migration if option (a).

### Expected Effort

Medium (45–90 min) — most of the time is the migration if option (a) is chosen.

## Task 6: End-to-end PATCH-move against a fake Google

### Objective

Prove the full request path works: REST caller → router → proxy → (fake) Google. Catches any regression in the param merge + query/body split + URL construction.

### Files to Create/Modify

- `tests/test_proxy_e2e.py` (new) or append to `tests/test_api.py` — spin up `httpx.MockTransport` that returns a canned 200 for `PATCH https://www.googleapis.com/drive/v3/files/{fileId}?addParents=...&removeParents=...&...`. Stub the Google credentials manager to return a non-empty token. Call `proxy.call_google(...)` with the post-merge `params` dict. Assert the outgoing request's URL query string contains `addParents=A&removeParents=B` and the body contains `{"name": "renamed.doc"}`.

### Acceptance Criteria

- [ ] Test passes against the fake transport.
- [ ] The asserted URL query string is exactly the post-split `query_params` (i.e. `addParents` and `removeParents` only, no `file_id`).
- [ ] The asserted body is exactly the post-split `body_params` (i.e. `{"name": "renamed.doc"}`, no `file_id`, no `addParents`).
- [ ] The test is offline (no network).

### Deliverable Location

`tests/test_proxy_e2e.py`

### Expected Effort

Medium (45–90 min).

## Risks and Assumptions Lens Must Inspect

1. **The 404 is not what the code does today.** The proxy never returns 404 except for "module not found" or "route not found" (proxy.py lines 100-120), and both modules and routes are seeded at startup. The most plausible explanations for the user-reported 404 are: (a) the user hit a different path (e.g. `PATCH /api/v1/drive/files/{fileId}` instead of `/api/v1/drive/files/update`); (b) a FastAPI native 404 from a trailing-slash or method mismatch; (c) middleware. The spec does not chase the 404 phantom directly — it relies on Task 5 (audit log enrichment) to make the next occurrence diagnosable. **Lens should confirm this disposition is acceptable**, or call out a need to add a request-receiver middleware that records the raw incoming path.

2. **Enabling `drive.files.update` by default is a behavior change.** Existing deployments that relied on the opt-in default will see previously-denied requests succeed. The migration note covers the manual case, but auto-migration is out of scope. **Lens should confirm** this is acceptable for the current release cadence.

3. **The body-override-query precedence is a deliberate design call.** REST convention varies (some prefer query-wins, some body-wins). The spec picks body-wins to match the intuition that an explicit body field is more specific than a URL param. **Lens should confirm** this matches the project's REST conventions, or call for the opposite.

4. **The audit-log column choice (Task 5) has a migration cost.** If the implementer picks option (b) (append to `response_summary`), the test contract must be updated accordingly. **Lens should pin which option is in scope** before Task 5 starts.

5. **The misnamed test fix (Task 3) must not be conflated with a real 404 → 403 behavior change.** It is purely a rename + assertion tightening. **Lens should verify** the test still passes against the current code (it does — the docstring already says 403 and the proxy returns 403 today).

6. **Pydantic schemas for PATCH/POST/PUT bodies are not in scope.** The current handlers treat the body as a free-form `dict`. Adding Pydantic validation is a separate spec. **Lens should confirm** this is not a hidden requirement.

7. **Concurrency on `RoutePolicy` rows.** `seed_default_policies()` is called on every startup and has a TOCTOU window. This is pre-existing and out of scope for this spec, but **Lens should note it** if the project has a migration / hot-reload story.

## Deployment Notes (for the implementer, not the spec body)

- After Task 2 ships, operators on existing deployments with a seeded `RoutePolicy(module="drive", route="drive.files.update", enabled=False)` row must either (a) flip `enabled=True` via the admin API or `gatekeeper policy enable drive.files.update`, or (b) delete the row and restart so `seed_default_policies()` reseeds it as `enabled=True`.
- The `enabled_by_default` change does NOT affect fresh installations — `seed_default_policies()` reads the new value directly.

## Acceptance Criteria for the Spec Itself (what Lens checks)

- Every numbered task has a falsifiable acceptance criterion.
- Every modified file is listed in the corresponding task.
- No task depends on a missing upstream — Tasks 1, 2, 3, 5 are independent; 4 depends on 1; 6 depends on 1 + 2.
- All "Important constraints, risks, and assumptions" are listed in the Risks section.
- The spec is implementation-ready: an implementer reading only this file can make the changes without re-reading the research brief.
