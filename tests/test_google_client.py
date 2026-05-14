"""Tests for Google OAuth client and credential management."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet

from gatekeeper.config import Settings


def _make_settings(tmp_path, encryption_key=None):
    """Create settings with a temp token path."""
    if encryption_key is None:
        encryption_key = Fernet.generate_key().decode()
    return Settings(
        _env_file=None,
        secret_key="test-key",
        admin_password="test-pass",
        encryption_key=encryption_key,
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
        google_token_file=str(tmp_path / "token.json"),
    )


class TestGoogleCredentialManager:
    """Tests for GoogleCredentialManager."""

    def test_load_credentials_returns_none_when_no_file(self, tmp_path):
        """load_credentials should return None when token file doesn't exist."""
        from gatekeeper.google_client import GoogleCredentialManager

        settings = _make_settings(tmp_path)
        mgr = GoogleCredentialManager(token_path=Path(settings.google_token_file))
        import gatekeeper.encryption
        import gatekeeper.google_client

        orig = gatekeeper.google_client.settings
        orig_enc = gatekeeper.encryption.settings
        gatekeeper.google_client.settings = settings
        gatekeeper.encryption.settings = settings

        try:
            result = mgr.load_credentials()
            assert result is None
        finally:
            gatekeeper.google_client.settings = orig
            gatekeeper.encryption.settings = orig_enc

    def test_save_and_load_roundtrip(self, tmp_path):
        """Saving and loading credentials should round-trip correctly."""
        from google.oauth2.credentials import Credentials

        from gatekeeper.google_client import GoogleCredentialManager

        settings = _make_settings(tmp_path)
        token_path = Path(settings.google_token_file)

        import gatekeeper.encryption
        import gatekeeper.google_client

        orig = gatekeeper.google_client.settings
        orig_enc = gatekeeper.encryption.settings
        gatekeeper.google_client.settings = settings
        gatekeeper.encryption.settings = settings

        try:
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

            # Verify file is encrypted (not valid JSON)
            assert token_path.exists()
            raw_content = token_path.read_text()
            try:
                json.loads(raw_content)
                assert False, "Token file should be encrypted, not plaintext JSON"
            except json.JSONDecodeError:
                pass  # Expected

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

        settings = _make_settings(tmp_path)
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

        settings = _make_settings(tmp_path)
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
        from gatekeeper.google_client import GoogleCredentialManager, credential_manager

        assert credential_manager is not None
        assert isinstance(credential_manager, GoogleCredentialManager)


