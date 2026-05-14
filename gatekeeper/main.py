"""FastAPI application assembly, lifespan, and CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from gatekeeper.config import settings
from gatekeeper.db import async_session, init_db
from gatekeeper.models import ApiKey, RoutePolicy

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    # Startup
    logger.info("Gatekeeper starting up...")
    await init_db()
    logger.info("Database initialized")

    # Seed default route policies for enabled modules
    await seed_default_policies()

    # Generate default API key if none exist
    await ensure_default_key()

    gv = __import__("gatekeeper").__version__
    logger.info(f"Gatekeeper v{gv} ready on {settings.host}:{settings.port}")

    yield

    # Shutdown
    logger.info("Gatekeeper shutting down...")


async def seed_default_policies():
    """Seed default RoutePolicy rows for all enabled module routes."""

    enabled = []
    if settings.drive_enabled:
        enabled.append("drive")
    if settings.gmail_enabled:
        enabled.append("gmail")
    if settings.calendar_enabled:
        enabled.append("calendar")

    # Also load modules even if not explicitly enabled so policies exist
    # This allows toggling via admin UI later
    all_modules = ["drive", "gmail", "calendar"]
    from gatekeeper.modules import load_module

    for name in all_modules:
        mod = load_module(name)
        if mod is None:
            continue

        for route in mod.get_routes():
            # Check if policy already exists
            async with async_session() as session:
                result = await session.execute(
                    select(RoutePolicy).where(
                        RoutePolicy.module == name,
                        RoutePolicy.route == route.route_id,
                    )
                )
                if result.scalar_one_or_none() is None:
                    # Seed with default
                    defaults = mod.get_default_policies().get(route.route_id, {})
                    policy_config = defaults.get("config", route.default_policy)
                    policy = RoutePolicy(
                        module=name,
                        route=route.route_id,
                        enabled=defaults.get("enabled", route.enabled_by_default),
                        policy_config=json.dumps(policy_config),
                        description=route.description,
                    )
                    session.add(policy)
                    await session.commit()
                    logger.debug(f"Seeded policy: {name}.{route.route_id}")


async def ensure_default_key():
    """Generate a default admin API key if none exist."""
    async with async_session() as session:
        result = await session.execute(select(ApiKey))
        existing = result.scalars().all()

        if not existing:
            raw, hash_val, prefix = ApiKey.generate_key()
            key = ApiKey(
                name="default-admin",
                key_hash=hash_val,
                key_prefix=prefix,
                permissions="*",
            )
            session.add(key)
            await session.commit()
            print(f"\n{'=' * 60}")
            print("🔑 Default API Key generated (save this — it won't be shown again):")
            print(f"   {raw}")
            print(f"{'=' * 60}\n")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from gatekeeper.api.router import create_api_router

    app = FastAPI(
        title="Gatekeeper",
        description="Policy gateway for Google Workspace APIs with MCP server integration",
        version=__import__("gatekeeper").__version__,
        lifespan=lifespan,
    )

    # CORS middleware — validate config (no wildcard origins with credentials)
    if "*" in settings.cors_origins:
        import warnings

        warnings.warn(
            "GATEKEEPER_CORS_ORIGINS contains '*' which is insecure with credentials. "
            "Specify exact origins instead.",
            stacklevel=2,
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["X-Gatekeeper-API-Key", "Authorization", "Content-Type"],
    )

    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok", "version": __import__("gatekeeper").__version__}

    # API routes
    api_router = create_api_router()
    app.include_router(api_router)

    # Admin routes
    from gatekeeper.admin.routes import create_admin_router
    from gatekeeper.admin.ui import mount_ui

    admin_router = create_admin_router()
    app.include_router(admin_router)
    mount_ui(app)

    # MCP server - graceful fallback if mcp package not available
    if settings.mcp_enabled:
        try:
            from gatekeeper.mcp_server import mount_mcp_server

            mount_mcp_server(app)
        except ImportError:
            logger.warning("MCP package not installed. Install with: pip install mcp")
        except Exception as e:
            logger.warning(f"Failed to mount MCP server: {e}")

    return app


def cli():
    """CLI entry point for gatekeeper."""
    parser = argparse.ArgumentParser(
        prog="gatekeeper",
        description="Policy gateway for Google Workspace APIs",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the Gatekeeper server")
    serve_parser.add_argument("--host", default=None, help="Host to bind to")
    serve_parser.add_argument("--port", type=int, default=None, help="Port to bind to")

    # init
    subparsers.add_parser("init", help="Initialize the database and seed default policies")

    # auth
    auth_parser = subparsers.add_parser("auth", help="Run the Google OAuth authorization flow")
    auth_parser.add_argument(
        "--flow",
        choices=["desktop", "device"],
        default="desktop",
        help=(
            "Auth flow: 'desktop' (opens browser locally, recommended)"
            " or 'device' (link + code for headless/remote). Default: desktop"
        ),
    )

    # key
    key_parser = subparsers.add_parser("key", help="Manage API keys")
    key_subparsers = key_parser.add_subparsers(dest="key_command", help="Key commands")

    key_create = key_subparsers.add_parser("create", help="Create a new API key")
    key_create.add_argument("--name", required=True, help="Name for the key")
    key_create.add_argument(
        "--permissions",
        default="*",
        help="Comma-separated module permissions (default: *)",
    )

    _ = key_subparsers.add_parser("list", help="List API keys")

    key_revoke = key_subparsers.add_parser("revoke", help="Revoke an API key")
    key_revoke.add_argument("--prefix", required=True, help="Key prefix to revoke")

    # status
    subparsers.add_parser("status", help="Show configuration status")

    # service
    service_parser = subparsers.add_parser(
        "service", help="Manage Gatekeeper as a systemd user service"
    )
    service_subparsers = service_parser.add_subparsers(
        dest="service_command", help="Service commands"
    )
    service_subparsers.add_parser("install", help="Install and enable the systemd user service")
    service_subparsers.add_parser("uninstall", help="Stop, disable, and remove the systemd user service")
    service_subparsers.add_parser("enable", help="Enable and start the service")
    service_subparsers.add_parser("disable", help="Stop and disable the service")
    service_subparsers.add_parser("status", help="Show service status")
    logs_parser = service_subparsers.add_parser("logs", help="Show service logs")
    logs_parser.add_argument("-f", "--follow", action="store_true", help="Follow log output")

    args = parser.parse_args()

    if args.command == "serve":
        host = args.host or settings.host
        port = args.port or settings.port
        uvicorn.run(
            "gatekeeper.main:create_app",
            host=host,
            port=port,
            factory=True,
            reload=settings.debug,
        )

    elif args.command == "init":
        asyncio.run(_cli_init())

    elif args.command == "auth":
        asyncio.run(_cli_auth(args.flow))

    elif args.command == "key":
        if args.key_command == "create":
            asyncio.run(_cli_key_create(args.name, args.permissions))
        elif args.key_command == "list":
            asyncio.run(_cli_key_list())
        elif args.key_command == "revoke":
            asyncio.run(_cli_key_revoke(args.prefix))
        else:
            key_parser.print_help()

    elif args.command == "status":
        _cli_status()

    elif args.command == "service":
        from gatekeeper.service import (
            disable_service,
            enable_service,
            install_service,
            service_logs,
            service_status,
            uninstall_service,
        )

        handlers = {
            "install": lambda: install_service(),
            "uninstall": lambda: uninstall_service(),
            "enable": lambda: enable_service(),
            "disable": lambda: disable_service(),
            "status": lambda: service_status(),
            "logs": lambda: service_logs(follow=args.follow),
        }
        handler = handlers.get(args.service_command)
        if handler:
            result = handler()
            if result is False:
                sys.exit(1)
        else:
            service_parser.print_help()

    else:
        parser.print_help()


async def _cli_init():
    """Initialize the database, seed policies, and create default API key."""
    await init_db()
    await seed_default_policies()
    await ensure_default_key()
    print("✅ Database initialized and default policies seeded.")


async def _cli_auth(flow: str = "desktop"):
    """Run the Google OAuth authorization flow."""
    from gatekeeper.google_client import credential_manager

    if flow == "desktop":
        print("🌐 Opening browser for Google OAuth authorization...")
        print("   A browser window will open. Authorize Gatekeeper to access your data.")
    else:
        print("🔐 Starting Google authorization flow (headless/remote)...")
        print("   You'll open a URL and enter a code on any device.")
        print("   (Use 'gatekeeper auth --flow desktop' for browser-based auth)")
    print("   Scopes will be requested based on enabled modules.")
    print(
        f"   Drive: {settings.drive_enabled},"
        f" Gmail: {settings.gmail_enabled},"
        f" Calendar: {settings.calendar_enabled}"
    )

    creds = credential_manager.start_auth_flow(flow=flow)
    if creds:
        print("✅ Authorization successful! Credentials saved.")
        print(f"   Scopes: {creds.scopes}")
    else:
        print("❌ Authorization failed.")
        sys.exit(1)


async def _cli_key_create(name: str, permissions: str):
    """Create a new API key."""
    async with async_session() as session:
        raw, hash_val, prefix = ApiKey.generate_key()
        key = ApiKey(
            name=name,
            key_hash=hash_val,
            key_prefix=prefix,
            permissions=permissions,
        )
        session.add(key)
        await session.commit()

        print(f"\n{'=' * 60}")
        print(f"🔑 API Key created: {name}")
        print(f"   Key:     {raw}")
        print(f"   Prefix:  {prefix}")
        print(f"   Permissions: {permissions}")
        print(f"{'=' * 60}")
        print("⚠️  Save the key now — it won't be shown again!\n")


async def _cli_key_list():
    """List API keys."""
    async with async_session() as session:
        result = await session.execute(select(ApiKey))
        keys = result.scalars().all()

        if not keys:
            print("No API keys found. Run 'gatekeeper init' to create a default key.")
            return

        print(f"\n{'Prefix':<15} {'Name':<20} {'Active':<8} {'Permissions':<20} {'Last Used'}")
        print("-" * 85)
        for key in keys:
            last_used = str(key.last_used_at) if key.last_used_at else "Never"
            active = "✅" if key.is_active else "❌"
            print(
                f"{key.key_prefix:<15} {key.name:<20} {active:<8} {key.permissions:<20} {last_used}"
            )
        print()


async def _cli_key_revoke(prefix: str):
    """Revoke an API key by prefix."""
    async with async_session() as session:
        result = await session.execute(select(ApiKey).where(ApiKey.key_prefix == prefix))
        key = result.scalar_one_or_none()

        if key:
            key.is_active = False
            await session.commit()
            print(f"✅ Key {prefix} ({key.name}) revoked.")
        else:
            print(f"❌ Key with prefix {prefix} not found.")


def _cli_status():
    """Show configuration status."""
    from gatekeeper.service import _is_systemd_available, _unit_path

    print(f"\n{'=' * 50}")
    print("  Gatekeeper Status")
    print(f"{'=' * 50}")
    print(f"  Version:      {__import__('gatekeeper').__version__}")
    print(f"  Host:         {settings.host}")
    print(f"  Port:         {settings.port}")
    print(f"  Debug:        {settings.debug}")
    print(f"  Database:     {settings.database_url}")
    print(f"  MCP Enabled:  {settings.mcp_enabled}")
    print("  Modules:")
    print(f"    Drive:      {'✅' if settings.drive_enabled else '❌'}")
    print(f"    Gmail:      {'✅' if settings.gmail_enabled else '❌'}")
    print(f"    Calendar:   {'✅' if settings.calendar_enabled else '❌'}")
    oauth_status = "✅ Configured" if settings.google_client_id else "❌ Not configured"
    print(f"  Google OAuth: {oauth_status}")
    print(f"  Admin User:   {settings.admin_username}")
    # Service status
    if _is_systemd_available():
        unit = _unit_path()
        if unit.exists():
            print(f"  Service:      ✅ Installed ({unit})")
        else:
            print("  Service:      ❌ Not installed (run: gatekeeper service install)")
    else:
        print("  Service:      — systemd not available")
    print(f"{'=' * 50}\n")
