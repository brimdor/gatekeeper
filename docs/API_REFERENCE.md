# Gatekeeper REST API Reference

**Audience:** Agents and operators using or scripting against the REST API (not the MCP transport).  
**See also:** [ROUTES.md](ROUTES.md) for the full route table and input schemas, [AGENT_ERRORS.md](AGENT_ERRORS.md) for error recovery.

---

## 1. Overview

- **Base URL:** `http://localhost:8080/api/v1` (port configurable via `GATEKEEPER_PORT`).
- **OpenAPI docs:** `http://localhost:8080/docs` (FastAPI auto-generated).
- **Health check:** `GET http://localhost:8080/health`.

## 2. Authentication

Pass the API key in one of these ways:

- **Header (preferred):** `Authorization: Bearer gkp_...`
- **Legacy header:** `X-Gatekeeper-API-Key: gkp_...`
- **Query string:** `?api_key=gkp_...` (use only for quick tests)

The MCP `api_key` *parameter* and the REST `Authorization` *header* carry the same key. Keys start with the configured prefix (default `gkp_`) and are verified with bcrypt in `gatekeeper/auth.py:28-60`.

## 3. URL Structure

```text
/api/v1/{module}/{route-path}
```

- `{module}` is one of `drive`, `gmail`, `calendar`, `forms`, `appsscript`.
- `{route-path}` is derived from `route_id` by stripping the leading module name and replacing dots with slashes.

Examples:

| `route_id` | HTTP method | URL |
|---|---|---|
| `drive.files.list` | GET | `/api/v1/drive/files/list` |
| `gmail.messages.get` | GET | `/api/v1/gmail/messages/get` |
| `calendar.events.list` | GET | `/api/v1/calendar/events/list` |
| `drive.files.upload` | POST | `/api/v1/drive/files/upload` |

Source: `gatekeeper/api/router.py:43-50`.

## 4. Per-Route Reference

This section summarizes each module. For the full list of 200 routes, their complete `input_schema`, required OAuth scopes, default policies, and binary/multipart flags, see [ROUTES.md](ROUTES.md).

### Drive

**Required OAuth scopes:** `drive`, `spreadsheets`, `documents`, `presentations`.  
**Enabled by default:** 36 of 83 routes.  
**Binary routes:** `drive.files.export`, `drive.files.download`.  
**Multipart upload route:** `drive.files.upload`.  
**Per-route base URLs:** 16 Sheets/Docs/Slides routes use `https://sheets.googleapis.com` or `https://docs.googleapis.com` or `https://slides.googleapis.com`.

#### Example: list files

```bash
curl -H "Authorization: Bearer $GK_API_KEY" \
  "http://localhost:8080/api/v1/drive/files/list?q=name+contains+'report'&page_size=10"
```

Response (truncated):

```json
{
  "files": [
    {"id": "...", "name": "report.pdf", "mimeType": "application/pdf"}
  ],
  "nextPageToken": "..."
}
```

#### Example: export a file

```bash
curl -H "Authorization: Bearer $GK_API_KEY" \
  "http://localhost:8080/api/v1/drive/files/export?file_id=ABC123&mime_type=application/pdf"
```

Response is base64-encoded content when small, or a saved file path when large. See [ROUTES.md](ROUTES.md) for `binary_response=True` details.

### Gmail

**Required OAuth scopes:** `gmail.modify`, `gmail.send`, `gmail.compose`, `gmail.settings.basic`.  
**Enabled by default:** 16 of 53 routes.

#### Example: list messages

```bash
curl -H "Authorization: Bearer $GK_API_KEY" \
  "http://localhost:8080/api/v1/gmail/messages/list?max_results=10&label_ids=INBOX"
```

Response:

```json
{
  "messages": [{"id": "...", "threadId": "..."}],
  "nextPageToken": "..."
}
```

### Calendar

**Required OAuth scopes:** `calendar`, `calendar.events`.  
**Enabled by default:** 13 of 38 routes.

#### Example: list events

```bash
curl -H "Authorization: Bearer $GK_API_KEY" \
  "http://localhost:8080/api/v1/calendar/events/list?calendar_id=primary&max_results=10"
```

Response:

```json
{
  "items": [{"id": "...", "summary": "Team standup", "start": {"dateTime": "..."}}]
}
```

## 5. Error Responses

Common envelope:

```json
{
  "error": true,
  "status": 403,
  "message": "Route drive.files.delete is disabled"
}
```

Common status codes:

| Code | Meaning |
|---|---|
| 400 | Bad request / invalid payload |
| 401 | Missing or invalid API key |
| 403 | Key lacks module permission or route disabled |
| 404 | Module/route not found |
| 413 | Upload too large |
| 421 | DNS rebinding rejected (MCP only) |
| 429 | Rate limit exceeded |
| 500 | Internal error |
| 502 | Google API error |
| 503 | Google transient error |
| 504 | Google timeout |

