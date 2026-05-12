"""Fernet-based encryption helpers for storing Google OAuth tokens at rest."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from gatekeeper.config import settings


def derive_fernet_key(hex_key: str) -> bytes:
    """Derive a Fernet-compatible key from a hex-encoded string.
    
    Fernet requires a 32-byte key, url-safe base64-encoded.
    We take the 64-char hex string (32 bytes) and base64-encode it
    to produce a valid Fernet key.
    """
    raw_bytes = bytes.fromhex(hex_key)
    # Fernet key must be 32 url-safe base64-encoded bytes
    return base64.urlsafe_b64encode(raw_bytes)


def _get_fernet() -> Fernet:
    """Get a Fernet instance configured with the current encryption key."""
    key = derive_fernet_key(settings.encryption_key)
    return Fernet(key)


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