"""Pydantic models for the admin API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, model_serializer


class ApiKeyCreate(BaseModel):
    name: str
    permissions: str = "*"


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    is_active: bool
    permissions: str
    created_at: datetime | None = None
    last_used_at: datetime | None = None

    @model_serializer(mode="plain")
    def _serialize_datetimes(self) -> dict:
        """Convert UTC datetimes to display timezone before serialization."""
        from gatekeeper.format import format_dt

        return {
            "id": self.id,
            "name": self.name,
            "key_prefix": self.key_prefix,
            "is_active": self.is_active,
            "permissions": self.permissions,
            "created_at": format_dt(self.created_at),
            "last_used_at": format_dt(self.last_used_at),
        }


class ApiKeyCreated(BaseModel):
    id: int  # Database ID, useful for revoke/delete operations
    name: str
    key_prefix: str
    raw_key: str  # Only returned on creation


class RoutePolicyUpdate(BaseModel):
    enabled: bool | None = None
    policy_config: dict | None = None
    description: str | None = None


class RoutePolicyResponse(BaseModel):
    id: int
    module: str
    route: str
    enabled: bool
    policy_config: str
    description: str | None = None


class AuditLogResponse(BaseModel):
    id: int
    api_key_prefix: str
    module: str
    route: str
    method: str
    path: str
    status_code: int
    response_summary: str | None = None
    created_at: datetime | None = None

    @model_serializer(mode="plain")
    def _serialize_datetimes(self) -> dict:
        """Convert UTC datetimes to display timezone before serialization."""
        from gatekeeper.format import format_dt

        return {
            "id": self.id,
            "api_key_prefix": self.api_key_prefix,
            "module": self.module,
            "route": self.route,
            "method": self.method,
            "path": self.path,
            "status_code": self.status_code,
            "response_summary": self.response_summary,
            "created_at": format_dt(self.created_at),
        }


class AuthStatus(BaseModel):
    connected: bool
    scopes: list[str] = []
    expired: bool = True
    has_refresh_token: bool = False


class ModuleStatus(BaseModel):
    name: str
    display_name: str
    icon: str
    description: str
    enabled: bool
    route_count: int
    scopes: list[str]


class DashboardStats(BaseModel):
    total_requests: int
    active_keys: int
    enabled_routes: int
    auth_connected: bool
