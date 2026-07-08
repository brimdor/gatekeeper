"""Pydantic models for the admin API."""

from __future__ import annotations

from pydantic import BaseModel


class ApiKeyCreate(BaseModel):
    name: str
    permissions: str = "*"


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    is_active: bool
    permissions: str
    created_at: str | None = None
    last_used_at: str | None = None


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
    response_message: str | None = None
    created_at: str | None = None


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
