# Gatekeeper Upgrade Guide

**Audience:** Operators upgrading Gatekeeper from one version to the next.  
**See also:** [CHANGELOG.md](../CHANGELOG.md) for release notes.

---

## 1. Conventions

Each Gatekeeper release gets a matching section in this document. Sections appear in reverse chronological order (newest first). A section uses the following subsections only when relevant:

- **Breaking Changes**
- **Database Migrations**
- **Configuration Changes**
- **Manual Steps**

If a release has nothing under a heading, the heading is omitted.

## 2. General Upgrade Procedure

For every upgrade, follow this procedure:

1. **Back up state.**

   ```bash
   cp gatekeeper.db gatekeeper.db.bak
   cp gatekeeper_secrets.json gatekeeper_secrets.json.bak
   ```

2. **Stop the service.**

   ```bash
   gatekeeper service stop
   ```

3. **Update code and dependencies.**

   ```bash
   git pull
   uv pip install -e ".[dev]"
   ```

4. **Run database initialization / migrations.**

   ```bash
   gatekeeper init
   ```

5. **Start the service.**

   ```bash
   gatekeeper service start
   ```

6. **Verify health.**

   ```bash
   gatekeeper status
   curl http://127.0.0.1:8080/health
   ```

7. **Apply any version-specific steps** from the matching section below.

## 3. Version-Specific Notes

### Unreleased

No migration steps yet. See [CHANGELOG.md](../CHANGELOG.md) § Unreleased for the list of documentation changes covered by this release.

### 0.1.0 → 0.2.0

TBD. This section will be populated when version 0.2.0 ships. At that time, check [CHANGELOG.md](../CHANGELOG.md) for the 0.2.0 entry and add the corresponding migration steps here.

### 0.0.x → 0.1.0

No tracked migration steps. Gatekeeper 0.1.0 was the first public beta release. Run `gatekeeper init` after install to seed the default route policies.
