"""Tests for Gatekeeper configuration."""

import os
import pytest


def test_settings_load_from_defaults():
    """Settings should load with sensible defaults when no env vars are set."""
    from gatekeeper.config import Settings

    s = Settings(
        _env_file=None,
        secret_key="test-key-for-unit-tests",
        admin_password="test-pass",
        encryption_key="a" * 64,  # 32 bytes = 64 hex chars
    )
    s.ensure_secrets()
    assert s.host == "127.0.0.1"
    assert s.port == 8080
    assert s.api_key_prefix == "gkp_"
    assert s.database_url.startswith("sqlite")
    assert s.mcp_enabled is True
    assert s.drive_enabled is False
    assert s.gmail_enabled is False
    assert s.calendar_enabled is False


def test_settings_ensure_secrets_generates_missing():
    """ensure_secrets() should generate missing secret values."""
    from gatekeeper.config import Settings

    s = Settings(
        _env_file=None,
        secret_key="",
        admin_password="",
        encryption_key="",
    )
    # Before ensure_secrets, these are empty
    assert s.secret_key == ""
    assert s.admin_password == ""
    assert s.encryption_key == ""

    s.ensure_secrets()

    # After ensure_secrets, these should be populated
    assert len(s.secret_key) > 0
    assert len(s.admin_password) > 0
    assert len(s.encryption_key) == 64  # 32 bytes = 64 hex chars


def test_settings_ensure_secrets_preserves_existing():
    """ensure_secrets() should NOT overwrite existing values."""
    from gatekeeper.config import Settings

    s = Settings(
        _env_file=None,
        secret_key="my-existing-key",
        admin_password="my-existing-pass",
        encryption_key="b" * 64,
    )
    s.ensure_secrets()

    assert s.secret_key == "my-existing-key"
    assert s.admin_password == "my-existing-pass"
    assert s.encryption_key == "b" * 64


def test_settings_env_vars_override():
    """GATEKEEPER_* env vars should override defaults."""
    from gatekeeper.config import Settings

    s = Settings(
        _env_file=None,
        secret_key="test-key",
        admin_password="test-pass",
        encryption_key="c" * 64,
        host="0.0.0.0",
        port=9090,
        debug=True,
        drive_enabled=True,
    )
    s.ensure_secrets()
    assert s.host == "0.0.0.0"
    assert s.port == 9090
    assert s.debug is True
    assert s.drive_enabled is True