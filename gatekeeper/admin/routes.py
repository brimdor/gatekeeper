"""Admin API endpoints — manage keys, policies, modules, audit logs, and auth."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from gatekeeper.admin.models import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyResponse,
    AuditLogResponse,
    AuthStatus,
    DashboardStats,
    ModuleStatus,
    RoutePolicyResponse,
    RoutePolicyUpdate,
)
from gatekeeper.auth import require_admin
from gatekeeper.config import settings
from gatekeeper.db import async_session
from gatekeeper.google_client import credential_manager
from gatekeeper.models import ApiKey, AuditLog, RoutePolicy

logger = logging.getLogger(__name__)


def create_admin_router() -> APIRouter:
    """Create the admin API router with all management endpoints."""
    router = APIRouter(prefix="/admin/api", tags=["admin"])

    @router.get("/dashboard", response_model=DashboardStats)
    async def dashboard(admin=Depends(require_admin)):
        """Get dashboard statistics."""
        async with async_session() as session:
            total_requests = await session.scalar(select(func.count(AuditLog.id)))
            active_keys = await session.scalar(
                select(func.count(ApiKey.id)).where(ApiKey.is_active == True)  # noqa: E712
            )
            enabled_routes = await session.scalar(
                select(func.count(RoutePolicy.id)).where(RoutePolicy.enabled == True)  # noqa: E712
            )

        auth_status = credential_manager.get_status()

        return DashboardStats(
            total_requests=total_requests or 0,
            active_keys=active_keys or 0,
            enabled_routes=enabled_routes or 0,
            auth_connected=auth_status.get("connected", False),
        )

    @router.get("/keys", response_model=list[ApiKeyResponse])
    async def list_keys(admin=Depends(require_admin)):
        """List all API keys."""
        async with async_session() as session:
            result = await session.execute(select(ApiKey))
            keys = result.scalars().all()
            return [
                ApiKeyResponse(
                    id=k.id,
                    name=k.name,
                    key_prefix=k.key_prefix,
                    is_active=k.is_active,
                    permissions=k.permissions,
                    created_at=k.created_at,
                    last_used_at=k.last_used_at,
                )
                for k in keys
            ]

    @router.post("/keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
    async def create_key(key_data: ApiKeyCreate, admin=Depends(require_admin)):
        """Create a new API key."""
        async with async_session() as session:
            raw, hash_val, prefix = ApiKey.generate_key()
            key = ApiKey(
                name=key_data.name,
                key_hash=hash_val,
                key_prefix=prefix,
                permissions=key_data.permissions,
            )
            session.add(key)
            await session.commit()
            await session.refresh(key)  # Populate the id field
            return ApiKeyCreated(id=key.id, name=key_data.name, key_prefix=prefix, raw_key=raw)

    @router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def revoke_key(key_id: int, admin=Depends(require_admin)):
        """Revoke an API key."""
        async with async_session() as session:
            result = await session.execute(select(ApiKey).where(ApiKey.id == key_id))
            key = result.scalar_one_or_none()
            if not key:
                raise HTTPException(status_code=404, detail="Key not found")
            key.is_active = False
            await session.commit()

    @router.get("/modules", response_model=list[ModuleStatus])
    async def list_modules(admin=Depends(require_admin)):
        """List all modules with their enable status."""
        from gatekeeper.modules import AVAILABLE_MODULES, load_module

        modules = []
        for name in AVAILABLE_MODULES:
            mod = load_module(name)
            if mod:
                # Check if enabled in settings
                enabled = getattr(settings, f"{name}_enabled", False)

                # Count enabled routes
                async with async_session() as session:
                    enabled_count = await session.scalar(
                        select(func.count(RoutePolicy.id))
                        .where(RoutePolicy.module == name)
                        .where(RoutePolicy.enabled == True)  # noqa: E712
                    )

                modules.append(
                    ModuleStatus(
                        name=mod.name,
                        display_name=mod.display_name,
                        icon=mod.icon,
                        description=mod.description,
                        enabled=enabled,
                        route_count=enabled_count or 0,
                        scopes=mod.required_scopes,
                    )
                )
        return modules

    @router.post("/modules/{module_name}/toggle")
    async def toggle_module(module_name: str, admin=Depends(require_admin)):
        """Toggle a module on or off."""
        from gatekeeper.modules import load_module

        mod = load_module(module_name)
        if not mod:
            raise HTTPException(status_code=404, detail=f"Module {module_name} not found")

        # Toggle the setting
        current = getattr(settings, f"{module_name}_enabled", False)
        setattr(settings, f"{module_name}_enabled", not current)
        new_status = not current
        return {"module": module_name, "enabled": new_status}

    @router.get("/routes", response_model=list[RoutePolicyResponse])
    async def list_routes(module: str | None = None, admin=Depends(require_admin)):
        """List all route policies, optionally filtered by module."""
        async with async_session() as session:
            query = select(RoutePolicy)
            if module:
                query = query.where(RoutePolicy.module == module)
            result = await session.execute(query.order_by(RoutePolicy.module, RoutePolicy.route))
            policies = result.scalars().all()
            return [
                RoutePolicyResponse(
                    id=p.id,
                    module=p.module,
                    route=p.route,
                    enabled=p.enabled,
                    policy_config=p.policy_config,
                    description=p.description,
                )
                for p in policies
            ]

    @router.patch("/routes/{route_id}", response_model=RoutePolicyResponse)
    async def update_route(route_id: int, update: RoutePolicyUpdate, admin=Depends(require_admin)):
        """Update a route policy (enable/disable, set config)."""
        async with async_session() as session:
            result = await session.execute(select(RoutePolicy).where(RoutePolicy.id == route_id))
            policy = result.scalar_one_or_none()
            if not policy:
                raise HTTPException(status_code=404, detail="Route policy not found")

            if update.enabled is not None:
                policy.enabled = update.enabled
            if update.policy_config is not None:
                policy.policy_config = json.dumps(update.policy_config)
            if update.description is not None:
                policy.description = update.description

            await session.commit()
            await session.refresh(policy)

            return RoutePolicyResponse(
                id=policy.id,
                module=policy.module,
                route=policy.route,
                enabled=policy.enabled,
                policy_config=policy.policy_config,
                description=policy.description,
            )

    @router.get("/audit", response_model=list[AuditLogResponse])
    async def audit_log(
        module: str | None = None,
        key_prefix: str | None = None,
        limit: int = 50,
        offset: int = 0,
        admin=Depends(require_admin),
    ):
        """Get audit log entries with optional filters."""
        async with async_session() as session:
            query = select(AuditLog).order_by(AuditLog.created_at.desc())

            if module:
                query = query.where(AuditLog.module == module)
            if key_prefix:
                query = query.where(AuditLog.api_key_prefix.startswith(key_prefix))

            query = query.limit(limit).offset(offset)
            result = await session.execute(query)
            entries = result.scalars().all()
            return [
                AuditLogResponse(
                    id=e.id,
                    api_key_prefix=e.api_key_prefix,
                    module=e.module,
                    route=e.route,
                    method=e.method,
                    path=e.path,
                    status_code=e.status_code,
                    response_summary=e.response_summary,
                    created_at=e.created_at,
                )
                for e in entries
            ]

    @router.get("/auth/status", response_model=AuthStatus)
    async def auth_status(admin=Depends(require_admin)):
        """Get Google OAuth connection status."""
        status = credential_manager.get_status()
        return AuthStatus(
            connected=status.get("connected", False),
            scopes=status.get("scopes", []),
            expired=status.get("expired", True),
            has_refresh_token=status.get("has_refresh_token", False),
        )

    return router
