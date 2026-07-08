# Intelligence Brief: Drive Module Expansion — Hostname Validation & Architecture Assessment

## Summary

The root task's proposed implementation strategy of adding Sheets/Docs/Slides routes to the existing Drive module is **NOT VIABLE as written**. The proxy (`api/proxy.py`) hardcodes `GOOGLE_API_BASE = "https://www.googleapis.com"` and uses it for ALL URL construction. All three Workspace APIs (Sheets, Docs, Slides) use **different hostnames** — confirmed by both the Google Discovery documents and live HTTP testing. Adding `google_path="/sheets/v4/..."` to a Drive route will produce `https://www.googleapis.com/sheets/v4/...`, which returns **HTML 404**. The proxy must be modified to support per-route base URLs before any Sheets/Docs/Slides routes can function.

## Evidence

### 1. API Hostname Requirements (CERTAIN)

Live HTTP testing confirms the three Workspace APIs are NOT served from `www.googleapis.com`:

| URL Pattern | Status | Response |
|---|---|---|
| `https://sheets.googleapis.com/v4/spreadsheets/{id}` | 403 | "Method doesn't allow unregistered callers" (endpoint exists, auth required) |
| `https://www.googleapis.com/v4/spreadsheets/{id}` | 404 | HTML 404 page (endpoint does not exist) |
| `https://docs.googleapis.com/v1/documents/{id}` | 401 | "Request is missing required authentication credential" (endpoint exists, auth required) |
| `https://www.googleapis.com/v1/documents/{id}` | 404 | HTML 404 page (endpoint does not exist) |
| `https://slides.googleapis.com/v1/presentations/{id}` | 401 | "Request is missing required authentication credential" (endpoint exists, auth required) |
| `https://www.googleapis.com/v1/presentations/{id}` | 404 | HTML 404 page (endpoint does not exist) |
| `https://www.googleapis.com/drive/v3/files` | 403 | Auth required (endpoint exists — this is the current working pattern) |

**Verdict:** The root task's claim that `google_path="/sheets/v4/..."` will "work correctly" because "the proxy calls `https://googleapis.com/sheets/v4/...`" is **FALSE**. The proxy constructs `https://www.googleapis.com/sheets/v4/...`, which returns 404.

### 2. Google Discovery Document Confirmation (CERTAIN)

The official API Discovery documents confirm the canonical base URLs:

| API | Discovery URL | baseUrl | rootUrl |
|---|---|---|---|
| Sheets | `https://sheets.googleapis.com/$discovery/rest?version=v4` | `https://sheets.googleapis.com/` | `https://sheets.googleapis.com/` |
| Docs | `https://docs.googleapis.com/$discovery/rest?version=v1` | `https://docs.googleapis.com/` | `https://docs.googleapis.com/` |
| Slides | `https://slides.googleapis.com/$discovery/rest?version=v1` | `https://slides.googleapis.com/` | `https://slides.googleapis.com/` |

All three APIs have their own dedicated hostname. None share `www.googleapis.com`.

### 3. Current Proxy Architecture — URL Construction (CERTAIN)

From `gatekeeper/api/proxy.py` lines 29-36 and 195-202:

```python
GOOGLE_API_BASE = "https://www.googleapis.com"

MODULE_API_MAP = {
    "drive": "/drive/v3",
    "gmail": "/gmail/v1",
    "calendar": "/calendar/v3",
}

# In call_google():
if route.google_path.startswith("/"):
    url = f"{GOOGLE_API_BASE}{google_path}"
else:
    api_prefix = MODULE_API_MAP.get(module_name, f"/{module_name}/v1")
    url = f"{GOOGLE_API_BASE}{api_prefix}/{google_path}"
```

**Both code paths use `GOOGLE_API_BASE`** (which is `https://www.googleapis.com`). There is no mechanism for a route to specify a different base URL. The `MODULE_API_MAP` only controls the path prefix, not the hostname.

### 4. RouteDef Model — No base_url Field (CERTAIN)

From `gatekeeper/modules/route.py`:

```python
class RouteDef(BaseModel):
    route_id: str
    method: str = "GET"
    google_path: str
    description: str = ""
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}
    query_params: list[str] = []
    binary_response: bool = False
    multipart_upload: bool = False
    default_policy: dict[str, Any] = {}
    enabled_by_default: bool = True
```

