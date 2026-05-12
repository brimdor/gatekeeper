"""Tests for Google OAuth client and credential management."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from gatekeeper.config import Settings


class TestGoogleCredentialManager:
    """Tests for GoogleCredentialManager."""

    def _make_settings(self, tmp_path):
        """Create settings with a temp token path."""
        return Settings(
            _env_file=None,
            secret_key="test-key",
            admin_password="test-pass",
            encryption_key="a" * 64,
            google_client_id="test-client-id",
            google_client_secret="test-client-secret",
            google_token_file=str(tmp_path / "token.json"),
        )

    def test_load_credentials_returns_none_when_no_file(self, tmp_path):
        """load_credentials should return None when token file doesn't exist."""
        from gatekeeper.google_client import GoogleCredentialManager

        settings = self._make_settings(tmp_path)
        mgr = GoogleCredentialManager(token_path=Path(settings.google_token_file))
        # Override settings
        import gatekeeper.google_client

        orig = gatekeeper.google_client.settings
        gatekeeper.google_client.settings = settings

        # Also need to update encryption module settings
        import gatekeeper.encryption

        orig_enc = gatekeeper.encryption.settings
        gatekeeper.encryption.settings = settings

        try:
            result = mgr.load_credentials()
            assert result is None
        finally:
            gatekeeper.google_client.settings = orig
            gatekeeper.encryption.settings = orig_enc

    def test_save_and_load_roundtrip(self, tmp_path):
        """Saving and loading credentials should round-trip correctly."""
        from gatekeeper.google_client import GoogleCredentialManager
        from gatekeeper.encryption import encrypt_value
        from google.oauth2.credentials import Credentials

        settings = self._make_settings(tmp_path)
        token_path = Path(settings.google_token_file)

        import gatekeeper.google_client
        import gatekeeper.encryption

        orig = gatekeeper.google_client.settings
        orig_enc = gatekeeper.encryption.settings
        gatekeeper.google_client.settings = settings
        gatekeeper.encryption.settings = settings

        try:
            # Create and save credentials directly
            creds = Credentials(
                token="test-token-123",
                refresh_token="test-refresh-456",
                token_uri="https://oauth2.googleapis.com/token",
                client_id="test-client-id",
                client_secret="test-client-secret",
                scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            )

            mgr = GoogleCredentialManager(token_path=token_path)
            mgr._credentials = creds
            mgr._save_credentials()

            # Verify file exists and is encrypted (not valid JSON)
            assert token_path.exists()
            raw_content = token_path.read_text()
            # Should NOT be valid JSON (it's encrypted)
            try:
                json.loads(raw_content)
                assert False, "Token file should be encrypted, not plaintext JSON"
            except json.JSONDecodeError:
                pass  # Expected — file is encrypted

            # Load should work
            loaded = mgr.load_credentials()
            assert loaded is not None
            assert loaded.refresh_token == "test-refresh-456"
            assert loaded.token == "test-token-123"
            assert "https://www.googleapis.com/auth/gmail.readonly" in loaded.scopes
        finally:
            gatekeeper.google_client.settings = orig
            gatekeeper.encryption.settings = orig_enc

    def test_get_credentials_returns_none_when_no_creds(self, tmp_path):
        """get_credentials should return None when no credentials exist."""
        from gatekeeper.google_client import GoogleCredentialManager

        settings = self._make_settings(tmp_path)
        import gatekeeper.google_client

        orig = gatekeeper.google_client.settings
        gatekeeper.google_client.settings = settings

        try:
            mgr = GoogleCredentialManager(token_path=Path(settings.google_token_file))
            result = mgr.get_credentials()
            assert result is None
        finally:
            gatekeeper.google_client.settings = orig

    def test_get_status_when_disconnected(self, tmp_path):
        """get_status should return disconnected when no credentials exist."""
        from gatekeeper.google_client import GoogleCredentialManager

        settings = self._make_settings(tmp_path)
        import gatekeeper.google_client

        orig = gatekeeper.google_client.settings
        gatekeeper.google_client.settings = settings

        try:
            mgr = GoogleCredentialManager(token_path=Path(settings.google_token_file))
            status = mgr.get_status()
            assert status["connected"] is False
            assert status["has_refresh_token"] is False
        finally:
            gatekeeper.google_client.settings = orig

    def test_credential_manager_singleton_exists(self):
        """The module-level singleton should exist."""
        from gatekeeper.google_client import credential_manager, GoogleCredentialManager

        assert credential_manager is not None
        assert isinstance(credential_manager, GoogleCredentialManager)