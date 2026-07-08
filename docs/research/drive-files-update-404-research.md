## Intelligence Brief: Fix 404 Error on Gatekeeper Drive Files Update Endpoint

### Summary

The `PATCH /api/v1/drive/files/update` endpoint has **two confirmed bugs** and **one configuration issue**:

1. **Route disabled by default** — `enabled_by_default=False` means the route requires an explicit RoutePolicy enable before any request can succeed.
2. **PATCH handler drops query parameters** — `router.py` lines 146-168: the PATCH handler falls back to `params = {}` on JSON parse failure, unlike POST/PUT which fall back to `dict(request.query_params)`. This means REST callers sending `addParents`/`removeParents` as URL query params lose them entirely.
3. **The 404 vs 403 discrepancy** — The proxy code always returns 403 for policy denials (lines 80-93 of proxy.py). A 404 can only occur if (a) the module is not loaded, (b) the route_id is not found in the module's route list, or (c) FastAPI itself doesn't match the request. Since the route IS registered and the module IS loaded, the 404 in the audit log likely came from a scenario where `seed_default_policies()` was not run (or the module failed to load at runtime).

### Evidence

| # | Claim | Source | Confidence |
|---|---|---|---|
| 1 | `drive.files.update` has `enabled_by_default=False` | `gatekeeper/modules/drive/__init__.py` line 304 | Certain |
| 2 | Policy engine returns `allowed=False` with 403 when no RoutePolicy row exists | `gatekeeper/policy.py` lines 67-72: `PolicyDecision(allowed=False, reason="No policy defined for {route}")` → proxy returns 403 at lines 80-93 | Certain |
| 3 | Policy engine returns `allowed=False` with 403 when route is explicitly disabled | `gatekeeper/policy.py` lines 74-78: `PolicyDecision(allowed=False, reason="Route {route} is disabled")` → proxy returns 403 | Certain |
| 4 | PATCH handler does NOT merge `request.query_params` (bug) | `gatekeeper/api/router.py` lines 146-168: `params = await request.json()` with fallback to `params = {}` — contrast with POST (lines 98-120) and PUT (lines 122-144) which fall back to `dict(request.query_params)` | Certain |
| 5 | POST and PUT handlers DO merge query params as fallback | `gatekeeper/api/router.py` lines 109-112 (POST) and 133-136 (PUT): `except Exception: params = dict(request.query_params)` | Certain |
| 6 | DELETE handler uses only `dict(request.query_params)` | `gatekeeper/api/router.py` lines 170-189: `params = dict(request.query_params)` — no JSON body parsing at all | Certain |
| 7 | REST path is flat: `/api/v1/drive/files/update` (no `{fileId}`) | `gatekeeper/api/router.py` lines 44-49: `parts[1].replace('.', '/')` converts `"files.update"` → `"/files/update"` | Certain |
| 8 | `file_id` is passed as JSON body param and proxy substitutes into Google path | `gatekeeper/api/proxy.py` lines 148-188: snake_case→camelCase normalization + `{fileId}` placeholder substitution | Certain |
| 9 | `addParents`/`removeParents` are correctly split from body into Google query params by the proxy | `gatekeeper/api/proxy.py` lines 227-244: `camel_query_keys` splits marked params into `query_params` dict, rest goes to `body_params` | Certain |
| 10 | MCP path works correctly because it passes all params as a dict directly to `call_google()` | `gatekeeper/mcp_server/__init__.py` lines 261-270: `params=arguments` — no REST query param parsing involved | Certain |
| 11 | All module routes are always registered in FastAPI at startup | `gatekeeper/api/router.py` lines 30-34: docstring + `create_api_router()` iterates all modules and all routes | Certain |
| 12 | `seed_default_policies()` seeds routes with `enabled=False` when `enabled_by_default=False` | `gatekeeper/main.py` lines 49-92: `defaults.get("enabled", route.enabled_by_default)` — since `drive.files.update` has `enabled_by_default=False` and no override in `get_default_policies()`, it seeds `enabled=False` | Certain |
| 13 | Proxy returns 404 only for "Module not found" (line 96-108) or "Route not found" (line 116-120) | `gatekeeper/api/proxy.py` lines 96-120: only two 404 paths, both inside `call_google` after policy check | Certain |
| 14 | The test `test_no_policy_returns_404` is misnamed — it actually tests 403 behavior | `tests/test_api.py` line 88: test name says "404" but docstring says "403 (default deny)" and only asserts `body["error"] is True` without checking status code | Certain |