class TestDeviceAuthFlow:
    """Tests for the device authorization flow (link + code, for headless/remote setups)."""

    def test_device_auth_no_client_id(self, tmp_path):
        """Device auth should fail gracefully with no client ID."""
        from gatekeeper.google_client import GoogleCredentialManager

        settings = _make_settings(tmp_path)
        settings.google_client_id = None
        settings.google_client_secret = None

        import gatekeeper.google_client

        orig = gatekeeper.google_client.settings
        gatekeeper.google_client.settings = settings

        try:
            mgr = GoogleCredentialManager(token_path=Path(settings.google_token_file))
            result = mgr.start_device_auth_flow()
            assert result is None
        finally:
            gatekeeper.google_client.settings = orig

    def test_device_auth_mock_success(self, tmp_path):
        """Device auth flow should succeed with mocked HTTP responses."""
        from google.oauth2.credentials import Credentials

        from gatekeeper.google_client import GoogleCredentialManager

        settings = _make_settings(tmp_path)
        token_path = Path(settings.google_token_file)

        import gatekeeper.encryption
        import gatekeeper.google_client

        orig = gatekeeper.google_client.settings
        orig_enc = gatekeeper.encryption.settings
        gatekeeper.google_client.settings = settings
        gatekeeper.encryption.settings = settings

        try:
            # Mock the device code request
            device_code_response = MagicMock()
            device_code_response.status_code = 200
            device_code_response.json.return_value = {
                "device_code": "test-device-code",
                "user_code": "ABCD-EFGH",
                "verification_url": "https://www.google.com/device",
                "expires_in": 900,
                "interval": 1,
            }
            device_code_response.raise_for_status = MagicMock()

            # Mock the token exchange (success on first poll)
            token_response = MagicMock()
            token_response.status_code = 200
            token_response.json.return_value = {
                "access_token": "test-access-token",
                "refresh_token": "test-refresh-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/gmail.readonly",
            }

            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = [device_code_response, token_response]
            mock_client.get.side_effect = []  # No GET calls needed

            with patch("gatekeeper.google_client.httpx.Client", return_value=mock_client):
                mgr = GoogleCredentialManager(token_path=token_path)
                result = mgr.start_device_auth_flow(
                    scopes=["https://www.googleapis.com/auth/gmail.readonly"]
                )

            # Should return credentials
            assert result is not None
            assert isinstance(result, Credentials)
            assert result.token == "test-access-token"

            # Token file should exist (encrypted)
            assert token_path.exists()
        finally:
            gatekeeper.google_client.settings = orig
            gatekeeper.encryption.settings = orig_enc

    def test_device_auth_mock_pending_then_success(self, tmp_path):
        """Device auth should poll until user authorizes (authorization_pending -> success)."""
        from gatekeeper.google_client import GoogleCredentialManager

        settings = _make_settings(tmp_path)
        token_path = Path(settings.google_token_file)

        import gatekeeper.encryption
        import gatekeeper.google_client

        orig = gatekeeper.google_client.settings
        orig_enc = gatekeeper.encryption.settings
        gatekeeper.google_client.settings = settings
        gatekeeper.encryption.settings = settings

        try:
            device_code_response = MagicMock()
            device_code_response.status_code = 200
            device_code_response.json.return_value = {
                "device_code": "test-device-code",
                "user_code": "WXYZ-1234",
                "verification_url": "https://www.google.com/device",
                "expires_in": 900,
                "interval": 0,  # No wait in tests
            }
            device_code_response.raise_for_status = MagicMock()

            # First poll: pending, second poll: success
            pending_response = MagicMock()
            pending_response.status_code = 428
            pending_response.json.return_value = {"error": "authorization_pending"}

            success_response = MagicMock()
            success_response.status_code = 200
            success_response.json.return_value = {
                "access_token": "test-access-token-2",
                "refresh_token": "test-refresh-token-2",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/calendar.readonly",
            }

            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = [
                device_code_response,
                pending_response,
                success_response,
            ]

            with patch("gatekeeper.google_client.httpx.Client", return_value=mock_client):
                with patch("gatekeeper.google_client.time.sleep"):  # Skip sleeps in test
                    mgr = GoogleCredentialManager(token_path=token_path)
                    result = mgr.start_device_auth_flow(
                        scopes=["https://www.googleapis.com/auth/calendar.readonly"]
                    )

            assert result is not None
            assert result.token == "test-access-token-2"
        finally:
            gatekeeper.google_client.settings = orig
            gatekeeper.encryption.settings = orig_enc

    def test_get_enabled_scopes_defaults(self, tmp_path):
        """get_enabled_scopes should return read-only defaults when no modules enabled."""
        from gatekeeper.google_client import GoogleCredentialManager

        settings = _make_settings(tmp_path)
        settings.drive_enabled = False
        settings.gmail_enabled = False
        settings.calendar_enabled = False

        import gatekeeper.google_client

        orig = gatekeeper.google_client.settings
        gatekeeper.google_client.settings = settings

        try:
            mgr = GoogleCredentialManager(token_path=Path(settings.google_token_file))
            scopes = mgr._get_enabled_scopes()
            # When nothing is enabled, should return read-only defaults
            assert "https://www.googleapis.com/auth/drive.readonly" in scopes
            assert "https://www.googleapis.com/auth/gmail.readonly" in scopes
            assert "https://www.googleapis.com/auth/calendar.readonly" in scopes
        finally:
            gatekeeper.google_client.settings = orig


