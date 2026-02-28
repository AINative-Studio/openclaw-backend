"""
Test suite for API Key Management endpoints (Issue #83)

Tests cover:
- Encryption/decryption of API keys
- CRUD operations for API keys
- Key masking in responses
- API key verification against real services
- Security (no plaintext keys in logs/responses)
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from cryptography.fernet import Fernet
import uuid

from backend.main import app
from backend.db.base_class import Base
from backend.db.base import get_db
from backend.models.api_key import APIKey
from backend.services.api_key_service import APIKeyService


# Test database setup
TEST_DATABASE_URL = "sqlite:///./test_api_keys.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Create test database session."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Create test client with overridden database dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def encryption_key():
    """Generate test encryption key."""
    return Fernet.generate_key()


@pytest.fixture(scope="function")
def api_key_service(db_session, encryption_key, monkeypatch):
    """Create APIKeyService instance with test encryption key."""
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())
    return APIKeyService(db_session)


class TestAPIKeyEncryption:
    """Test encryption and decryption functionality."""

    def test_encrypt_decrypt_roundtrip(self, api_key_service):
        """Test that encryption and decryption are reversible."""
        original_key = "sk-ant-test-key-12345678"
        encrypted = api_key_service.encrypt_key(original_key)

        assert encrypted != original_key.encode()
        assert isinstance(encrypted, bytes)

        decrypted = api_key_service.decrypt_key(encrypted)
        assert decrypted == original_key

    def test_different_keys_produce_different_ciphertext(self, api_key_service):
        """Test that same plaintext produces different ciphertext (IV randomization)."""
        key1 = "sk-test-key"
        encrypted1 = api_key_service.encrypt_key(key1)
        encrypted2 = api_key_service.encrypt_key(key1)

        # Fernet includes random IV, so same plaintext -> different ciphertext
        assert encrypted1 != encrypted2

        # But both decrypt to same value
        assert api_key_service.decrypt_key(encrypted1) == key1
        assert api_key_service.decrypt_key(encrypted2) == key1

    def test_mask_key_shows_last_four_chars(self, api_key_service):
        """Test key masking shows only last 4 characters."""
        key = "sk-ant-api-key-abcd1234"
        masked = api_key_service.mask_key(key)
        assert masked == "sk-...1234"

    def test_mask_short_key(self, api_key_service):
        """Test masking of keys shorter than 4 characters."""
        key = "abc"
        masked = api_key_service.mask_key(key)
        assert masked == "***"

    def test_mask_empty_key(self, api_key_service):
        """Test masking empty string."""
        masked = api_key_service.mask_key("")
        assert masked == "***"


class TestCreateAPIKey:
    """Test POST /api/v1/api-keys endpoint."""

    def test_create_api_key_success(self, client, db_session, monkeypatch, encryption_key):
        """Test successful API key creation."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        payload = {
            "service_name": "anthropic",
            "api_key": "sk-ant-test-key-12345678"
        }

        response = client.post("/api/v1/api-keys", json=payload)

        assert response.status_code == 201
        data = response.json()

        assert data["service_name"] == "anthropic"
        assert data["masked_key"] == "sk-...5678"
        assert data["is_active"] is True
        assert "created_at" in data
        assert "updated_at" in data
        assert "api_key" not in data  # Never return plaintext key

        # Verify key is encrypted in database
        db_key = db_session.query(APIKey).filter_by(service_name="anthropic").first()
        assert db_key is not None
        assert db_key.encrypted_key != payload["api_key"].encode()
        assert isinstance(db_key.encrypted_key, bytes)

    def test_create_duplicate_service_name_fails(self, client, db_session, monkeypatch, encryption_key):
        """Test that creating duplicate service name fails."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        payload = {
            "service_name": "openai",
            "api_key": "sk-test-key-1"
        }

        # First creation succeeds
        response1 = client.post("/api/v1/api-keys", json=payload)
        assert response1.status_code == 201

        # Second creation with same service_name fails
        payload2 = {
            "service_name": "openai",
            "api_key": "sk-test-key-2"
        }
        response2 = client.post("/api/v1/api-keys", json=payload2)
        assert response2.status_code == 400
        assert "already exists" in response2.json()["detail"].lower()

    def test_create_invalid_service_name(self, client, monkeypatch, encryption_key):
        """Test validation of service name."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        payload = {
            "service_name": "invalid_service",
            "api_key": "sk-test-key"
        }

        response = client.post("/api/v1/api-keys", json=payload)
        assert response.status_code == 422  # Validation error

    def test_create_missing_encryption_key_env_var(self, client, monkeypatch):
        """Test that missing encryption key env var returns 500."""
        monkeypatch.delenv("API_KEY_ENCRYPTION_KEY", raising=False)

        payload = {
            "service_name": "anthropic",
            "api_key": "sk-test-key"
        }

        response = client.post("/api/v1/api-keys", json=payload)
        assert response.status_code == 500
        assert "encryption" in response.json()["detail"].lower()