No `base_url` field exists. No per-route hostname override is possible.

### 5. Root Task's Architectural Claim (DISPROVEN)

The root task (t_cb75e033e8c2) states:

> "The proxy in `api/proxy.py` uses each route's `google_path` directly when it starts with `/` — so routes can point to any Google API path (`/sheets/v4/...`, `/docs/v1/...`, `/slides/v1/...`) regardless of which module they belong to. The `MODULE_API_MAP` is only a fallback for relative paths. This means we can add Sheets/Docs/Slides routes to the Drive module by: (1) expanding `required_scopes` to include the three new OAuth scopes, and (2) appending new `RouteDef` entries to the existing `get_routes()` return list. No new modules, no registry changes, no config changes, **no proxy changes**."

This claim is **incorrect**. While it is true that `google_path` starting with `/` is used directly, the resulting URL is `https://www.googleapis.com{/sheets/v4/...}`, which returns 404. The proxy **must** be modified to support per-route base URLs.

## Assessment: FAIL

The root task's implementation strategy **fails** because it does not account for the hostname difference. Adding `google_path="/sheets/v4/spreadsheets/{spreadsheetId}"` to a Drive module route will construct `https://www.googleapis.com/sheets/v4/spreadsheets/{spreadsheetId}` — which returns a 404 HTML page.

## Required Architectural Changes for Cartographer

The following changes are necessary before any Sheets/Docs/Slides routes can work:

### Change 1: Add `base_url` field to `RouteDef`

**File:** `gatekeeper/modules/route.py`

```python
class RouteDef(BaseModel):
    # ... existing fields ...
    base_url: str | None = None  # Override GOOGLE_API_BASE for this route
```

### Change 2: Update `call_google()` in proxy to use `base_url`

**File:** `gatekeeper/api/proxy.py`

In the URL construction section (lines 195-202), replace:

```python
# Current:
if route.google_path.startswith("/"):
    url = f"{GOOGLE_API_BASE}{google_path}"
else:
    api_prefix = MODULE_API_MAP.get(module_name, f"/{module_name}/v1")
    url = f"{GOOGLE_API_BASE}{api_prefix}/{google_path}"
```

With:

```python
# New:
base = route.base_url or GOOGLE_API_BASE
if route.google_path.startswith("/"):
    url = f"{base}{google_path}"
else:
    api_prefix = MODULE_API_MAP.get(module_name, f"/{module_name}/v1")
    url = f"{base}{api_prefix}/{google_path}"
```

### Change 3: Set `base_url` on all new routes

Every Sheets, Docs, and Slides `RouteDef` must include `base_url="https://sheets.googleapis.com"`, `base_url="https://docs.googleapis.com"`, or `base_url="https://slides.googleapis.com"` respectively.

### Change 4 (Optional but Recommended): Separate module classes

The parent research task (t_1baea2b6) recommended creating three separate module classes (SheetsModule, DocsModule, SlidesModule) instead of adding routes to DriveModule. This is the cleaner architectural pattern, consistent with how Drive, Gmail, and Calendar are each their own module. However, the `base_url` approach works either way — routes can be in DriveModule or in separate modules.

If adding routes to DriveModule (per the root task's preference):
- Simpler implementation (no new module files, no config changes)
- Set `base_url` on each new `RouteDef`
- Still requires proxy changes (Change 1 + Change 2)

If creating separate modules (per parent research recommendation):
- Cleaner separation of concerns
- Each module can define its own `base_url` default
- Requires config flags (`sheets_enabled`, `docs_enabled`, `slides_enabled`) and registry entries
- More changes but better long-term architecture

## Gaps

1. **No `base_url` field exists on `RouteDef`** — must be added.
2. **Proxy hardcodes `GOOGLE_API_BASE`** — must be made per-route configurable.
3. **Root task's implementation plan will produce 404 errors** — it must be revised.
4. **OAuth re-authorization is still required** regardless of architecture — adding scopes means users must re-auth.

## Recommendations

1. **Cartographer must specify Changes 1-3 above** as prerequisites before any route additions.
2. **The root task should be updated** to reflect the proxy change requirement.
3. **Module placement is a design choice** — either DriveModule consolidation or separate modules will work, as long as `base_url` is set on each route.