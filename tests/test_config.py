"""Tests for Gatekeeper configuration."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet


def test_settings_load_from_defaults():
    """Settings should load with sensible defaults when no env vars are set."""
    from gatekeeper.config import Settings

    s = Settings(
        _env_file=None,
        secret_key="test-key-for-unit-tests",
        admin_password="test-pass",
        encryption_key=Fernet.generate_key().decode(),
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
    """ensure_secrets() should generate and persist missing secret values."""
    from gatekeeper.config import Settings

    with tempfile.TemporaryDirectory() as tmpdir:
        secrets_path = Path(tmpdir) / "test_secrets.json"

        with patch("gatekeeper.config._SECRETS_FILE", secrets_path):
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

            # Patch the module-level reference so ensure_secrets uses our temp path
            with patch("gatekeeper.config._SECRETS_FILE", secrets_path):
                s.ensure_secrets()

            # After ensure_secrets, these should be populated
            assert len(s.secret_key) > 0
            assert len(s.admin_password) > 0
            # encryption_key is now a Fernet key (base64-encoded 32 bytes)
            assert len(s.encryption_key) > 0
            # Verify it's a valid Fernet key
            Fernet(s.encryption_key.encode())


def test_settings_ensure_secrets_preserves_existing():
    """ensure_secrets() should NOT overwrite existing values."""
    from gatekeeper.config import Settings

    fernet_key = Fernet.generate_key().decode()
    s = Settings(
        _env_file=None,
        secret_key="my-existing-key",
        admin_password="my-existing-pass",
        encryption_key=fernet_key,
    )
    s.ensure_secrets()

    assert s.secret_key == "my-existing-key"
    assert s.admin_password == "my-existing-pass"
    assert s.encryption_key == fernet_key


def test_settings_persistence_across_restarts():
    """Generated secrets should persist in the secrets file and be reused."""
    from gatekeeper.config import Settings

    with tempfile.TemporaryDirectory() as tmpdir:
        secrets_path = Path(tmpdir) / "test_secrets.json"

        # First run: generate secrets
        with patch("gatekeeper.config._SECRETS_FILE", secrets_path):
            s1 = Settings(
                _env_file=None,
                secret_key="",
                admin_password="",
                encryption_key="",
            )
            with patch("gatekeeper.config._SECRETS_FILE", secrets_path):
                s1.ensure_secrets()

            gen_key = s1.secret_key
            gen_pass = s1.admin_password
            gen_enc = s1.encryption_key

        # Second run: should load persisted secrets
        with patch("gatekeeper.config._SECRETS_FILE", secrets_path):
            s2 = Settings(
                _env_file=None,
                secret_key="",
                admin_password="",
                encryption_key="",
            )
            with patch("gatekeeper.config._SECRETS_FILE", secrets_path):
                s2.ensure_secrets()

            # Same values loaded from file
            assert s2.secret_key == gen_key
            assert s2.admin_password == gen_pass
            assert s2.encryption_key == gen_enc


def test_settings_env_vars_override():
    """GATEKEEPER_* env vars should override defaults."""
    from gatekeeper.config import Settings

    fernet_key = Fernet.generate_key().decode()
    s = Settings(
        _env_file=None,
        secret_key="test-key",
        admin_password="test-pass",
        encryption_key=fernet_key,
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
