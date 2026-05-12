"""Fernet-based encryption helpers for storing Google OAuth tokens at rest."""

from __future__ import annotations

from cryptography.fernet import Fernet

from gatekeeper.config import settings


def _get_fernet() -> Fernet:
    """Get a Fernet instance configured with the current encryption key.

    The encryption_key is now stored as a proper Fernet key (base64-encoded
    32 bytes), so it can be used directly. For backwards compatibility with
    old hex-encoded keys, we detect the format and convert if needed.
    """
    key = settings.encryption_key

    # If it's 64 hex chars (old format), convert to Fernet key
    if len(key) == 64 and all(c in "0123456789abcdefABCDEF" for c in key):
        import base64
        raw_bytes = bytes.fromhex(key)
        fernet_key = base64.urlsafe_b64encode(raw_bytes)
        return Fernet(fernet_key)

    # Otherwise assume it's already a Fernet key (base64-encoded)
    return Fernet(key.encode())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value using Fernet.

    Args:
        plaintext: The string to encrypt.

    Returns:
        Base64-encoded encrypted string.
    """
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted string.

    Args:
        ciphertext: The base64-encoded encrypted string.

    Returns:
        The decrypted plaintext string.
    """
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()