"""ORM models — API keys, route policies, audit log, Google tokens."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from gatekeeper.db import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Permissions: comma-separated module names, or "*" for all enabled
    permissions: Mapped[str] = mapped_column(String(500), default="*")

    @staticmethod
    def generate_key(prefix: str = "gkp_") -> tuple[str, str, str]:
        """Generate an API key.
        
        Returns:
            (raw_key, key_hash, key_prefix) — raw_key is shown once, 
            key_hash stored in DB, key_prefix used for lookup.
        """
        import bcrypt

        raw = prefix + secrets.token_urlsafe(32)
        key_hash = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
        key_prefix = raw[: len(prefix) + 8]  # e.g. "gkp_a1b2c3d4"
        return raw, key_hash, key_prefix

    def __repr__(self) -> str:
        return f"<ApiKey id={self.id} name={self.name!r} prefix={self.key_prefix!r}>"


class RoutePolicy(Base):
    __tablename__ = "route_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    route: Mapped[str] = mapped_column(String(200), nullable=False)
    __table_args__ = (
        UniqueConstraint("module", "route", name="uq_route_policy_module_route"),
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # JSON policy config — limits, filters, transforms
    policy_config: Mapped[str] = mapped_column(Text, default="{}")
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<RoutePolicy id={self.id} {self.module}.{self.route} enabled={self.enabled}>"


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    api_key_prefix: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    route: Mapped[str] = mapped_column(String(200), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # Truncated response summary (avoid bloating DB)
    response_summary: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} {self.method} {self.module}.{self.route} {self.status_code}>"


class GoogleToken(Base):
    __tablename__ = "google_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    # Encrypted token data (JSON blob encrypted with settings.encryption_key)
    encrypted_token: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<GoogleToken id={self.id} service={self.service!r}>"