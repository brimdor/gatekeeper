"""Pydantic models for the admin API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

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
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class ApiKeyCreated(BaseModel):
    id: int  # Database ID, useful for revoke/delete operations
    name: str
    key_prefix: str
    raw_key: str  # Only returned on creation


class RoutePolicyUpdate(BaseModel):
    enabled: Optional[bool] = None
    policy_config: Optional[dict] = None
    description: Optional[str] = None


class RoutePolicyResponse(BaseModel):
    id: int
    module: str
    route: str
    enabled: bool
    policy_config: str
    description: Optional[str] = None


class AuditLogResponse(BaseModel):
    id: int
    api_key_prefix: str
    module: str
    route: str
    method: str
    path: str
    status_code: int
    response_summary: Optional[str] = None
    created_at: Optional[datetime] = None


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