For recovery guidance, see [AGENT_ERRORS.md](AGENT_ERRORS.md).

## 6. Admin API

The `/admin/api/*` endpoints are used by the built-in admin UI. They require **HTTP Basic Auth** with the admin username and password configured at first run.

Endpoints (from `gatekeeper/admin/routes.py:31-280`):

| Method | Endpoint | Description |
|---|---|---|
| GET | `/admin/api/dashboard` | Dashboard statistics |
| GET | `/admin/api/keys` | List API keys |
| POST | `/admin/api/keys` | Create API key |
| DELETE | `/admin/api/keys/{id}` | Revoke API key |
| GET | `/admin/api/modules` | List modules |
| POST | `/admin/api/modules/{name}/toggle` | Toggle module routes |
| GET | `/admin/api/routes` | List route policies |
| PATCH | `/admin/api/routes/{id}` | Update route policy |
| GET | `/admin/api/audit` | Query audit log |
| GET | `/admin/api/auth/status` | Google OAuth status |

**Not for agent use.** Agents cannot create keys, modify policies, or access audit logs through the MCP interface.

## 7. Rate Limiting

- Global default: `GATEKEEPER_RATE_LIMIT_PER_MINUTE=120`.
- Applied per API key in a sliding window.
- Exceeded requests return:

  ```json
  {"error": true, "status": 429, "message": "Rate limit exceeded"}
  ```

Source: `gatekeeper/config.py:74`.

## 8. Binary and Multipart Routes


### Forms

**Required OAuth scopes:** `forms.body`, `forms.body.readonly`, `forms.responses.readonly`.  
**Enabled by default:** 0 of 10 routes.  
**Base URL:** `https://forms.googleapis.com` (per-route `base_url` set on all 10 routes).

#### Example: list form responses

```bash
curl -H "Authorization: Bearer ***" \
  "http://localhost:8080/api/v1/forms/forms/responses/list?form_id=FORM_ID&page_size=20"
```

### Apps Script

**Required OAuth scopes:** `script.projects`, `script.projects.readonly`, `script.deployments`, `script.deployments.readonly`, `script.processes`, `script.metrics`.  
**Enabled by default:** 0 of 16 routes.  
**Base URL:** `https://script.googleapis.com` (per-route `base_url` set on all 16 routes).  
**Security note:** `appsscript.scripts.run` executes arbitrary user-defined code under the authenticated user's credentials. Enable only with a restrictive policy.

#### Example: get script project

```bash
curl -H "Authorization: Bearer ***" \
  "http://localhost:8080/api/v1/appsscript/projects/get?script_id=SCRIPT_ID"
```
### Binary downloads

Routes with `binary_response=True` ask Google for raw bytes (`alt=media`). The proxy decides whether to inline the file as base64 or save it to disk based on the `max_inline_size_mb` policy key (default 1 MB). See `gatekeeper/api/proxy.py:440-504`.

Example flow for `drive.files.download`:

```bash
curl -H "Authorization: Bearer $GK_API_KEY" \
  "http://localhost:8080/api/v1/drive/files/download?file_id=ABC123"
```

### Multipart uploads

Routes with `multipart_upload=True` accept a `base64_content` parameter and build a `multipart/related` body for Google. Metadata fields (`name`, `mimeType`, `parents`, `description`) go into the JSON metadata part; the decoded bytes go into the binary part. See `gatekeeper/api/proxy.py:249-318`.

Example flow for `drive.files.upload`:

```bash
curl -X POST \
  -H "Authorization: Bearer $GK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "report.txt",
    "mime_type": "text/plain",
    "base64_content": "SGVsbG8sIHdvcmxkIQ=="
  }' \
  http://localhost:8080/api/v1/drive/files/upload
```

## 9. Parameter Handling

- **Schema defaults** are injected for missing optional parameters (`gatekeeper/api/proxy.py:125-128`).
- **Snake_case parameters** in the schema are normalized to camelCase before calling Google (`gatekeeper/api/proxy.py:150-154`).
- **Path parameters** (`{fileId}`, `{calendarId}`, etc.) are substituted into `google_path` and removed from the query/body (`gatekeeper/api/proxy.py:184-188`).
- **Array parameters** sent as JSON strings are parsed back into lists when the schema declares them as arrays (`gatekeeper/api/proxy.py:160-180`).
- **Query-only parameters** configured in `RouteDef.query_params` are forced onto the URL query string even for POST/PATCH routes (`gatekeeper/api/proxy.py:233-244`).
