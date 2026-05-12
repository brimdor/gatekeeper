"""Google OAuth credential management — desktop app flow with encrypted token storage."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from gatekeeper.config import settings
from gatekeeper.encryption import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for the OAuth redirect callback."""

    auth_code: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            _CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Authorization successful!</h1>"
                b"<p>You can close this window.</p></body></html>"
            )
        elif "error" in params:
            _CallbackHandler.error = params["error"][0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            error_msg = f"Error: {params['error'][0]}"
            self.wfile.write(
                b"<html><body><h1>Authorization failed</h1>"
                b"<p>" + error_msg.encode() + b"</p></body></html>"
            )
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress default HTTP server logging."""
        pass


class GoogleCredentialManager:
    """Manages Google OAuth2 credentials — load, refresh, and store tokens."""

    def __init__(self, token_path: Optional[Path] = None):
        self.token_path = token_path or Path(settings.google_token_file)
        self._credentials: Optional[Credentials] = None
        self._lock = threading.Lock()

    def load_credentials(self) -> Optional[Credentials]:
        """Load credentials from the encrypted token file.

        Returns None if no token file exists.
        """
        if not self.token_path.exists():
            logger.info(f"Token file not found: {self.token_path}")
            return None

        try:
            encrypted_data = self.token_path.read_text().strip()
            decrypted_data = decrypt_value(encrypted_data)
            data = json.loads(decrypted_data)

            creds = Credentials(
                token=data.get("token"),
                refresh_token=data.get("refresh_token"),
                token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
                scopes=data.get("scopes", []),
            )
            self._credentials = creds
            logger.info("Google credentials loaded successfully")
            return creds
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            return None

    def refresh_if_needed(self) -> Optional[Credentials]:
        """Refresh credentials if expired. Returns valid credentials or None."""
        with self._lock:
            if not self._credentials:
                self._credentials = self.load_credentials()
            if not self._credentials:
                return None

            if self._credentials.expired and self._credentials.refresh_token:
                try:
                    self._credentials.refresh(Request())
                    self._save_credentials()
                    logger.info("Google credentials refreshed successfully")
                except Exception as e:
                    logger.error(f"Failed to refresh credentials: {e}")
                    return None

            return self._credentials

    def get_credentials(self) -> Optional[Credentials]:
        """Get valid credentials, refreshing if needed."""
        return self.refresh_if_needed()

    def _save_credentials(self) -> None:
        """Save credentials to the encrypted token file."""
        if not self._credentials:
            return

        data = {
            "token": self._credentials.token,
            "refresh_token": self._credentials.refresh_token,
            "token_uri": self._credentials.token_uri,
            "client_id": self._credentials.client_id,
            "client_secret": self._credentials.client_secret,
            "scopes": list(self._credentials.scopes) if self._credentials.scopes else [],
        }
        encrypted_data = encrypt_value(json.dumps(data))
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(encrypted_data)
        logger.info("Credentials saved (encrypted)")

    def start_auth_flow(self, scopes: Optional[list[str]] = None) -> Optional[Credentials]:
        """Run the desktop OAuth flow.

        Starts a local HTTP server, opens the browser for authorization,
        captures the redirect, exchanges the auth code for tokens,
        and saves encrypted credentials.

        Args:
            scopes: OAuth scopes to request. Defaults to all enabled module scopes.

        Returns:
            Valid credentials on success, None on failure.
        """
        from google_auth_oauthlib.flow import InstalledAppFlow

        if not settings.google_client_id or not settings.google_client_secret:
            logger.error("Google OAuth client ID/secret not configured")
            print("ERROR: Set GATEKEEPER_GOOGLE_CLIENT_ID and GATEKEEPER_GOOGLE_CLIENT_SECRET")
            return None

        # Determine scopes from enabled modules
        if scopes is None:
            scopes = self._get_enabled_scopes()

        if not scopes:
            scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

        client_config = {
            "installed": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }

        try:
            flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)
            creds = flow.run_local_server(port=0, open_browser=True)

            self._credentials = creds
            self._save_credentials()
            logger.info("OAuth flow completed successfully")
            return creds
        except Exception as e:
            logger.error(f"OAuth flow failed: {e}")
            print(f"ERROR: OAuth flow failed: {e}")
            return None

    def _get_enabled_scopes(self) -> list[str]:
        """Get scopes required by all enabled modules."""
        from gatekeeper.modules import load_module

        scopes = set()
        enabled = []
        if settings.drive_enabled:
            enabled.append("drive")
        if settings.gmail_enabled:
            enabled.append("gmail")
        if settings.calendar_enabled:
            enabled.append("calendar")

        # If nothing enabled, use all modules
        if not enabled:
            enabled = ["drive", "gmail", "calendar"]

        for name in enabled:
            mod = load_module(name)
            if mod:
                scopes.update(mod.required_scopes)

        return list(scopes)

    def get_status(self) -> dict:
        """Return auth status information."""
        creds = self.get_credentials()
        if creds:
            return {
                "connected": True,
                "scopes": list(creds.scopes) if creds.scopes else [],
                "expired": creds.expired,
                "has_refresh_token": bool(creds.refresh_token),
            }
        return {"connected": False, "scopes": [], "expired": True, "has_refresh_token": False}


# Singleton instance
credential_manager = GoogleCredentialManager()