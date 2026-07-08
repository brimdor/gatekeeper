# Gatekeeper Policy Configuration Reference

**Audience:** Operators and developers writing route policy configs.  
**See also:** [ARCHITECTURE.md](ARCHITECTURE.md) § Policy Engine, [AGENT_ERRORS.md](AGENT_ERRORS.md) § Error Envelope.

---

## 1. Policy Storage

Policies live in the `route_policies` table (`gatekeeper/models.py:46-60`). Each row stores:

- `module` — module name (e.g., `gmail`).
- `route` — route ID (e.g., `gmail.messages.list`).
- `enabled` — boolean; disabled routes return 403.
- `policy_config` — JSON-encoded transform settings.
- `description` — optional operator note.

Route policies are seeded automatically when you run `gatekeeper init`.

## 2. Per-Route Config Keys

All keys are optional. Transforms are applied in the order shown in §3.

### Request transforms

| Key | Type | Default | Applies to | Description | Source |
|---|---|---|---|---|---|
| `max_results` | `integer` | varies by route | Request | Caps `maxResults`, `max_results`, `pageSize`, or `page_size` to the policy value. | `gatekeeper/policy.py:102-107` |
| `allowed_labels` | `list[string]` | `[]` | Request | For Gmail routes: filters `labelIds` to this allowed set. | `gatekeeper/policy.py:110-115` |
| `exclude_labels` | `list[string]` | `[]` | Request | For Gmail routes: removes these labels from `labelIds`. | `gatekeeper/policy.py:118-123` |
| `query_filter` | `string` | `""` | Request | Appends a forced query to the `q` parameter with `AND`. | `gatekeeper/policy.py:126-132` |

### Response filters

| Key | Type | Default | Applies to | Description | Source |
|---|---|---|---|---|---|
| `blocked_fields` | `list[string]` | `[]` | Response | Removes top-level fields from the Google API response. | `gatekeeper/policy.py:151-153` |
| `max_items` | `dict[string, integer]` | `{}` | Response | Caps the length of named arrays in the response. | `gatekeeper/policy.py:156-159` |

### Special-purpose keys

| Key | Type | Default | Applies to | Description | Source |
|---|---|---|---|---|---|
| `max_recipients` | `integer` | route default | Request | Reserved for future Gmail send-route recipient limiting. | `gatekeeper/policy.py` |
| `max_file_size_mb` | `float` | `25` | Request | Maximum upload size for multipart uploads. | `gatekeeper/api/proxy.py:278` |
| `max_attachment_size_mb` | `float` | — | Request | Reserved for future Gmail attachment limiting. | `gatekeeper/policy.py` |
| `require_body` | `boolean` | `false` | Request | Reserved for future body-presence enforcement. | `gatekeeper/policy.py` |

## 3. Application Order

For every request the pipeline is:

1. **Policy check** — allow/deny (`PolicyEngine.check_route`, `gatekeeper/policy.py:33-87`).
2. **Request transforms** in this order:
   1. Cap `max_results`/`pageSize`.
   2. Filter `labelIds` to `allowed_labels`.
   3. Remove `exclude_labels` from `labelIds`.
   4. Append `query_filter` to `q`.
3. **Google API call** with transformed parameters.
4. **Response filters** in this order:
   1. Strip `blocked_fields`.
   2. Cap arrays per `max_items`.
5. **Audit log** write.
6. **Return** the filtered response.

Sources: `gatekeeper/api/proxy.py:75-146` (policy check + transforms + Google call), `gatekeeper/api/proxy.py:384-402` (response filter).

## 4. Combining Transforms

Example: "Read-only, SPAM-filtered Gmail inbox with a 50-result cap."

Policy JSON:

```json
{
  "max_results": 50,
  "allowed_labels": ["INBOX"],
  "exclude_labels": ["SPAM", "TRASH"],
  "query_filter": "in:inbox",
  "blocked_fields": ["internalLabels"]
}
```

What happens to a `gmail__messages_list` call with `{"max_results": 100, "label_ids": ["INBOX", "SPAM"]}`:

1. `max_results` is capped to `50`.
2. `labelIds` is filtered to `["INBOX"]` (`SPAM` is removed by `exclude_labels` and was not in `allowed_labels`).
3. `q` becomes `in:inbox`.
4. Google API is called.
5. `internalLabels` is stripped from the response.

## 5. Per-Route vs Global

- **Per-route policies** — stored in `route_policies` and applied per `(module, route_id)`.
- **Global rate limit** — `GATEKEEPER_RATE_LIMIT_PER_MINUTE` (default `120`), applied per API key across all routes.
- **API-key permissions** — the `permissions` column on `api_keys` controls which modules a key may use. It is orthogonal to per-route policy transforms.

## 6. Validation

There is no JSON-schema validation for `policy_config` today. Malformed JSON is logged and treated as empty config:

```python
# gatekeeper/policy.py:81-85
try:
    config = json.loads(policy.policy_config) if policy.policy_config else {}
except json.JSONDecodeError:
    logger.warning(f"Invalid JSON in policy config for {route}")
    config = {}
```

Future improvement: a `--validate-policy` CLI subcommand could catch malformed configs before they are saved.

## 7. Common Recipes

### Read-only with a 50-result cap

```json
{"max_results": 50}
```

### Filter Gmail SPAM and TRASH

```json
{"exclude_labels": ["SPAM", "TRASH"]}
```

### Block the `internalLabels` field

```json
{"blocked_fields": ["internalLabels"]}
```

### Force `q=in:inbox` on Gmail list routes

```json
{"query_filter": "in:inbox"}
```

### Disable write routes by default for a new module

Set `enabled_by_default=False` on each write `RouteDef` in the module source, or use the admin UI / `gatekeeper init` seeding to create policies with `enabled=false` for those routes. See [MODULE_DEVELOPMENT.md](MODULE_DEVELOPMENT.md) § Common Pitfalls.

## 8. How to Verify

After editing a policy, run the existing test suite:

```bash
uv run pytest tests/test_policy.py -v
```

No server restart is required for policy changes to take effect — `list_tools` and `call_tool` both query the policy table on every call.
