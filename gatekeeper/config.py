"""Gatekeeper configuration via environment variables and pydantic-settings."""

from __future__ import annotations

import json
import logging
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Path for persisting auto-generated secrets across restarts
_SECRETS_FILE = Path("./gatekeeper_secrets.json")


def _load_persisted_secrets() -> dict:
    """Load persisted secrets from the secrets file."""
    if _SECRETS_FILE.exists():
        try:
            return json.loads(_SECRETS_FILE.read_text())
        except Exception:
            return {}
    return {}


def _persist_secrets(data: dict) -> None:
    """Persist secrets to the secrets file."""
    _SECRETS_FILE.write_text(json.dumps(data, indent=2))
    # Restrict permissions (owner read/write only)
    try:
        _SECRETS_FILE.chmod(0o600)
    except Exception:
        pass


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
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_token_file: str = "./google_token.json"

    # Admin
    admin_username: str = "admin"
    admin_password: str = ""  # Generated on first run if empty

    # MCP Server
    mcp_enabled: bool = True
    # MCP allowed hosts — Host header values the MCP SSE endpoint will accept.
    # Default is localhost/127.0.0.1 on the configured port.
    # Add your Tailscale hostname, LAN IP, etc. via GATEKEEPER_MCP_ALLOWED_HOSTS.
    # Use "*:PORT" to allow any hostname (less secure, convenient for proxies).
    mcp_allowed_hosts: list[str] = []

    # Security
    api_key_prefix: str = "gkp_"
    rate_limit_per_minute: int = 120
    # CORS: do NOT use wildcards with allow_credentials=True — specify exact origins.
    # For development, list localhost variants. For production, set GATEKEEPER_CORS_ORIGINS
    # to the exact origin(s) that need access.
    cors_origins: list[str] = ["http://localhost:8080", "http://127.0.0.1:8080"]

    # Modules
    drive_enabled: bool = False
    gmail_enabled: bool = False
    calendar_enabled: bool = False

    # Encryption key for storing Google OAuth tokens (Fernet key, base64-encoded)
    encryption_key: str = ""  # Generated on first run if empty

    def ensure_secrets(self) -> None:
        """Generate secrets if not set, persisting them to avoid regeneration on restart.

        Secrets are stored in gatekeeper_secrets.json (chmod 600). On subsequent
        starts, the persisted values are loaded so the admin password, encryption
        key, and secret key remain stable across restarts.
        """
        from cryptography.fernet import Fernet

        persisted = _load_persisted_secrets()
        changed = False

        if not self.secret_key:
            if "secret_key" in persisted:
                self.secret_key = persisted["secret_key"]
            else:
                self.secret_key = secrets.token_hex(32)
                persisted["secret_key"] = self.secret_key
                changed = True

        if not self.admin_password:
            if "admin_password" in persisted:
                self.admin_password = persisted["admin_password"]
            else:
                self.admin_password = secrets.token_urlsafe(16)
                persisted["admin_password"] = self.admin_password
                changed = True
                # Print the generated password so the admin can save it
                logger.info("=" * 60)
                logger.info("🔑 Admin password generated: %s", self.admin_password)
                logger.info("   This is also saved in gatekeeper_secrets.json")
                logger.info("=" * 60)
                print(f"\n{'=' * 60}")
                print(f"🔑 Admin password generated: {self.admin_password}")
                print("   Saved to gatekeeper_secrets.json")
                print(f"{'=' * 60}\n")

        if not self.encryption_key:
            if "encryption_key" in persisted:
                self.encryption_key = persisted["encryption_key"]
            else:
                # Generate a proper Fernet key (base64-encoded 32 bytes)
                self.encryption_key = Fernet.generate_key().decode()
                persisted["encryption_key"] = self.encryption_key
                changed = True

        if changed:
            _persist_secrets(persisted)


settings = Settings()
settings.ensure_secrets()
