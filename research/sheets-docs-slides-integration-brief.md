# Intelligence Brief: Google Sheets, Docs, and Slides API Integration for Gatekeeper

## Summary

Integrating Google Sheets, Docs, and Slides APIs into the Gatekeeper Drive module is **technically feasible** but requires a **critical architectural change** to the proxy layer: all three APIs use different base hostnames (`sheets.googleapis.com`, `docs.googleapis.com`, `slides.googleapis.com`) rather than the `www.googleapis.com` host that Drive, Gmail, and Calendar currently share. The existing `GOOGLE_API_BASE` constant and `MODULE_API_MAP` cannot accommodate this without modification. Two viable approaches exist: (A) extend RouteDef with a `base_url` field, or (B) extend `MODULE_API_MAP` to include per-module base URLs. Approach A is cleaner and more future-proof.

---

## Evidence

### 1. OAuth Scopes Required

| API | Scope (Read-Only) | Scope (Read/Write) | Confidence |
|---|---|---|---|
| Sheets | `https://www.googleapis.com/auth/spreadsheets.readonly` | `https://www.googleapis.com/auth/spreadsheets` | Certain — official docs |
| Docs | `https://www.googleapis.com/auth/documents.readonly` | `https://www.googleapis.com/auth/documents` | Certain — official docs |
| Slides | `https://www.googleapis.com/auth/presentations.readonly` | `https://www.googleapis.com/auth/presentations` | Certain — official docs |

Note: The existing Drive module uses `https://www.googleapis.com/auth/drive` which is a **broader scope** that includes read/write access to Sheets, Docs, and Slides files as Drive files. However, accessing the structured content of these file types (cell ranges, document body, slide elements) requires the respective API-specific scopes above. The Drive scope alone is **not sufficient** for the Sheets/Docs/Slides APIs.

### 2. API Base Paths and Versioning

| API | Base URL | Version | Confidence |
|---|---|---|---|
| Sheets | `https://sheets.googleapis.com/v4/spreadsheets` | v4 | Certain — official reference |
| Docs | `https://docs.googleapis.com/v1/documents` | v1 | Certain — official reference |
| Slides | `https://slides.googleapis.com/v1/presentations` | v1 | Certain — official reference |

**Critical finding**: All three APIs use **different hostnames** from the Drive/Gmail/Calendar APIs that share `www.googleapis.com`. Verified that `www.googleapis.com/v4/spreadsheets` and `www.googleapis.com/v1/documents` both return 404 — these APIs are NOT available on the shared hostname.

### 3. Current Proxy Architecture — URL Construction

The proxy (`gatekeeper/api/proxy.py`) constructs URLs in `call_google()` (lines 196-202):

```python
GOOGLE_API_BASE = "https://www.googleapis.com"
MODULE_API_MAP = {
    "drive": "/drive/v3",
    "gmail": "/gmail/v1",
    "calendar": "/calendar/v3",
}

# In call_google():
if route.google_path.startswith("/"):
    # Absolute path — prepend base only
    url = f"{GOOGLE_API_BASE}{google_path}"
else:
    # Relative path — prepend module prefix
    api_prefix = MODULE_API_MAP.get(module_name, f"/{module_name}/v1")
    url = f"{GOOGLE_API_BASE}{api_prefix}/{google_path}"
```

**Current Drive routes** all use absolute `google_path` values starting with `/` (e.g., `/drive/v3/files`), which produce `https://www.googleapis.com/drive/v3/files`. This works because Drive v3 IS available at that URL.

**Problem for Sheets/Docs/Slides**: Even if we add routes like `google_path="/v4/spreadsheets/{spreadsheetId}"`, the proxy will construct `https://www.googleapis.com/v4/spreadsheets/{spreadsheetId}` — which returns 404. The proxy needs per-module (or per-route) base URL support.

### 4. Module Architecture Observations

