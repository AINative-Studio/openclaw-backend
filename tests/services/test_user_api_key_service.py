"""
Unit tests for UserAPIKeyService (Issue #96)

Tests encryption, decryption, CRUD operations, and key validation.
Uses SQLite in-memory database for isolation.
"""

import pytest
import os
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from uuid import uuid4

from backend.db.base_class import Base
from backend.models.user_api_key import UserAPIKey
from backend.services.user_api_key_service import UserAPIKeyService


# Generate a test encryption key
TEST_ENCRYPTION_SECRET = Fernet.generate_key().decode()


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    """Create UserAPIKeyService with test encryption secret."""
    return UserAPIKeyService(db_session, encryption_secret=TEST_ENCRYPTION_SECRET)


@pytest.fixture
def workspace_id():
    """Generate a test workspace ID."""
    return str(uuid4())


class TestUserAPIKeyServiceEncryption:
    """Test encryption and decryption functionality."""

    def test_encrypt_key(self, service):
        """Test basic key encryption."""
        plaintext = "sk-ant-test-key-12345"
        encrypted = service.encrypt_key(plaintext)

        assert encrypted != plaintext
        assert isinstance(encrypted, str)
        assert len(encrypted) > len(plaintext)  # Encrypted is longer

    def test_decrypt_key(self, service):
        """Test basic key decryption."""
        plaintext = "sk-ant-test-key-12345"
        encrypted = service.encrypt_key(plaintext)
        decrypted = service.decrypt_key(encrypted)

        assert decrypted == plaintext

    def test_encryption_is_deterministic_with_random_iv(self, service):
        """Test that each encryption produces different ciphertext (due to random IV)."""
        plaintext = "sk-ant-test-key-12345"
        encrypted1 = service.encrypt_key(plaintext)
        encrypted2 = service.encrypt_key(plaintext)

        # Same plaintext should produce different ciphertext (Fernet uses random IV)
        assert encrypted1 != encrypted2
        # But both should decrypt to same plaintext
        assert service.decrypt_key(encrypted1) == plaintext
        assert service.decrypt_key(encrypted2) == plaintext

    def test_decrypt_invalid_key_raises_error(self, service):
        """Test that decrypting invalid ciphertext raises ValueError."""
        with pytest.raises(ValueError, match="Failed to decrypt"):
            service.decrypt_key("invalid-ciphertext")

    def test_mask_key_anthropic(self, service):
        """Test key masking for Anthropic keys."""
        key = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234"
        masked = service.mask_key(key)

        assert masked == "sk-***...1234"
        assert "abcdefghijklmnopqrstuvwxyz" not in masked

    def test_mask_key_openai(self, service):
        """Test key masking for OpenAI keys."""
        key = "sk-proj-abcdefghijklmnopqrstuvwxyz1234"
        masked = service.mask_key(key)

        assert masked == "sk-***...1234"

    def test_mask_key_short(self, service):
        """Test key masking for very short keys."""
        key = "abc"
        masked = service.mask_key(key)

        assert masked == "***"

    def test_mask_key_no_prefix(self, service):
        """Test key masking for keys without prefix."""
        key = "abcdefghijklmnopqrstuvwxyz1234"
        masked = service.mask_key(key)

        assert masked == "***...1234"