### Root Cause Analysis

#### Bug #1: PATCH handler drops query parameters

**Location:** `gatekeeper/api/router.py` lines 146-168

```python
elif method == "PATCH":
    ...
    try:
        params = await request.json()
    except Exception:
        params = {}  # BUG: should be dict(request.query_params)
```

**Impact:** REST callers who send `addParents` or `removeParents` as query parameters on a PATCH request (e.g., `PATCH /api/v1/drive/files/update?addParents=folder1`) will have those params silently dropped. The proxy will then send the request to Google without these required query params, causing the Google API to behave unexpectedly (it silently ignores `addParents`/`removeParents` in the PATCH body).

**Contrast with other handlers:**
- GET: `params = dict(request.query_params)` — correct
- POST: falls back to `dict(request.query_params)` — correct
- PUT: falls back to `dict(request.query_params)` — correct
- DELETE: `params = dict(request.query_params)` — correct
- PATCH: falls back to `{}` — **BUG**

**Additionally**, even when JSON body parsing succeeds, the PATCH handler does NOT merge query params. A caller who sends both JSON body AND query params on a PATCH request will lose the query params. The other handlers (POST, PUT) have the same limitation when JSON parsing succeeds — they don't merge query_params with the JSON body. However, PATCH is the only one with the empty-dict fallback.

#### Bug #2 (configuration): Route disabled by default

**Location:** `gatekeeper/modules/drive/__init__.py` line 304

`enabled_by_default=False` means the route requires explicit admin action to enable. After `seed_default_policies()`, the RoutePolicy row exists with `enabled=False`. Without enabling it, all requests get a 403 with message "Route drive.files.update is disabled".

#### The 404 mystery

The proxy code only returns 404 in two cases (lines 96-120 of proxy.py):
1. Module not loaded → `{"message": "Module {module_name} not found"}`
2. Route not found in module → `{"message": "Route {route_id} not found"}`

Both of these would require the module or route to be missing at runtime, which shouldn't happen with the current code since all modules are loaded at startup.

The most likely 404 scenario is that the user reporting the 404 was calling an endpoint path that didn't exactly match FastAPI's registered route, or the module failed to load. However, **policy denial always returns 403**, never 404. The audit log showing 404 suggests one of:
1. The audit log was recording status_code from somewhere other than the proxy response (e.g., a middleware or FastAPI native 404)
2. The module was not loaded at the time of the request
3. The request path didn't exactly match the registered FastAPI route (trailing slash, wrong method, etc.)

### Gaps

- **Cannot confirm the exact 404 source** without live server logs or database state. The audit log should include the response body to distinguish policy 403 from module/route-not-found 404 from native FastAPI 404.
- **The PATCH handler's JSON-only param collection means even with the fallback fix, query params aren't merged with JSON body params.** A more complete fix would merge both: `params = {**dict(request.query_params), **(await request.json())}` or vice versa. This is the pattern needed for `addParents`/`removeParents` support via REST.

### Recommendations

1. **Fix the PATCH handler fallback** — Change `params = {}` to `params = dict(request.query_params)` in `router.py` line 160. This matches the behavior of POST and PUT handlers.

2. **Consider merging query_params into JSON body for PATCH/POST/PUT** — Currently all three handlers collect params from only one source. For REST callers who need to send `addParents` as a query param alongside a JSON body, the handler should merge both: `params = {**dict(request.query_params), **(await request.json())}` (JSON body takes precedence for overlapping keys).

3. **Enable the route** — Set `enabled_by_default=True` for `drive.files.update` or enable it via the admin API after deployment. This is a configuration change, not a code bug.

4. **Add audit log response body** — Include the response body or at least the error message in audit log entries. This would make debugging 404 vs 403 issues trivial.

5. **Fix the misnamed test** — `test_no_policy_returns_404` in `test_api.py` should be renamed `test_no_policy_returns_403` to match the actual behavior and its own docstring.