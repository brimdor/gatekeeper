# `drive.files.update` now enabled by default

Starting with this release, the `drive.files.update` route is seeded with `enabled=True` by default. This makes the basic file-update verb available as soon as the Drive module is enabled, which is the expected behavior for most deployments.

## Impact

- **Fresh installations:** `drive.files.update` is automatically enabled on first startup.
- **Existing installations:** If your database already contains a `RoutePolicy` row for `drive.files.update` that was seeded with `enabled=False`, that row is preserved. You must explicitly enable it, or delete the row and restart Gatekeeper so `seed_default_policies()` recreates it with the new default.

## Migration steps

Option 1 — enable via the admin API or CLI (preferred):

```bash
gatekeeper policy enable drive.files.update
```

Option 2 — delete the existing policy row so it is re-seeded on startup:

```bash
gatekeeper policy delete drive.files.update
# then restart Gatekeeper
gatekeeper service restart
```

If you use the SQLite database directly, the equivalent SQL is:

```sql
DELETE FROM route_policies WHERE module = 'drive' AND route = 'drive.files.update';
```

After deletion, restart Gatekeeper and the route will be re-seeded as enabled.
