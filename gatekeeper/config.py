"""Gatekeeper configuration via environment variables and pydantic-settings."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GATEKEEPER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    host: str = "127.0.0.1"
    port: int = 8080
    debug: bool = False
    secret_key: str = ""  # Generated on first run if empty

    # Database
    database_url: str = "sqlite+aiosqlite:///./gatekeeper.db"

    # Google OAuth
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_token_file: str = "./google_token.json"

    # Admin
    admin_username: str = "admin"
    admin_password: str = ""  # Generated on first run if empty

    # MCP Server
    mcp_enabled: bool = True

    # Security
    api_key_prefix: str = "gkp_"
    rate_limit_per_minute: int = 120
    cors_origins: list[str] = ["http://localhost:8080", "http://127.0.0.1:8080"]

    # Modules
    drive_enabled: bool = False
    gmail_enabled: bool = False
    calendar_enabled: bool = False

    # Encryption key for storing Google OAuth tokens (64-char hex string for Fernet)
    encryption_key: str = ""  # Generated on first run if empty

    def ensure_secrets(self) -> None:
        """Generate secrets if not set. Returns True if any were generated."""
        if not self.secret_key:
            self.secret_key = secrets.token_hex(32)
        if not self.admin_password:
            self.admin_password = secrets.token_urlsafe(16)
        if not self.encryption_key:
            self.encryption_key = secrets.token_hex(32)


settings = Settings()
settings.ensure_secrets()