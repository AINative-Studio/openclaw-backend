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
    # Only create the user_api_keys table to avoid SQLite/PostgreSQL ARRAY incompatibility
    UserAPIKey.__table__.create(engine, checkfirst=True)
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


class TestGroqProviderSupport:
    """Test Groq provider support (Issue #119)."""

    def test_add_groq_key_success(self, service, workspace_id):
        """Test adding a Groq API key."""
        plaintext_key = "gsk_test_groq_key_12345678901234567890"

        user_api_key = service.add_key(
            workspace_id=workspace_id,
            provider="groq",
            plaintext_key=plaintext_key,
            validate=False
        )

        assert user_api_key.provider == "groq"
        assert user_api_key.encrypted_key != plaintext_key
        assert user_api_key.is_active is True

    def test_get_groq_key_success(self, service, workspace_id):
        """Test retrieving a Groq API key."""
        plaintext_key = "gsk_test_groq_key_12345678901234567890"

        service.add_key(workspace_id, "groq", plaintext_key, validate=False)
        retrieved_key = service.get_key(workspace_id, "groq")

        assert retrieved_key == plaintext_key

    def test_mask_groq_key(self, service):
        """Test key masking for Groq keys."""
        key = "gsk_abcdefghijklmnopqrstuvwxyz1234"
        masked = service.mask_key(key)

        assert masked == "gsk_***...1234"
        assert "abcdefghijklmnopqrstuvwxyz" not in masked

    def test_validate_groq_key_invalid(self, service):
        """Test validating an invalid Groq API key."""
        is_valid, message = service.validate_key("groq", "gsk_invalid_key_12345")

        assert is_valid is False
        # Can be either "not installed" or "invalid" depending on whether SDK is available
        assert any(word in message.lower() for word in ["fail", "invalid", "not installed", "install"])

    @pytest.mark.skipif(
        not os.getenv("GROQ_API_KEY"),
        reason="GROQ_API_KEY not set - skipping live API test"
    )
    def test_validate_groq_key_valid(self, service):
        """Test validating a valid Groq API key (requires real key)."""
        api_key = os.getenv("GROQ_API_KEY")
        is_valid, message = service.validate_key("groq", api_key)

        assert is_valid is True
        assert "valid" in message.lower() or "authenticated" in message.lower()

    def test_add_groq_key_with_validation_invalid_raises_error(self, service, workspace_id):
        """Test that adding Groq key with validation=True rejects invalid keys."""
        with pytest.raises(ValueError, match="validation failed"):
            service.add_key(
                workspace_id=workspace_id,
                provider="groq",
                plaintext_key="gsk_invalid_key_12345",
                validate=True
            )

    def test_update_groq_key_success(self, service, workspace_id):
        """Test updating a Groq API key."""
        old_key = "gsk_old_key_12345678901234567890"
        new_key = "gsk_new_key_98765432109876543210"

        service.add_key(workspace_id, "groq", old_key, validate=False)
        service.update_key(workspace_id, "groq", new_key, validate=False)

        retrieved = service.get_key(workspace_id, "groq")
        assert retrieved == new_key


class TestMistralProviderSupport:
    """Test Mistral provider support (Issue #119)."""

    def test_add_mistral_key_success(self, service, workspace_id):
        """Test adding a Mistral API key."""
        plaintext_key = "msk_test_mistral_key_12345678901234567890"

        user_api_key = service.add_key(
            workspace_id=workspace_id,
            provider="mistral",
            plaintext_key=plaintext_key,
            validate=False
        )

        assert user_api_key.provider == "mistral"
        assert user_api_key.encrypted_key != plaintext_key
        assert user_api_key.is_active is True

    def test_get_mistral_key_success(self, service, workspace_id):
        """Test retrieving a Mistral API key."""
        plaintext_key = "msk_test_mistral_key_12345678901234567890"

        service.add_key(workspace_id, "mistral", plaintext_key, validate=False)
        retrieved_key = service.get_key(workspace_id, "mistral")

        assert retrieved_key == plaintext_key

    def test_mask_mistral_key(self, service):
        """Test key masking for Mistral keys."""
        key = "msk_abcdefghijklmnopqrstuvwxyz1234"
        masked = service.mask_key(key)

        assert masked == "msk_***...1234"
        assert "abcdefghijklmnopqrstuvwxyz" not in masked

    def test_validate_mistral_key_invalid(self, service):
        """Test validating an invalid Mistral API key."""
        is_valid, message = service.validate_key("mistral", "msk_invalid_key_12345")

        assert is_valid is False
        # Can be either "not installed" or "invalid" depending on whether SDK is available
        assert any(word in message.lower() for word in ["fail", "invalid", "not installed", "install"])

    @pytest.mark.skipif(
        not os.getenv("MISTRAL_API_KEY"),
        reason="MISTRAL_API_KEY not set - skipping live API test"
    )
    def test_validate_mistral_key_valid(self, service):
        """Test validating a valid Mistral API key (requires real key)."""
        api_key = os.getenv("MISTRAL_API_KEY")
        is_valid, message = service.validate_key("mistral", api_key)

        assert is_valid is True
        assert "valid" in message.lower() or "authenticated" in message.lower()

    def test_add_mistral_key_with_validation_invalid_raises_error(self, service, workspace_id):
        """Test that adding Mistral key with validation=True rejects invalid keys."""
        with pytest.raises(ValueError, match="validation failed"):
            service.add_key(
                workspace_id=workspace_id,
                provider="mistral",
                plaintext_key="msk_invalid_key_12345",
                validate=True
            )

    def test_update_mistral_key_success(self, service, workspace_id):
        """Test updating a Mistral API key."""
        old_key = "msk_old_key_12345678901234567890"
        new_key = "msk_new_key_98765432109876543210"

        service.add_key(workspace_id, "mistral", old_key, validate=False)
        service.update_key(workspace_id, "mistral", new_key, validate=False)

        retrieved = service.get_key(workspace_id, "mistral")
        assert retrieved == new_key