class TestListAPIKeys:
    """Test GET /api/v1/api-keys endpoint."""

    def test_list_empty_keys(self, client):
        """Test listing when no keys are configured."""
        response = client.get("/api/v1/api-keys")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_keys_returns_masked_values(self, client, db_session, monkeypatch, encryption_key):
        """Test that list endpoint returns masked keys."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        # Create multiple keys
        services = [
            ("anthropic", "sk-ant-key-abcd1234"),
            ("openai", "sk-openai-key-xyz9876"),
            ("cohere", "co-test-key-999")
        ]

        for service, key in services:
            client.post("/api/v1/api-keys", json={"service_name": service, "api_key": key})

        response = client.get("/api/v1/api-keys")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 3

        # Verify masking
        anthropic_key = next(k for k in data if k["service_name"] == "anthropic")
        assert anthropic_key["masked_key"] == "sk-...1234"

        openai_key = next(k for k in data if k["service_name"] == "openai")
        assert openai_key["masked_key"] == "sk-...9876"

        # Verify no plaintext keys in response
        for key_data in data:
            assert "api_key" not in key_data
            assert "encrypted_key" not in key_data

    def test_list_keys_shows_active_status(self, client, db_session, monkeypatch, encryption_key):
        """Test that list endpoint shows is_active status."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        client.post("/api/v1/api-keys", json={"service_name": "anthropic", "api_key": "sk-test"})

        # Manually deactivate key
        db_key = db_session.query(APIKey).filter_by(service_name="anthropic").first()
        db_key.is_active = False
        db_session.commit()

        response = client.get("/api/v1/api-keys")
        data = response.json()

        assert len(data) == 1
        assert data[0]["is_active"] is False