class TestDesktopAuthFlow:
    """Tests for the desktop OAuth flow (browser redirect)."""

    def test_desktop_auth_no_client_id(self, tmp_path):
        """Desktop auth should fail gracefully with no client ID."""
        from gatekeeper.google_client import GoogleCredentialManager

        settings = _make_settings(tmp_path)
        settings.google_client_id = None
        settings.google_client_secret = None

        import gatekeeper.google_client

        orig = gatekeeper.google_client.settings
        gatekeeper.google_client.settings = settings

        try:
            mgr = GoogleCredentialManager(token_path=Path(settings.google_token_file))
            result = mgr.start_desktop_auth_flow()
            assert result is None
        finally:
            gatekeeper.google_client.settings = orig

    def test_desktop_auth_mock_success(self, tmp_path):
        """Desktop auth flow should succeed with mocked InstalledAppFlow."""
        from google.oauth2.credentials import Credentials

        from gatekeeper.google_client import GoogleCredentialManager

        settings = _make_settings(tmp_path)
        token_path = Path(settings.google_token_file)

        import gatekeeper.encryption
        import gatekeeper.google_client

        orig = gatekeeper.google_client.settings
        orig_enc = gatekeeper.encryption.settings
        gatekeeper.google_client.settings = settings
        gatekeeper.encryption.settings = settings

        try:
            # Create mock credentials
            mock_creds = Credentials(
                token="test-access-token-desktop",
                refresh_token="test-refresh-token-desktop",
                token_uri="https://oauth2.googleapis.com/token",
                client_id="test-client-id",
                client_secret="test-client-secret",
                scopes=["https://www.googleapis.com/auth/drive.readonly"],
            )

            # Mock the flow: InstalledAppFlow.from_client_config().run_local_server()
            mock_flow = MagicMock()
            mock_flow.run_local_server.return_value = mock_creds

            mock_iapp = MagicMock()
            mock_iapp.from_client_config.return_value = mock_flow

            import google_auth_oauthlib.flow
            orig_class = google_auth_oauthlib.flow.InstalledAppFlow
            google_auth_oauthlib.flow.InstalledAppFlow = mock_iapp

            try:
                mgr = GoogleCredentialManager(token_path=token_path)
                result = mgr.start_desktop_auth_flow(
                    scopes=["https://www.googleapis.com/auth/drive.readonly"]
                )
            finally:
                google_auth_oauthlib.flow.InstalledAppFlow = orig_class

            # Should return credentials
            assert result is not None
            assert result.token == "test-access-token-desktop"
            assert result.refresh_token == "test-refresh-token-desktop"

            # Token file should exist (encrypted)
            assert token_path.exists()

            # Verify the flow config used correct client details
            call_kwargs = mock_iapp.from_client_config.call_args
            config = call_kwargs[0][0]
            assert config["installed"]["client_id"] == "test-client-id"
            assert config["installed"]["client_secret"] == "test-client-secret"
            assert "http://localhost" in config["installed"]["redirect_uris"]
            assert call_kwargs[1]["scopes"] == ["https://www.googleapis.com/auth/drive.readonly"]
        finally:
            gatekeeper.google_client.settings = orig
            gatekeeper.encryption.settings = orig_enc

    def test_desktop_auth_flow_failure(self, tmp_path):
        """Desktop auth should return None if InstalledAppFlow raises an exception."""
        from gatekeeper.google_client import GoogleCredentialManager

        settings = _make_settings(tmp_path)
        token_path = Path(settings.google_token_file)

        import gatekeeper.google_client

        orig = gatekeeper.google_client.settings
        gatekeeper.google_client.settings = settings

        try:
            mock_flow = MagicMock()
            mock_flow.run_local_server.side_effect = Exception("Browser failed to open")

            mock_iapp = MagicMock()
            mock_iapp.from_client_config.return_value = mock_flow

            import google_auth_oauthlib.flow
            orig_class = google_auth_oauthlib.flow.InstalledAppFlow
            google_auth_oauthlib.flow.InstalledAppFlow = mock_iapp

            try:
                mgr = GoogleCredentialManager(token_path=token_path)
                result = mgr.start_desktop_auth_flow()
            finally:
                google_auth_oauthlib.flow.InstalledAppFlow = orig_class

            assert result is None
        finally:
            gatekeeper.google_client.settings = orig


class TestStartAuthFlow:
    """Tests for start_auth_flow dispatching."""

    def test_start_auth_flow_defaults_to_desktop(self, tmp_path):
        """start_auth_flow with no args should use desktop flow (the default)."""
        from gatekeeper.google_client import GoogleCredentialManager

        settings = _make_settings(tmp_path)
        settings.google_client_id = None  # Will fail fast — we just check it dispatches

        import gatekeeper.google_client

        orig = gatekeeper.google_client.settings
        gatekeeper.google_client.settings = settings

        try:
            mgr = GoogleCredentialManager(token_path=Path(settings.google_token_file))
            # Without flow kwarg, should dispatch to desktop (which will fail
            # because client_id is None, but that proves the dispatch)
            with patch.object(mgr, "start_desktop_auth_flow", return_value=None) as mock_desktop:
                mgr.start_auth_flow()
                mock_desktop.assert_called_once()
        finally:
            gatekeeper.google_client.settings = orig

    def test_start_auth_flow_device_dispatches(self, tmp_path):
        """start_auth_flow with flow='device' should use device flow."""
        from gatekeeper.google_client import GoogleCredentialManager

        settings = _make_settings(tmp_path)
        settings.google_client_id = None

        import gatekeeper.google_client

        orig = gatekeeper.google_client.settings
        gatekeeper.google_client.settings = settings

        try:
            mgr = GoogleCredentialManager(token_path=Path(settings.google_token_file))
            with patch.object(mgr, "start_device_auth_flow", return_value=None) as mock_device:
                mgr.start_auth_flow(flow="device")
                mock_device.assert_called_once()
        finally:
            gatekeeper.google_client.settings = orig