- Each module class extends `GoogleModule` and defines `name`, `required_scopes`, and `get_routes()`.
- The `modules/__init__.py` registry (`AVAILABLE_MODULES`) maps module names to import paths.
- The `config.py` has boolean flags per module: `drive_enabled`, `gmail_enabled`, `calendar_enabled`.
- The `GoogleCredentialManager._get_enabled_scopes()` method aggregates scopes from enabled modules.
- The proxy's `MODULE_API_MAP` currently only maps module names to **path prefixes**, not base URLs.

### 5. Key API Operations for Sheets, Docs, Slides

#### Sheets API (v4)
Key routes needed:

| Route | Method | Google Path | Description |
|---|---|---|---|
| `sheets.spreadsheets.get` | GET | `/v4/spreadsheets/{spreadsheetId}` | Get spreadsheet metadata |
| `sheets.spreadsheets.values.get` | GET | `/v4/spreadsheets/{spreadsheetId}/values/{range}` | Read cell range |
| `sheets.spreadsheets.values.batchGet` | GET | `/v4/spreadsheets/{spreadsheetId}/values:batchGet` | Read multiple ranges |
| `sheets.spreadsheets.values.update` | PUT | `/v4/spreadsheets/{spreadsheetId}/values/{range}` | Write cell range |
| `sheets.spreadsheets.values.batchUpdate` | POST | `/v4/spreadsheets/{spreadsheetId}/values:batchUpdate` | Write multiple ranges |
| `sheets.spreadsheets.values.append` | POST | `/v4/spreadsheets/{spreadsheetId}/values:append` | Append data |
| `sheets.spreadsheets.values.clear` | POST | `/v4/spreadsheets/{spreadsheetId}/values/{range}:clear` | Clear cell range |

#### Docs API (v1)
Key routes needed:

| Route | Method | Google Path | Description |
|---|---|---|---|
| `docs.documents.get` | GET | `/v1/documents/{documentId}` | Get document content |
| `docs.documents.create` | POST | `/v1/documents` | Create new document |
| `docs.documents.batchUpdate` | POST | `/v1/documents/{documentId}:batchUpdate` | Edit document (insert/delete text, etc.) |

#### Slides API (v1)
Key routes needed:

| Route | Method | Google Path | Description |
|---|---|---|---|
| `slides.presentations.get` | GET | `/v1/presentations/{presentationId}` | Get presentation data |
| `slides.presentations.pages.get` | GET | `/v1/presentations/{presentationId}/pages/{pageObjectId}` | Get slide page |
| `slides.presentations.batchUpdate` | POST | `/v1/presentations/{presentationId}:batchUpdate` | Edit presentation |

---

## Gaps

1. **Per-route/per-module base URL**: The proxy currently has no mechanism to route requests to different Google API hostnames. This is the **single most important gap** — without it, no Sheets/Docs/Slides route will work.

2. **Config module flags**: New modules need `sheets_enabled`, `docs_enabled`, and `slides_enabled` settings added to `config.py`, plus corresponding entries in `_get_enabled_scopes()`.

3. **Module registry**: `AVAILABLE_MODULES` in `modules/__init__.py` needs entries for the new modules.

4. **Batch update body transformation**: Sheets `values.update` and Docs/Slides `batchUpdate` all use structured JSON request bodies (e.g., `ValueRange` for Sheets, `Request[]` for Docs/Slides) that differ from the flat-parameter pattern used by Drive/Gmail routes. The proxy may need per-route body transformation hooks similar to the existing `_restructure_filter_body` for Gmail filters.

5. **Sheets `valueInputOption` parameter**: The Sheets `values.update` and `values.append` endpoints **require** a `valueInputOption` query parameter (e.g., `USER_ENTERED` or `RAW`). This is similar to the `query_params` pattern already used in Drive routes — no architectural change needed, just explicit listing in `RouteDef.query_params`.

6. **Sheets `fields` as Opaque Parameter**: The `fields` parameter for Sheets `spreadsheets.get` should be sent as a query parameter (not in the body), similar to Drive's pattern.