class TestUpdateAPIKey:
    """Test PUT /api/v1/api-keys/{service_name} endpoint."""

    def test_update_existing_key(self, client, db_session, monkeypatch, encryption_key):
        """Test updating an existing API key."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        # Create initial key
        client.post("/api/v1/api-keys", json={"service_name": "anthropic", "api_key": "sk-old-key"})

        # Update key
        response = client.put(
            "/api/v1/api-keys/anthropic",
            json={"api_key": "sk-new-key-abcd9999"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["service_name"] == "anthropic"
        assert data["masked_key"] == "sk-...9999"

        # Verify key is updated in database
        service = APIKeyService(db_session)
        decrypted = service.get_decrypted_key("anthropic")
        assert decrypted == "sk-new-key-abcd9999"

    def test_update_nonexistent_key_fails(self, client, monkeypatch, encryption_key):
        """Test updating a key that doesn't exist."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        response = client.put(
            "/api/v1/api-keys/nonexistent",
            json={"api_key": "sk-test-key"}
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_update_preserves_created_at(self, client, db_session, monkeypatch, encryption_key):
        """Test that update doesn't change created_at timestamp."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        # Create key
        create_response = client.post("/api/v1/api-keys", json={"service_name": "openai", "api_key": "sk-old"})
        original_created_at = create_response.json()["created_at"]

        # Update key
        update_response = client.put("/api/v1/api-keys/openai", json={"api_key": "sk-new"})

        assert update_response.json()["created_at"] == original_created_at
        assert update_response.json()["updated_at"] != original_created_at


class TestDeleteAPIKey:
    """Test DELETE /api/v1/api-keys/{service_name} endpoint."""

    def test_delete_existing_key(self, client, db_session, monkeypatch, encryption_key):
        """Test deleting an existing API key."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        # Create key
        client.post("/api/v1/api-keys", json={"service_name": "cohere", "api_key": "co-test-key"})

        # Delete key
        response = client.delete("/api/v1/api-keys/cohere")
        assert response.status_code == 204

        # Verify key is deleted
        db_key = db_session.query(APIKey).filter_by(service_name="cohere").first()
        assert db_key is None

    def test_delete_nonexistent_key_fails(self, client, monkeypatch, encryption_key):
        """Test deleting a key that doesn't exist."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        response = client.delete("/api/v1/api-keys/nonexistent")
        assert response.status_code == 404


class TestVerifyAPIKey:
    """Test GET /api/v1/api-keys/{service_name}/verify endpoint."""

    @patch("anthropic.Anthropic")
    def test_verify_anthropic_key_valid(self, mock_anthropic_class, client, monkeypatch, encryption_key):
        """Test verification of valid Anthropic API key."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        # Mock Anthropic client
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        mock_client.models.list.return_value = Mock(data=[{"id": "claude-3"}])

        # Create key
        client.post("/api/v1/api-keys", json={"service_name": "anthropic", "api_key": "sk-ant-test"})

        # Verify key
        response = client.get("/api/v1/api-keys/anthropic/verify")

        assert response.status_code == 200
        data = response.json()
        assert data["service_name"] == "anthropic"
        assert data["is_valid"] is True
        assert "message" in data

        # Verify API was called
        mock_anthropic_class.assert_called_once_with(api_key="sk-ant-test")
        mock_client.models.list.assert_called_once()

    @patch("anthropic.Anthropic")
    def test_verify_anthropic_key_invalid(self, mock_anthropic_class, client, monkeypatch, encryption_key):
        """Test verification of invalid Anthropic API key."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        # Mock Anthropic client to raise auth error
        mock_anthropic_class.side_effect = Exception("Invalid API key")

        # Create key
        client.post("/api/v1/api-keys", json={"service_name": "anthropic", "api_key": "sk-bad-key"})

        # Verify key
        response = client.get("/api/v1/api-keys/anthropic/verify")

        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is False
        assert "error" in data or "message" in data

    @patch("openai.OpenAI")
    def test_verify_openai_key_valid(self, mock_openai_class, client, monkeypatch, encryption_key):
        """Test verification of valid OpenAI API key."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        # Mock OpenAI client
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.models.list.return_value = Mock(data=[{"id": "gpt-4"}])

        # Create key
        client.post("/api/v1/api-keys", json={"service_name": "openai", "api_key": "sk-openai-test"})

        # Verify key
        response = client.get("/api/v1/api-keys/openai/verify")

        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True

    def test_verify_nonexistent_key_fails(self, client, monkeypatch, encryption_key):
        """Test verifying a key that doesn't exist."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        # Valid service name but key doesn't exist
        response = client.get("/api/v1/api-keys/anthropic/verify")
        assert response.status_code == 404

    def test_verify_unsupported_service(self, client, db_session, monkeypatch, encryption_key):
        """Test verification fails gracefully for unsupported services."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        # Try to verify with unsupported service name
        # FastAPI validation will reject with 422 (Unprocessable Entity)
        response = client.get("/api/v1/api-keys/unsupported_service/verify")
        assert response.status_code == 422  # Pydantic validation error
        assert "detail" in response.json()


