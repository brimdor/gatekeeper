"""Tests for database models and encryption."""

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import select

from gatekeeper.db import Base


class TestEncryption:
    """Tests for Fernet encryption helpers."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypting then decrypting should return the original value."""
        from gatekeeper.encryption import encrypt_value, decrypt_value
        from gatekeeper.config import Settings

        fernet_key = Fernet.generate_key().decode()
        settings = Settings(
            _env_file=None,
            encryption_key=fernet_key,
            secret_key="test",
            admin_password="test",
        )
        settings.ensure_secrets()

        # Override the global settings
        import gatekeeper.encryption

        original_settings = gatekeeper.encryption.settings
        gatekeeper.encryption.settings = settings

        try:
            plaintext = "hello, this is a secret token"
            encrypted = encrypt_value(plaintext)
            decrypted = decrypt_value(encrypted)
            assert decrypted == plaintext
            assert encrypted != plaintext
        finally:
            gatekeeper.encryption.settings = original_settings

    def test_encrypt_produces_different_ciphertexts(self):
        """Two encryptions of the same plaintext should produce different ciphertexts (Fernet uses IV)."""
        from gatekeeper.encryption import encrypt_value
        from gatekeeper.config import Settings

        fernet_key = Fernet.generate_key().decode()
        settings = Settings(
            _env_file=None,
            encryption_key=fernet_key,
            secret_key="test",
            admin_password="test",
        )
        settings.ensure_secrets()

        import gatekeeper.encryption

        original_settings = gatekeeper.encryption.settings
        gatekeeper.encryption.settings = settings

        try:
            ct1 = encrypt_value("same plaintext")
            ct2 = encrypt_value("same plaintext")
            assert ct1 != ct2  # Fernet uses random IVs
        finally:
            gatekeeper.encryption.settings = original_settings

    def test_hex_key_backwards_compatibility(self):
        """Old hex-encoded keys should still work for decryption."""
        from gatekeeper.encryption import encrypt_value, decrypt_value
        from gatekeeper.config import Settings

        # Use old hex format key
        hex_key = "d" * 64
        settings = Settings(
            _env_file=None,
            encryption_key=hex_key,
            secret_key="test",
            admin_password="test",
        )
        settings.ensure_secrets()

        import gatekeeper.encryption

        original_settings = gatekeeper.encryption.settings
        gatekeeper.encryption.settings = settings

        try:
            plaintext = "test with old hex key"
            encrypted = encrypt_value(plaintext)
            decrypted = decrypt_value(encrypted)
            assert decrypted == plaintext
        finally:
            gatekeeper.encryption.settings = original_settings


@pytest.mark.asyncio
class TestDBModels:
    """Tests for SQLAlchemy ORM models."""

    async def test_api_key_create_and_query(self, db_session):
        """ApiKey should be creatable and queryable."""
        from gatekeeper.models import ApiKey

        raw, hash_val, prefix = ApiKey.generate_key()
        key = ApiKey(name="test-key", key_hash=hash_val, key_prefix=prefix, permissions="*")
        db_session.add(key)
        await db_session.commit()

        result = await db_session.execute(select(ApiKey).where(ApiKey.name == "test-key"))
        fetched = result.scalar_one()
        assert fetched.name == "test-key"
        assert fetched.key_prefix == prefix
        assert fetched.is_active is True
        assert fetched.permissions == "*"

    async def test_api_key_generate_key_format(self):
        """generate_key should produce keys with correct format."""
        from gatekeeper.models import ApiKey

        raw, hash_val, prefix = ApiKey.generate_key()
        assert raw.startswith("gkp_")
        assert len(raw) > 20  # prefix + 32 url-safe chars
        assert prefix.startswith("gkp_")
        assert len(prefix) == 12  # "gkp_" + 8 chars

    async def test_route_policy_create_and_query(self, db_session):
        """RoutePolicy should be creatable and queryable."""
        from gatekeeper.models import RoutePolicy

        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config='{"max_results": 50}',
            description="List Gmail messages",
        )
        db_session.add(policy)
        await db_session.commit()

        result = await db_session.execute(
            select(RoutePolicy).where(RoutePolicy.module == "gmail")
        )
        fetched = result.scalar_one()
        assert fetched.module == "gmail"
        assert fetched.route == "gmail.messages.list"
        assert fetched.enabled is True
        assert fetched.description == "List Gmail messages"

    async def test_audit_log_create_and_query(self, db_session):
        """AuditLog should be creatable and queryable."""
        from gatekeeper.models import AuditLog

        log = AuditLog(
            api_key_prefix="gkp_abcd1234",
            module="gmail",
            route="gmail.messages.list",
            method="GET",
            path="/api/v1/gmail/messages/list",
            status_code=200,
            response_summary="returned 20 messages",
        )
        db_session.add(log)
        await db_session.commit()

        result = await db_session.execute(select(AuditLog))
        fetched = result.scalar_one()
        assert fetched.api_key_prefix == "gkp_abcd1234"
        assert fetched.status_code == 200
        assert fetched.module == "gmail"

    async def test_google_token_create_and_query(self, db_session):
        """GoogleToken should be creatable and queryable."""
        from gatekeeper.models import GoogleToken

        token = GoogleToken(
            service="gmail",
            encrypted_token="some-encrypted-blob",
        )
        db_session.add(token)
        await db_session.commit()

        result = await db_session.execute(select(GoogleToken))
        fetched = result.scalar_one()
        assert fetched.service == "gmail"
        assert fetched.encrypted_token == "some-encrypted-blob"

    async def test_google_token_unique_service(self, db_session):
        """GoogleToken service field should be unique."""
        from gatekeeper.models import GoogleToken
        from sqlalchemy.exc import IntegrityError

        token1 = GoogleToken(service="drive", encrypted_token="blob1")
        token2 = GoogleToken(service="drive", encrypted_token="blob2")
        db_session.add(token1)
        await db_session.commit()
        db_session.add(token2)
        with pytest.raises(IntegrityError):
            await db_session.commit()