class TestUserAPIKeyServiceCRUD:
    """Test CRUD operations for user API keys."""

    def test_add_key_success(self, service, workspace_id):
        """Test adding a new API key."""
        plaintext_key = "sk-ant-test-key-12345"

        user_api_key = service.add_key(
            workspace_id=workspace_id,
            provider="anthropic",
            plaintext_key=plaintext_key,
            validate=False
        )

        assert user_api_key.id is not None
        assert user_api_key.workspace_id == workspace_id
        assert user_api_key.provider == "anthropic"
        assert user_api_key.encrypted_key != plaintext_key
        assert user_api_key.key_hash == UserAPIKey.compute_key_hash(plaintext_key)
        assert user_api_key.is_active is True

    def test_add_key_duplicate_raises_error(self, service, workspace_id):
        """Test that adding duplicate key raises ValueError."""
        plaintext_key = "sk-ant-test-key-12345"

        # Add first key
        service.add_key(
            workspace_id=workspace_id,
            provider="anthropic",
            plaintext_key=plaintext_key,
            validate=False
        )

        # Try to add duplicate
        with pytest.raises(ValueError, match="already exists"):
            service.add_key(
                workspace_id=workspace_id,
                provider="anthropic",
                plaintext_key=plaintext_key,
                validate=False
            )

    def test_add_key_unsupported_provider_raises_error(self, service, workspace_id):
        """Test that unsupported provider raises ValueError."""
        with pytest.raises(ValueError, match="not supported"):
            service.add_key(
                workspace_id=workspace_id,
                provider="unsupported-provider",
                plaintext_key="test-key",
                validate=False
            )

    def test_get_key_success(self, service, workspace_id):
        """Test retrieving a decrypted API key."""
        plaintext_key = "sk-ant-test-key-12345"

        # Add key
        service.add_key(
            workspace_id=workspace_id,
            provider="anthropic",
            plaintext_key=plaintext_key,
            validate=False
        )

        # Get key
        retrieved_key = service.get_key(workspace_id, "anthropic")

        assert retrieved_key == plaintext_key

    def test_get_key_not_found_returns_none(self, service, workspace_id):
        """Test that getting non-existent key returns None."""
        retrieved_key = service.get_key(workspace_id, "anthropic")

        assert retrieved_key is None

    def test_get_key_inactive_returns_none(self, service, workspace_id, db_session):
        """Test that getting inactive key returns None."""
        plaintext_key = "sk-ant-test-key-12345"

        # Add key
        user_api_key = service.add_key(
            workspace_id=workspace_id,
            provider="anthropic",
            plaintext_key=plaintext_key,
            validate=False
        )

        # Mark as inactive
        user_api_key.is_active = False
        db_session.commit()

        # Get key
        retrieved_key = service.get_key(workspace_id, "anthropic")

        assert retrieved_key is None

    def test_list_keys_success(self, service, workspace_id):
        """Test listing all keys for a workspace."""
        # Add multiple keys
        service.add_key(workspace_id, "anthropic", "sk-ant-key-1", validate=False)
        service.add_key(workspace_id, "openai", "sk-proj-key-2", validate=False)

        # List keys
        keys = service.list_keys(workspace_id)

        assert len(keys) == 2
        providers = {key.provider for key in keys}
        assert providers == {"anthropic", "openai"}

    def test_list_keys_different_workspaces(self, service):
        """Test that list_keys only returns keys for specified workspace."""
        workspace1 = str(uuid4())
        workspace2 = str(uuid4())

        service.add_key(workspace1, "anthropic", "sk-ant-key-1", validate=False)
        service.add_key(workspace2, "openai", "sk-proj-key-2", validate=False)

        # List keys for workspace1
        keys1 = service.list_keys(workspace1)
        assert len(keys1) == 1
        assert keys1[0].provider == "anthropic"

        # List keys for workspace2
        keys2 = service.list_keys(workspace2)
        assert len(keys2) == 1
        assert keys2[0].provider == "openai"

    def test_update_key_success(self, service, workspace_id):
        """Test updating an existing API key."""
        original_key = "sk-ant-old-key-12345"
        new_key = "sk-ant-new-key-67890"

        # Add key
        service.add_key(workspace_id, "anthropic", original_key, validate=False)

        # Update key
        updated = service.update_key(workspace_id, "anthropic", new_key, validate=False)

        assert updated.key_hash == UserAPIKey.compute_key_hash(new_key)

        # Verify decryption
        retrieved = service.get_key(workspace_id, "anthropic")
        assert retrieved == new_key

    def test_update_key_not_found_raises_error(self, service, workspace_id):
        """Test that updating non-existent key raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            service.update_key(workspace_id, "anthropic", "new-key", validate=False)

    def test_delete_key_success(self, service, workspace_id):
        """Test deleting an API key."""
        # Add key
        service.add_key(workspace_id, "anthropic", "sk-ant-key", validate=False)

        # Delete key
        deleted = service.delete_key(workspace_id, "anthropic")

        assert deleted is True

        # Verify deleted
        retrieved = service.get_key(workspace_id, "anthropic")
        assert retrieved is None

    def test_delete_key_not_found_returns_false(self, service, workspace_id):
        """Test that deleting non-existent key returns False."""
        deleted = service.delete_key(workspace_id, "anthropic")

        assert deleted is False

    def test_delete_key_by_id_success(self, service, workspace_id):
        """Test deleting an API key by ID."""
        # Add key
        user_api_key = service.add_key(
            workspace_id, "anthropic", "sk-ant-key", validate=False
        )

        # Delete by ID
        deleted = service.delete_key_by_id(str(user_api_key.id))

        assert deleted is True

        # Verify deleted
        retrieved = service.get_key(workspace_id, "anthropic")
        assert retrieved is None

    def test_delete_key_by_id_not_found_returns_false(self, service):
        """Test that deleting non-existent key by ID returns False."""
        fake_id = str(uuid4())
        deleted = service.delete_key_by_id(fake_id)

        assert deleted is False


class TestUserAPIKeyServiceValidation:
    """Test API key validation against real provider APIs."""

    def test_validate_key_unsupported_provider_raises_error(self, service):
        """Test that validating unsupported provider raises ValueError."""
        with pytest.raises(ValueError, match="not supported"):
            service.validate_key("unsupported-provider", "test-key")

    @pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set - skipping live API test"
    )
    def test_validate_anthropic_key_valid(self, service):
        """Test validating a valid Anthropic API key (requires real key)."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        is_valid, message = service.validate_key("anthropic", api_key)

        assert is_valid is True
        assert "valid" in message.lower() or "authenticated" in message.lower()

    def test_validate_anthropic_key_invalid(self, service):
        """Test validating an invalid Anthropic API key."""
        is_valid, message = service.validate_key("anthropic", "sk-ant-invalid-key-12345")

        assert is_valid is False
        assert "fail" in message.lower() or "invalid" in message.lower()

    def test_add_key_with_validation_invalid_key_raises_error(self, service, workspace_id):
        """Test that adding key with validation=True rejects invalid keys."""
        with pytest.raises(ValueError, match="validation failed"):
            service.add_key(
                workspace_id=workspace_id,
                provider="anthropic",
                plaintext_key="sk-ant-invalid-key-12345",
                validate=True
            )