class TestAPIKeySecurity:
    """Test security aspects of API key management."""

    def test_no_plaintext_keys_in_database(self, client, db_session, monkeypatch, encryption_key):
        """Test that plaintext keys are never stored in database."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        plaintext_key = "sk-ant-secret-key-12345"
        client.post("/api/v1/api-keys", json={"service_name": "anthropic", "api_key": plaintext_key})

        # Query raw database
        db_key = db_session.query(APIKey).filter_by(service_name="anthropic").first()

        # Encrypted key should be bytes and not contain plaintext
        assert isinstance(db_key.encrypted_key, bytes)
        assert plaintext_key not in db_key.encrypted_key.decode('latin1', errors='ignore')

    def test_list_response_never_contains_decrypted_keys(self, client, monkeypatch, encryption_key):
        """Test that API responses never expose decrypted keys."""
        monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", encryption_key.decode())

        secret_key = "sk-ant-super-secret-key"
        client.post("/api/v1/api-keys", json={"service_name": "anthropic", "api_key": secret_key})

        response = client.get("/api/v1/api-keys")
        response_text = response.text

        # Secret key should not appear anywhere in response
        assert secret_key not in response_text
        assert "super-secret" not in response_text

    def test_different_encryption_keys_produce_different_ciphertext(self, db_session):
        """Test that changing encryption key produces different ciphertext."""
        plaintext = "sk-test-key"

        # Encrypt with first key
        key1 = Fernet.generate_key()
        service1 = APIKeyService(db_session, encryption_key=key1.decode())
        encrypted1 = service1.encrypt_key(plaintext)

        # Encrypt with second key
        key2 = Fernet.generate_key()
        service2 = APIKeyService(db_session, encryption_key=key2.decode())
        encrypted2 = service2.encrypt_key(plaintext)

        # Different encryption keys -> different ciphertext
        assert encrypted1 != encrypted2

    def test_cannot_decrypt_with_wrong_key(self, db_session):
        """Test that decryption fails with wrong encryption key."""
        plaintext = "sk-test-key"

        # Encrypt with one key
        key1 = Fernet.generate_key()
        service1 = APIKeyService(db_session, encryption_key=key1.decode())
        encrypted = service1.encrypt_key(plaintext)

        # Try to decrypt with different key
        key2 = Fernet.generate_key()
        service2 = APIKeyService(db_session, encryption_key=key2.decode())

        with pytest.raises(Exception):  # Fernet raises InvalidToken
            service2.decrypt_key(encrypted)


class TestAPIKeyServiceMethods:
    """Test APIKeyService business logic methods."""

    def test_get_decrypted_key_success(self, db_session, api_key_service):
        """Test retrieving and decrypting an API key."""
        # Create encrypted key in database
        original_key = "sk-test-key-12345"
        encrypted = api_key_service.encrypt_key(original_key)

        api_key = APIKey(
            id=uuid.uuid4(),
            service_name="anthropic",
            encrypted_key=encrypted,
            is_active=True
        )
        db_session.add(api_key)
        db_session.commit()

        # Retrieve and decrypt
        decrypted = api_key_service.get_decrypted_key("anthropic")
        assert decrypted == original_key

    def test_get_decrypted_key_not_found(self, api_key_service):
        """Test retrieving non-existent key raises error."""
        with pytest.raises(ValueError, match="not found"):
            api_key_service.get_decrypted_key("nonexistent")

    def test_create_api_key_method(self, db_session, api_key_service):
        """Test service create method."""
        created = api_key_service.create_api_key("openai", "sk-openai-key")

        assert created.service_name == "openai"
        assert created.is_active is True
        assert isinstance(created.encrypted_key, bytes)

        # Verify in database
        db_key = db_session.query(APIKey).filter_by(service_name="openai").first()
        assert db_key is not None

    def test_update_api_key_method(self, db_session, api_key_service):
        """Test service update method."""
        # Create initial key
        api_key_service.create_api_key("cohere", "co-old-key")

        # Update
        updated = api_key_service.update_api_key("cohere", "co-new-key")

        assert updated.service_name == "cohere"
        decrypted = api_key_service.get_decrypted_key("cohere")
        assert decrypted == "co-new-key"

    def test_delete_api_key_method(self, db_session, api_key_service):
        """Test service delete method."""
        api_key_service.create_api_key("huggingface", "hf-test-key")

        api_key_service.delete_api_key("huggingface")

        db_key = db_session.query(APIKey).filter_by(service_name="huggingface").first()
        assert db_key is None

    def test_list_api_keys_method(self, db_session, api_key_service):
        """Test service list method."""
        api_key_service.create_api_key("anthropic", "sk-ant-key")
        api_key_service.create_api_key("openai", "sk-openai-key")

        keys = api_key_service.list_api_keys()

        assert len(keys) == 2
        service_names = [k.service_name for k in keys]
        assert "anthropic" in service_names
        assert "openai" in service_names