---

## Recommendations

### Architecture Change Required: Per-Module Base URL

**Recommended approach: Add `base_url` field to `RouteDef`**

```python
class RouteDef(BaseModel):
    # ... existing fields ...
    base_url: str | None = None  # Override the module-level base URL
```

When `base_url` is set on a route, the proxy uses it instead of `GOOGLE_API_BASE`. This is the most flexible approach because:
- It doesn't require restructuring the entire proxy
- Individual routes can target any hostname
- It's backwards-compatible (None means use the module default)
- The `MODULE_API_MAP` can also be extended for default-per-module base URLs

**Alternative approach: Extend MODULE_API_MAP with full base URLs**

```python
MODULE_API_MAP = {
    "drive": {"base_url": "https://www.googleapis.com", "prefix": "/drive/v3"},
    "gmail": {"base_url": "https://www.googleapis.com", "prefix": "/gmail/v1"},
    "calendar": {"base_url": "https://www.googleapis.com", "prefix": "/calendar/v3"},
    "sheets": {"base_url": "https://sheets.googleapis.com", "prefix": "/v4"},
    "docs": {"base_url": "https://docs.googleapis.com", "prefix": "/v1"},
    "slides": {"base_url": "https://slides.googleapis.com", "prefix": "/v1"},
}
```

This is simpler but less flexible. The RouteDef approach is preferred because it avoids the need to coordinate between `MODULE_API_MAP` and `google_path` for routes on non-default hostnames.

### Module Placement Decision

The task says "adding scopes and RouteDefs to the Drive module." This is **not recommended** because:

1. **Different API hostnames**: Sheets/Docs/Slides are fundamentally different services from Drive, with their own base URLs, scopes, and rate limits.
2. **Scope contamination**: The Drive module currently has a single `required_scopes` list. Adding 6 new scopes for 3 different APIs would make the scope list confusing and would force all Drive users to authorize Sheets/Docs/Slides even if they only want Drive.
3. **Module design pattern**: Each existing module (Drive, Gmail, Calendar) is a self-contained `GoogleModule` subclass. The consistent pattern is to create new module classes.

**Recommendation**: Create three new module files:
- `gatekeeper/modules/sheets/__init__.py` — `SheetsModule`
- `gatekeeper/modules/docs/__init__.py` — `DocsModule`
- `gatekeeper/modules/slides/__init__.py` — `SlidesModule`

### Pitfalls

1. **Quota**: Sheets API has 300 read req/min/project and 60 read req/min/user, 300 write req/min/project and 60 write req/min/user. Docs API has similar per-minute quotas (300 per project, 60 per user). These are lower than Drive's limits and should be noted in `default_policy` with `max_results` caps.

2. **Batch operations are the norm**: The Docs and Slides APIs use `batchUpdate` for ALL mutations. There are no individual "insert text" or "add slide" endpoints — everything goes through `batchUpdate` with an array of `Request` objects. This means write routes need careful body schema definitions.

3. **Sheets values.update requires `valueInputOption`**: This is a mandatory query parameter that must be set to `USER_ENTERED` or `RAW`. Without it, the API returns 400.

4. **Docs API has no "update" endpoint for simple text**: All edits go through `documents.batchUpdate` which requires structured `Request` objects. The `documents.create` endpoint only accepts `title`.

5. **Slides `batchUpdate` requires structured requests**: Similar to Docs, all mutations on Slides go through `batchUpdate`.

6. **OAuth re-authorization required**: Adding new scopes means existing users must re-authorize. The `required_scopes` on new modules should be additive and the auth flow should request all enabled module scopes.

7. **The proxy's `_restructure_filter_body` pattern should be generalized**: Currently it's a hard-coded method for Gmail filters. The new Sheets/Docs/Slides write routes will need similar body transformation. Consider making this a per-route hook or adding a `body_transform` field to `RouteDef`.