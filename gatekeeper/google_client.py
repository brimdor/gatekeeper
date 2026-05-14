"""Google OAuth credential management — device auth flow
and desktop flow with encrypted token storage."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from gatekeeper.config import settings
from gatekeeper.encryption import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"


class GoogleCredentialManager:
    """Manages Google OAuth2 credentials — load, refresh, and store tokens.

    Supports two auth flows:
    1. Device authorization flow (default) — user visits a URL and enters a code.
       Works from any device, no local browser needed. Ideal for headless servers
       and remote setups.
    2. Desktop app flow — opens a browser on the local machine, captures the
       redirect automatically. Better UX when running locally.
    """

    def __init__(self, token_path: Path | None = None):
        self.token_path = token_path or Path(settings.google_token_file)
        self._credentials: Credentials | None = None
        self._lock = threading.Lock()

    def load_credentials(self) -> Credentials | None:
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

            # Restore expiry if persisted
            expiry = None
            if data.get("expiry"):
                from datetime import datetime

                expiry = datetime.fromisoformat(data["expiry"])

            creds = Credentials(
                token=data.get("token"),
                refresh_token=data.get("refresh_token"),
                token_uri=data.get("token_uri", GOOGLE_TOKEN_URL),
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
                scopes=data.get("scopes", []),
                expiry=expiry,
            )
            self._credentials = creds
            logger.info("Google credentials loaded successfully")
            return creds
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            return None

    def refresh_if_needed(self) -> Credentials | None:
        """Refresh credentials if expired or expiry is unknown.

        Credentials loaded from disk without an expiry field have
        ``expiry=None``, which makes ``expired`` return ``False`` — even
        though the access token may be stale.  We treat a missing expiry
        the same as expired and always refresh in that case.
        """
        with self._lock:
            if not self._credentials:
                self._credentials = self.load_credentials()
            if not self._credentials:
                return None

            needs_refresh = (
                self._credentials.expired or self._credentials.expiry is None
            ) and self._credentials.refresh_token
            if needs_refresh:
                try:
                    self._credentials.refresh(Request())
                    self._save_credentials()
                    logger.info("Google credentials refreshed successfully")
                except Exception as e:
                    logger.error(f"Failed to refresh credentials: {e}")
                    return None

            return self._credentials

    def get_credentials(self) -> Credentials | None:
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
            "expiry": self._credentials.expiry.isoformat() if self._credentials.expiry else None,
        }
        encrypted_data = encrypt_value(json.dumps(data))
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(encrypted_data)
        logger.info("Credentials saved (encrypted)")

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

        # If nothing enabled, use read-only scopes for all modules
        if not enabled:
            return [
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/calendar.readonly",
            ]

        for name in enabled:
            mod = load_module(name)
            if mod:
                scopes.update(mod.required_scopes)

        return list(scopes)

    def start_device_auth_flow(self, scopes: list[str] | None = None) -> Credentials | None:
        """Run the Google Device Authorization flow (link + code).

        This is the recommended flow for headless servers and remote setups.
        The user visits a URL on any device and enters a code — no local browser
        or redirect needed.

        Steps:
        1. POST to Google's device code endpoint → get user_code + verification_url
        2. Display the URL and code to the user
        3. Poll the token endpoint until the user authorizes
        4. Exchange for tokens and save encrypted credentials

        Args:
            scopes: OAuth scopes to request. Defaults to all enabled module scopes.

        Returns:
            Valid credentials on success, None on failure.
        """
        if not settings.google_client_id or not settings.google_client_secret:
            logger.error("Google OAuth client ID/secret not configured")
            print("\n❌ ERROR: Set GATEKEEPER_GOOGLE_CLIENT_ID and GATEKEEPER_GOOGLE_CLIENT_SECRET")
            print("   Add them to your .env file or environment variables.\n")
            return None

        if scopes is None:
            scopes = self._get_enabled_scopes()

        if not scopes:
            scopes = [
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/calendar.readonly",
            ]

        # Step 1: Get device code
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    GOOGLE_DEVICE_CODE_URL,
                    data={
                        "client_id": settings.google_client_id,
                        "client_secret": settings.google_client_secret,
                        "scope": " ".join(scopes),
                    },
                )
                response.raise_for_status()
                device_data = response.json()
        except httpx.HTTPError as e:
            logger.error(f"Device code request failed: {e}")
            print(f"\n❌ ERROR: Failed to get device code: {e}\n")
            return None

        user_code = device_data["user_code"]
        verification_url = device_data["verification_url"]
        device_code = device_data["device_code"]
        interval = device_data.get("interval", 5)
        expires_in = device_data.get("expires_in", 900)

        # Step 2: Display URL and code
        print(f"\n{'=' * 60}")
        print("🔐 Google Account Authorization")
        print(f"{'=' * 60}")
        print("\n  1. Open this URL on any device:")
        print(f"     {verification_url}\n")
        print("  2. Enter this code:")
        print(f"     {user_code}\n")
        print("  3. Authorize Gatekeeper to access your Google data.")
        print(f"\n  ⏳ Waiting for authorization (expires in {expires_in // 60} minutes)...")
        print(f"{'=' * 60}\n")

        # Step 3: Poll for token
        start_time = time.time()
        while time.time() - start_time < expires_in:
            time.sleep(interval)

            try:
                with httpx.Client(timeout=30) as client:
                    token_response = client.post(
                        GOOGLE_TOKEN_URL,
                        data={
                            "client_id": settings.google_client_id,
                            "client_secret": settings.google_client_secret,
                            "device_code": device_code,
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        },
                    )
                    token_data = token_response.json()

                    if token_response.status_code == 200:
                        # Success!
                        creds = Credentials(
                            token=token_data["access_token"],
                            refresh_token=token_data.get("refresh_token"),
                            token_uri=GOOGLE_TOKEN_URL,
                            client_id=settings.google_client_id,
                            client_secret=settings.google_client_secret,
                            scopes=scopes,
                        )
                        self._credentials = creds
                        self._save_credentials()

                        print(f"{'=' * 60}")
                        print("✅ Authorization successful!")
                        print(f"   Scopes: {', '.join(scopes)}")
                        print(f"   Token saved to: {self.token_path}")
                        print(f"{'=' * 60}\n")

                        logger.info("OAuth device flow completed successfully")
                        return creds

                    error = token_data.get("error")
                    if error == "authorization_pending":
                        # User hasn't authorized yet, keep polling
                        continue
                    elif error == "slow_down":
                        # Increase interval
                        interval += 5
                        continue
                    elif error == "expired_token":
                        print("\n❌ Authorization timed out. Please try again.\n")
                        return None
                    elif error == "access_denied":
                        print("\n❌ Authorization denied by user.\n")
                        return None
                    else:
                        logger.error(f"Unexpected token error: {error}")
                        print(f"\n❌ Authorization error: {error}\n")
                        return None

            except httpx.HTTPError as e:
                logger.warning(f"Token poll error (will retry): {e}")
                continue

        print("\n❌ Authorization timed out. Please try again.\n")
        return None

    def start_desktop_auth_flow(self, scopes: list[str] | None = None) -> Credentials | None:
        """Run the desktop OAuth flow (opens browser on local machine).

        This is the traditional OAuth flow — starts a local HTTP server,
        opens the browser, captures the redirect, and exchanges the code.
        Use this when running Gatekeeper on the same machine as your browser.

        Args:
            scopes: OAuth scopes to request. Defaults to all enabled module scopes.

        Returns:
            Valid credentials on success, None on failure.
        """
        from google_auth_oauthlib.flow import InstalledAppFlow

        if not settings.google_client_id or not settings.google_client_secret:
            logger.error("Google OAuth client ID/secret not configured")
            print("\n❌ ERROR: Set GATEKEEPER_GOOGLE_CLIENT_ID and GATEKEEPER_GOOGLE_CLIENT_SECRET")
            print("   Add them to your .env file or environment variables.\n")
            return None

        if scopes is None:
            scopes = self._get_enabled_scopes()

        if not scopes:
            scopes = [
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/calendar.readonly",
            ]

        client_config = {
            "installed": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": GOOGLE_AUTH_URL,
                "token_uri": GOOGLE_TOKEN_URL,
                "redirect_uris": ["http://localhost"],
            }
        }

        try:
            flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)
            creds = flow.run_local_server(port=0, open_browser=True)

            self._credentials = creds
            self._save_credentials()

            print(f"\n{'=' * 60}")
            print("✅ Authorization successful (desktop flow)!")
            print(f"   Scopes: {', '.join(scopes)}")
            print(f"   Token saved to: {self.token_path}")
            print(f"{'=' * 60}\n")

            logger.info("OAuth desktop flow completed successfully")
            return creds
        except Exception as e:
            logger.error(f"OAuth desktop flow failed: {e}")
            print(f"\n❌ OAuth flow failed: {e}\n")
            return None

    def start_auth_flow(
        self,
        flow: str = "device",
        scopes: list[str] | None = None,
    ) -> Credentials | None:
        """Run an OAuth authorization flow.

        Args:
            flow: Authorization flow to use.
                - "device" (default): Device Authorization flow — user visits a URL
                  and enters a code. Works from any device, no local browser needed.
                - "desktop": Opens browser on local machine, captures redirect automatically.
            scopes: OAuth scopes to request. Defaults to all enabled module scopes.

        Returns:
            Valid credentials on success, None on failure.
        """
        if flow == "desktop":
            return self.start_desktop_auth_flow(scopes=scopes)
        else:
            return self.start_device_auth_flow(scopes=scopes)

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