class TestUserAPIKeyServiceInitialization:
    """Test service initialization and error handling."""

    def test_init_without_encryption_secret_raises_error(self, db_session):
        """Test that initializing without encryption secret raises ValueError."""
        # Clear environment variable
        old_secret = os.environ.pop("ENCRYPTION_SECRET", None)

        try:
            with pytest.raises(ValueError, match="ENCRYPTION_SECRET"):
                UserAPIKeyService(db_session, encryption_secret=None)
        finally:
            # Restore environment variable
            if old_secret:
                os.environ["ENCRYPTION_SECRET"] = old_secret

    def test_init_with_invalid_encryption_secret_raises_error(self, db_session):
        """Test that initializing with invalid encryption secret raises ValueError."""
        with pytest.raises(ValueError, match="Invalid encryption secret"):
            UserAPIKeyService(db_session, encryption_secret="not-base64-fernet-key")

    def test_init_with_env_var_encryption_secret(self, db_session):
        """Test initializing with ENCRYPTION_SECRET from environment."""
        old_secret = os.environ.get("ENCRYPTION_SECRET")
        os.environ["ENCRYPTION_SECRET"] = TEST_ENCRYPTION_SECRET

        try:
            service = UserAPIKeyService(db_session, encryption_secret=None)
            assert service.cipher is not None
        finally:
            if old_secret:
                os.environ["ENCRYPTION_SECRET"] = old_secret
            else:
                os.environ.pop("ENCRYPTION_SECRET", None)


class TestUserAPIKeyModelMethods:
    """Test UserAPIKey model methods."""

    def test_compute_key_hash(self):
        """Test SHA-256 hash computation."""
        key = "sk-ant-test-key-12345"
        hash1 = UserAPIKey.compute_key_hash(key)
        hash2 = UserAPIKey.compute_key_hash(key)

        assert len(hash1) == 64  # SHA-256 is 64 hex chars
        assert hash1 == hash2  # Same key produces same hash

    def test_compute_key_hash_different_keys(self):
        """Test that different keys produce different hashes."""
        key1 = "sk-ant-test-key-1"
        key2 = "sk-ant-test-key-2"

        hash1 = UserAPIKey.compute_key_hash(key1)
        hash2 = UserAPIKey.compute_key_hash(key2)

        assert hash1 != hash2

    def test_repr_does_not_expose_key(self):
        """Test that __repr__ does not expose sensitive data."""
        key_record = UserAPIKey(
            workspace_id="test-workspace",
            provider="anthropic",
            encrypted_key="encrypted-data",
            key_hash="hash-value",
            is_active=True
        )

        repr_str = repr(key_record)

        assert "encrypted-data" not in repr_str
        assert "hash-value" not in repr_str
        assert "test-workspace" in repr_str
        assert "anthropic" in repr_str
