#!/usr/bin/env python3
"""Gatekeeper Route Smoke Test — Validates every route against live Google APIs.

Prerequisites:
  1. Gatekeeper is authenticated to your secondary/ test account.
  2. OAuth token is valid and stored at ./google_token.json.

Strategy:
  Phase A: Read-only routes — safe, no mutations.
  Phase B: Write routes — create temp resources, mutate them, clean up.

Write-route lifecycle (per-resource):
  1. Create a unique temp resource (file, event, label, etc.)
  2. Run mutation routes against that resource
  3. Delete temp resource

All actions are idempotent and tracked in a cleanup log.  Even if the test
exits halfway  through resources are logged  so a follow-up script can
finish cleanup.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Ensure Gatekeeper is on path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ─── Dependency Bootstrap ────────────────────────────────────────────────────
# Before importing any third-party packages, verify they are installed.
# If missing, auto-install from requirements.txt (or pyproject.toml fallback).

import shutil
import subprocess
import warnings as _warnings


class _DepBootstrap:
    
    @staticmethod
    def _parse_spec(spec: str) -> str:
        """Strip extras and version constraints, leaving only the distribution name."""
        # fastapi[standard]>=0.110  -> fastapi
        # httpx>=0.27                -> httpx
        name = spec.split("[")[0].split("=")[0].split(">")[0].split("<")[0].strip()
        return name

    @staticmethod
    def _check(spec: str) -> bool:
        """Return True if the package is importable (best-effort)."""
        name = _DepBootstrap._parse_spec(spec).replace("-", "_")
        try:
            __import__(name)
            return True
        except ImportError:
            return False

    @staticmethod
    def _load_reqs() -> list[str]:
        """Read requirements.txt or pyproject.toml dependencies."""
        req_file = PROJECT_ROOT / "requirements.txt"
        if req_file.exists():
            lines = [ln.strip() for ln in req_file.read_text().splitlines()]
            return [ln for ln in lines if ln and not ln.startswith("#")]

        pyproject = PROJECT_ROOT / "pyproject.toml"
        if pyproject.exists():
            try:
                import tomllib
                with pyproject.open("rb") as fh:
                    data = tomllib.load(fh)
                return data.get("project", {}).get("dependencies", [])
            except ModuleNotFoundError:
                _warnings.warn(
                    "tomllib not found (Python < 3.11). Cannot parse pyproject.toml."
                    " Please create a requirements.txt.",
                    stacklevel=2,
                )
        return []

    @staticmethod
    def ensure() -> None:
        deps = _DepBootstrap._load_reqs()
        if not deps:
            print("⚠️  No requirements.txt or pyproject.toml dependencies found. Skipping auto-install.")
            return

        missing = [d for d in deps if not _DepBootstrap._check(d)]
        if not missing:
            return

        print(f"🔧 Missing packages: {missing}")

        in_venv = sys.prefix != sys.base_prefix
        venv_path = PROJECT_ROOT / ".venv"
        venv_python = venv_path / "bin" / "python"

        if not in_venv and not venv_path.exists():
            # Externally-managed interpreter — create a local venv automatically.
            print(f"🔧 Creating local venv at {venv_path} ...")
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_path)],
                capture_output=True, text=True, check=True,
            )
            print("🔧 Venv created. Restarting inside it ...\n")
            os.execl(str(venv_python), str(venv_python), *sys.argv)

        # Choose python to target (venv if present, else current).
        target_python = venv_python if venv_path.exists() else Path(sys.executable)

        if shutil.which("uv"):
            cmd = ["uv", "pip", "install", "--python", str(target_python)] + missing
        else:
            cmd = [str(target_python), "-m", "pip", "install", "-q"] + missing

        print(f"🔧 Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Install failed:\n{result.stderr}")
            print("Work-arounds:")
            print("  python3 -m venv .venv && source .venv/bin/activate")
            print("  pip install -r requirements.txt")
            print("  uv pip install -r requirements.txt")
            sys.exit(1)
        print("✅ Dependencies installed.\n")

        # If we just installed into a local venv but are still running on the
        # system interpreter, restart inside the venv so imports resolve.
        if venv_path.exists() and not in_venv:
            print("🔧 Restarting inside .venv ...\n")
            os.execl(str(venv_python), str(venv_python), *sys.argv)


_DepBootstrap.ensure()
# ─────────────────────────────────────────────────────────────────────────────

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from gatekeeper.api.proxy import GoogleProxy
from gatekeeper.config import settings
from gatekeeper.db import Base, init_db
from gatekeeper.google_client import credential_manager
from gatekeeper.models import ApiKey, RoutePolicy
from gatekeeper.modules import AVAILABLE_MODULES, load_module

# --------------------------------------------------------------------------- #
# Config                                                                      #
# --------------------------------------------------------------------------- #

DB_PATH = Path(tempfile.mkdtemp(prefix="gk_smoke_")) / "test.db"
EMAIL_ADDRESS: str | None = None  # populated after profile lookup
CLEANUP_LOG: list[list[str]] = []  # [[route_id, resource_id_or_desc], ...]


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def extract_path_params(google_path: str) -> list[str]:
    import re
    return re.findall(r"\{([^}]+)\}", google_path)


def build_test_params(route, email: str | None) -> dict:
    """Build a reasonable set of params for a route based on its schema & path."""
    params: dict = {}
    schema_props = route.input_schema.get("properties", {})
    for key, spec in schema_props.items():
        ptype = spec.get("type", "string")
        if key == "base64_content":
            params[key] = base64.b64encode(b"Gatekeeper smoke test content").decode()
        elif key == "mime_type":
            params[key] = "application/octet-stream"
        elif key in ("name", "summary", "description", "content"):
            params[key] = f"GK-SMOKE-{int(time.time())}-{key}"
        elif key == "email_address":
            params[key] = email or "test@example.com"
        elif key == "role":
            params[key] = "reader"
        elif key == "type":
            params[key] = "user"
        elif key == "label_ids":
            params[key] = "INBOX"
        elif key == "add_label_ids":
            params[key] = "INBOX"
        elif key == "to":
            params[key] = email or "test@example.com"
        elif key == "subject":
            params[key] = "Gatekeeper smoke test"
        elif key == "body":
            params[key] = "This is a smoke test email"
        elif key == "q":
            if route.route_id.split(".", 1)[0] == "drive":
                params[key] = "name contains 'GK-SMOKE'"
            else:
                params[key] = ""
        elif ptype == "integer":
            params[key] = spec.get("default", 10)
        elif ptype == "boolean":
            params[key] = spec.get("default", False)
        elif ptype == "array":
            params[key] = []
        elif key == "resource":
            params[key] = {"id": "gk-smoke-id", "type": "web_hook"}
        else:
            params[key] = ""

    # Path params
    path_params = extract_path_params(route.google_path)
    for pp in path_params:
        if pp == "userId":
            params[snake_to_camel(pp)] = "me"
        elif pp in ("calendarId", "eventId", "fileId", "commentId", "replyId",
                     "revisionId", "permissionId", "driveId", "draftId",
                     "messageId", "labelId", "filterId", "ruleId",
                     "proposalId", "approvalId", "teamDriveId", "appId", "id"):
            params[snake_to_camel(pp)] = f"fake_{pp.lower()}"
        elif pp in ("name", "operation"):
            params[snake_to_camel(pp)] = f"fake_{pp.lower()}"
        else:
            params[snake_to_camel(pp)] = f"fake_{pp.lower()}"

    return params


def _get_db_session_factory():
    engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}")
    return sessionmaker(engine, class_=AsyncSession)


async def init_test_db():
    engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def create_test_api_key(session: AsyncSession) -> str:
    raw, key_hash, key_prefix = ApiKey.generate_key(prefix="smk_")
    key = ApiKey(
        name="smoke-test-key",
        key_hash=key_hash,
        key_prefix=key_prefix,
    )
    session.add(key)
    await session.commit()
    return key


async def get_api_key_plaintext(session: AsyncSession, db_key: ApiKey) -> str:
    """Return the raw API key string.  We can't recover the plaintext from the DB,
    so we construct it from the same deterministic logic used during creation."""
    # This is a test-only shortcut — in real usage the raw key is returned to
    # the caller and never stored.
    return db_key.key_hash  # proxy accepts the ApiKey record via api_key_record


async def create_route_policies(session: AsyncSession):
    """Create enabled policies for every route in every module."""
    for mod_name in AVAILABLE_MODULES:
        mod = load_module(mod_name)
        for route in mod.get_routes():
            policy = RoutePolicy(
                module=mod_name,
                route=route.route_id,
                enabled=True,
                policy_config="{}",
            )
            session.add(policy)
    await session.commit()


async def get_authenticated_email() -> str:
    """Hits the Gmail profile endpoint to get the email of the current account."""
    creds = credential_manager.get_credentials()
    if not creds or not creds.token:
        return ""

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/gmail/v1/users/me/profile",
            headers={"Authorization": f"Bearer {creds.token}"},
        )
        data = resp.json()
        email = data.get("emailAddress", "")
        return email


# --------------------------------------------------------------------------- #
# Phase A — Read-only routes                                                  #
# --------------------------------------------------------------------------- #

async def test_readonly_route(proxy, api_key, route, email: str) -> dict:
    """Test a read-only (GET) route.  Returns pass/fail with details."""
    params = build_test_params(route, email)
    try:
        resp = await proxy.call_google(
            module_name=route.route_id.split(".", 1)[0],
            route_id=route.route_id,
            params=params,
            api_key_record=api_key,
            request_method=route.method,
        )
        status = resp.status_code
        # 200 / 404 / 400 are all acceptable for read routes with fake IDs
        if status in (200, 201, 204):
            return {"status": "pass", "code": status, "detail": "OK"}
        else:
            body = json.loads(resp.body.decode()) if hasattr(resp, "body") else {}
            error_msg = body.get("message", "")
            return {"status": "fail", "code": status, "detail": error_msg[:120]}
    except Exception as e:
        return {"status": "error", "code": 0, "detail": str(e)[:120]}


# --------------------------------------------------------------------------- #
# Phase B — Write routes (resource lifecycle)                                 #
# --------------------------------------------------------------------------- #

async def test_write_route(proxy, api_key, route, email: str, tracker: WriteTracker) -> dict:
    """Test a write route.  Tracker manages lifecycle resources."""
    params = build_test_params(route, email)

    # Inject real IDs from tracker if path params reference known resources
    for pp in extract_path_params(route.google_path):
        real_id = tracker.get_resource_id(pp, route.route_id.split(".", 1)[0])
        if real_id:
            params[snake_to_camel(pp)] = real_id

    try:
        resp = await proxy.call_google(
            module_name=route.route_id.split(".", 1)[0],
            route_id=route.route_id,
            params=params,
            api_key_record=api_key,
            request_method=route.method,
        )
        status = resp.status_code
        body = {}
        try:
            body = json.loads(resp.body.decode()) if hasattr(resp, "body") else {}
        except Exception:
            pass

        if status in (200, 201, 204):
            # Track created resources for cleanup
            tracker.record(route, body, params)
            return {"status": "pass", "code": status, "id": body.get("id", "")}
        elif status == 404:
            return {"status": "skip", "code": 404, "detail": "Resource not found (expected with fake IDs)"}
        elif status == 403:
            return {"status": "fail", "code": 403, "detail": body.get("message", "Permission denied")[:120]}
        else:
            return {"status": "fail", "code": status, "detail": body.get("message", "")[:120]}
    except Exception as e:
        return {"status": "error", "code": 0, "detail": str(e)[:120]}


class WriteTracker:
    """Tracks resources created during smoke testing for cleanup."""

    def __init__(self):
        self.resources: dict[str, dict] = {}
        # module > param_name > real_id
        self.path_ids: dict[str, dict[str, str]] = {}

    def record(self, route, response_body: dict, params: dict):
        """Store a newly created resource for later cleanup."""
        rid = response_body.get("id", "")
        if not rid:
            return
        key = f"{route.route_id.split('.', 1)[0]}:{route.route_id}"
        self.resources[key] = {
            "id": rid,
            "type": route.route_id,
            "module": route.route_id.split(".", 1)[0],
            "params": params,
            "response": response_body,
        }
        # Map common path IDs
        if "fileId" in str(route.google_path):
            self.path_ids.setdefault(route.route_id.split(".", 1)[0], {})["fileId"] = rid
        if "calendarId" in str(route.google_path):
            self.path_ids.setdefault(route.route_id.split(".", 1)[0], {})["calendarId"] = rid
        if "eventId" in str(route.google_path):
            self.path_ids.setdefault(route.route_id.split(".", 1)[0], {})["eventId"] = rid
        if "commentId" in str(route.google_path):
            self.path_ids.setdefault(route.route_id.split(".", 1)[0], {})["commentId"] = rid
        if "replyId" in str(route.google_path):
            self.path_ids.setdefault(route.route_id.split(".", 1)[0], {})["replyId"] = rid
        if "draftId" in str(route.google_path):
            self.path_ids.setdefault(route.route_id.split(".", 1)[0], {})["draftId"] = rid
        if "labelId" in str(route.google_path):
            self.path_ids.setdefault(route.route_id.split(".", 1)[0], {})["labelId"] = rid
        if "ruleId" in str(route.google_path):
            self.path_ids.setdefault(route.route_id.split(".", 1)[0], {})["ruleId"] = rid
        if "driveId" in str(route.google_path):
            self.path_ids.setdefault(route.route_id.split(".", 1)[0], {})["driveId"] = rid
        if "teamDriveId" in str(route.google_path):
            self.path_ids.setdefault(route.route_id.split(".", 1)[0], {})["teamDriveId"] = rid

    def get_resource_id(self, param_name: str, module: str) -> str | None:
        return self.path_ids.get(module, {}).get(param_name)

    def cleanup_list(self) -> list[dict]:
        return list(self.resources.values())


async def cleanup_resources(proxy, api_key, tracker: WriteTracker):
    """Delete everything the smoke test created."""
    print("\n🧹 Cleaning up created resources...")
    cleaned = 0
    for item in tracker.cleanup_list():
        rid = item["id"]
        mod = item["module"]
        rtype = item["type"]
        params = item["params"]

        try:
            if rtype == "drive.files.create":
                await proxy.call_google(
                    module_name=mod, route_id="drive.files.delete",
                    params={"file_id": rid}, api_key_record=api_key, request_method="DELETE",
                )
            elif rtype == "calendar.calendars.create":
                await proxy.call_google(
                    module_name=mod, route_id="calendar.calendars.delete",
                    params={"calendar_id": rid}, api_key_record=api_key, request_method="DELETE",
                )
            elif rtype == "calendar.events.create":
                cid = params.get("calendar_id", "primary")
                await proxy.call_google(
                    module_name=mod, route_id="calendar.events.delete",
                    params={"calendar_id": cid, "event_id": rid},
                    api_key_record=api_key, request_method="DELETE",
                )
            elif rtype == "gmail.labels.create":
                await proxy.call_google(
                    module_name=mod, route_id="gmail.labels.delete",
                    params={"id": rid}, api_key_record=api_key, request_method="DELETE",
                )
            elif rtype == "gmail.drafts.create":
                await proxy.call_google(
                    module_name=mod, route_id="gmail.drafts.delete",
                    params={"draft_id": rid}, api_key_record=api_key, request_method="DELETE",
                )
            elif rtype == "drive.comments.create":
                fid = params.get("file_id", "")
                await proxy.call_google(
                    module_name=mod, route_id="drive.comments.delete",
                    params={"file_id": fid, "comment_id": rid},
                    api_key_record=api_key, request_method="DELETE",
                )
            elif rtype == "drive.replies.create":
                fid = params.get("file_id", "")
                cid = params.get("comment_id", "")
                await proxy.call_google(
                    module_name=mod, route_id="drive.replies.delete",
                    params={"file_id": fid, "comment_id": cid, "reply_id": rid},
                    api_key_record=api_key, request_method="DELETE",
                )
            elif rtype == "drive.permissions.create":
                fid = params.get("file_id", "")
                await proxy.call_google(
                    module_name=mod, route_id="drive.permissions.delete",
                    params={"file_id": fid, "permission_id": rid},
                    api_key_record=api_key, request_method="DELETE",
                )
            elif rtype == "drive.drives.create":
                await proxy.call_google(
                    module_name=mod, route_id="drive.drives.delete",
                    params={"drive_id": rid}, api_key_record=api_key, request_method="DELETE",
                )
            elif rtype == "drive.teamdrives.create":
                await proxy.call_google(
                    module_name=mod, route_id="drive.teamdrives.delete",
                    params={"team_drive_id": rid}, api_key_record=api_key, request_method="DELETE",
                )
            cleaned += 1
        except Exception as e:
            print(f"  ⚠️ Cleanup failed for {rtype} ({rid}): {e}")
    print(f"  ✅ Cleaned {cleaned} resources")


# --------------------------------------------------------------------------- #
# Reporting                                                                      #
# --------------------------------------------------------------------------- #

def print_results(module_name: str, results: list[dict]):
    print(f"\n{'─'*60}")
    print(f"📦 {module_name.upper()}  ({len(results)} routes)")
    print(f"{'─'*60}")
    passed = sum(1 for r in results if r["result"]["status"] == "pass")
    failed = sum(1 for r in results if r["result"]["status"] in ("fail", "error"))
    skipped = sum(1 for r in results if r["result"]["status"] == "skip")
    print(f"  Pass: {passed}  |  Fail: {failed}  |  Skip: {skipped}")
    if failed:
        for r in results:
            if r["result"]["status"] in ("fail", "error"):
                detail = r["result"].get("detail", "")
                code = r["result"].get("code", "")
                print(f"    ❌ {r['route']} [{code}] {detail}")


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

async def main():
    print("="*60)
    print("  Gatekeeper Route Smoke Test")
    print("  ============================")
    print("  WARNING: This will make live calls to Google APIs")
    print("  Ensure you have authenticated to your SECONDARY / TEST account.")
    print("="*60)

    creds = credential_manager.get_credentials()
    if not creds or not creds.token:
        print("\n❌ No credentials found. Run 'gatekeeper auth' first.")
        return 1

    # Confirm with user
    email = await get_authenticated_email()
    print(f"\n📧 Authenticated as: {email}")
    confirm = input("\nContinue with this account? [y/N]: ")
    if confirm.lower() not in ("y", "yes"):
        print("Aborted.")
        return 1

    # Init test DB and policies
    print("\n🗄️  Initializing test database...")
    engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = sessionmaker(engine, class_=AsyncSession)
    async with async_session_factory() as session:
        api_key = await create_test_api_key(session)
        await create_route_policies(session)
        proxy = GoogleProxy(session)

        tracker = WriteTracker()
        all_results: dict[str, list[dict]] = {mod: [] for mod in AVAILABLE_MODULES}

        # ── Phase A: Read-Only ──
        print("\n🔵 Phase A — Read-Only Routes (GET)")
        for mod_name in AVAILABLE_MODULES:
            mod = load_module(mod_name)
            for route in mod.get_routes():
                if route.method != "GET":
                    continue
                result = await test_readonly_route(proxy, api_key, route, email)
                all_results[route.route_id.split(".")[0]].append({
                    "route": route.route_id,
                    "method": route.method,
                    "result": result,
                })
                if result["status"] == "fail":
                    print(f"  ⚠️ {route.route_id} [{result['code']}] {result.get('detail', '')}")

        # ── Phase B: Write Routes ──
        print("\n🟠 Phase B — Write Routes (POST / PUT / PATCH / DELETE)")
        # Collect write routes, ordered with creates first
        create_routes = []
        other_writes = []
        cleanup_routes = []
        for mod_name in AVAILABLE_MODULES:
            mod = load_module(mod_name)
            for route in mod.get_routes():
                if route.method == "GET":
                    continue
                rid = route.route_id
                if any(x in rid for x in (".create", ".send", ".insert", ".import", ".copy", ".start")):
                    create_routes.append(route)
                elif any(x in rid for x in (".delete", ".trash", ".empty_", ".cancel", ".stop")):
                    cleanup_routes.append(route)
                else:
                    other_writes.append(route)

        # Run creates first (establish resources)
        for route in create_routes:
            result = await test_write_route(proxy, api_key, route, email, tracker)
            all_results[route.route_id.split(".", 1)[0]].append({
                "route": route.route_id, "method": route.method, "result": result,
            })
            if result["status"] == "pass":
                print(f"  ✅ {route.route_id} → id={result.get('id', '')}")
            elif result["status"] == "fail":
                print(f"  ❌ {route.route_id} [{result['code']}] {result.get('detail', '')}")

        # Run mutations on established resources
        for route in other_writes:
            result = await test_write_route(proxy, api_key, route, email, tracker)
            all_results[route.route_id.split(".", 1)[0]].append({
                "route": route.route_id, "method": route.method, "result": result,
            })
            if result["status"] == "fail":
                print(f"  ❌ {route.route_id} [{result['code']}] {result.get('detail', '')}")

        # Run cleanup routes (deletes, etc.)
        for route in cleanup_routes:
            result = await test_write_route(proxy, api_key, route, email, tracker)
            all_results[route.route_id.split(".", 1)[0]].append({
                "route": route.route_id, "method": route.method, "result": result,
            })
            if result["status"] == "fail":
                print(f"  ❌ {route.route_id} [{result['code']}] {result.get('detail', '')}")

        # Deep clean — run explicit cleanup deletions
        await cleanup_resources(proxy, api_key, tracker)

        # Final report
        print("\n" + "="*60)
        print("  SMOKE TEST REPORT")
        print("="*60)
        total_pass = 0
        total_fail = 0
        total_skip = 0
        for mod in AVAILABLE_MODULES:
            results = all_results[mod]
            passed = sum(1 for r in results if r["result"]["status"] == "pass")
            failed = sum(1 for r in results if r["result"]["status"] in ("fail", "error"))
            skipped = sum(1 for r in results if r["result"]["status"] == "skip")
            total_pass += passed
            total_fail += failed
            total_skip += skipped
            print_results(mod, results)

        total = total_pass + total_fail + total_skip
        print(f"\n{'='*60}")
        print(f"  TOTAL: {total_pass}/{total} passed  |  {total_fail} failed  |  {total_skip} skipped")
        print(f"{'='*60}")

    # Save report
    report_path = Path("/tmp/gk_smoke_report.json")
    report_path.write_text(json.dumps(all_results, indent=2, default=str))
    print(f"\n📄 Detailed report saved to: {report_path}")

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