class TestOllamaProviderSupport:
    """Test Ollama provider support (Issue #119)."""

    def test_add_ollama_connection_success(self, service, workspace_id):
        """Test adding Ollama connection string (no API key needed for local)."""
        connection_string = "http://localhost:11434"

        user_api_key = service.add_key(
            workspace_id=workspace_id,
            provider="ollama",
            plaintext_key=connection_string,
            validate=False
        )

        assert user_api_key.provider == "ollama"
        assert user_api_key.encrypted_key != connection_string
        assert user_api_key.is_active is True

    def test_get_ollama_connection_success(self, service, workspace_id):
        """Test retrieving Ollama connection string."""
        connection_string = "http://localhost:11434"

        service.add_key(workspace_id, "ollama", connection_string, validate=False)
        retrieved = service.get_key(workspace_id, "ollama")

        assert retrieved == connection_string

    def test_mask_ollama_connection(self, service):
        """Test masking Ollama connection strings."""
        connection = "http://localhost:11434"
        masked = service.mask_key(connection)

        # URLs don't have a prefix separator, so they'll be masked as ***...1434
        assert masked == "***...1434"
        assert "localhost" not in masked

    def test_validate_ollama_connection_invalid(self, service):
        """Test validating an invalid Ollama connection."""
        is_valid, message = service.validate_key("ollama", "http://invalid-host:99999")

        assert is_valid is False
        assert any(word in message.lower() for word in ["fail", "connection", "connect"])

    def test_validate_ollama_connection_valid_with_running_instance(self, service):
        """Test validating Ollama connection when instance is running (integration test)."""
        # This test will skip if Ollama is not running locally
        try:
            import httpx
            response = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
            ollama_running = response.status_code == 200
        except:
            ollama_running = False

        if not ollama_running:
            pytest.skip("Ollama not running on localhost:11434")

        is_valid, message = service.validate_key("ollama", "http://localhost:11434")
        assert is_valid is True
        assert "valid" in message.lower() or "connected" in message.lower()

    def test_add_ollama_with_validation_invalid_raises_error(self, service, workspace_id):
        """Test that adding Ollama connection with validation=True rejects invalid connections."""
        with pytest.raises(ValueError, match="validation failed"):
            service.add_key(
                workspace_id=workspace_id,
                provider="ollama",
                plaintext_key="http://invalid-host:99999",
                validate=True
            )

    def test_update_ollama_connection_success(self, service, workspace_id):
        """Test updating Ollama connection string."""
        old_connection = "http://localhost:11434"
        new_connection = "http://192.168.1.100:11434"

        service.add_key(workspace_id, "ollama", old_connection, validate=False)
        service.update_key(workspace_id, "ollama", new_connection, validate=False)

        retrieved = service.get_key(workspace_id, "ollama")
        assert retrieved == new_connection

    def test_ollama_supports_custom_ports(self, service, workspace_id):
        """Test that Ollama supports custom ports and hosts."""
        custom_connections = [
            "http://localhost:11434",
            "http://127.0.0.1:11434",
            "http://192.168.1.100:8080",
            "https://ollama.example.com:443"
        ]

        for i, connection in enumerate(custom_connections):
            ws_id = f"{workspace_id}-{i}"
            user_api_key = service.add_key(
                workspace_id=ws_id,
                provider="ollama",
                plaintext_key=connection,
                validate=False
            )
            assert user_api_key.provider == "ollama"
            retrieved = service.get_key(ws_id, "ollama")
            assert retrieved == connection


class TestMultiProviderSupport:
    """Test handling multiple providers in the same workspace."""

    def test_add_all_providers_in_same_workspace(self, service, workspace_id):
        """Test adding all supported providers (including new ones) to same workspace."""
        providers_and_keys = {
            "anthropic": "sk-ant-test-key-12345",
            "openai": "sk-proj-test-key-67890",
            "cohere": "co-test-key-abcde",
            "huggingface": "hf_test_key_fghij",
            "google": "AIza-test-key-klmno",
            "groq": "gsk_test_key_12345",
            "mistral": "msk_test_key_67890",
            "ollama": "http://localhost:11434"
        }

        for provider, key in providers_and_keys.items():
            service.add_key(workspace_id, provider, key, validate=False)

        # Verify all keys were added
        keys = service.list_keys(workspace_id)
        assert len(keys) == 8

        providers_in_db = {key.provider for key in keys}
        assert providers_in_db == set(providers_and_keys.keys())

    def test_get_specific_provider_from_multi_provider_workspace(self, service, workspace_id):
        """Test retrieving specific provider keys from workspace with multiple providers."""
        service.add_key(workspace_id, "groq", "gsk_test_key_12345", validate=False)
        service.add_key(workspace_id, "mistral", "msk_test_key_67890", validate=False)
        service.add_key(workspace_id, "ollama", "http://localhost:11434", validate=False)

        groq_key = service.get_key(workspace_id, "groq")
        mistral_key = service.get_key(workspace_id, "mistral")
        ollama_connection = service.get_key(workspace_id, "ollama")

        assert groq_key == "gsk_test_key_12345"
        assert mistral_key == "msk_test_key_67890"
        assert ollama_connection == "http://localhost:11434"
