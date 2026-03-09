"""
Integration tests for User API Key endpoints (Issue #96)

Tests API endpoints for workspace-level encrypted API key management.
Uses FastAPI TestClient and SQLite in-memory database.
"""

import pytest
import os
from uuid import uuid4
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.db.base import get_db
from backend.models.user_api_key import UserAPIKey


# Generate a test encryption key
TEST_ENCRYPTION_SECRET = Fernet.generate_key().decode()

# Test database setup
TEST_DATABASE_URL = "sqlite:///./test_user_api_keys.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Create test database session."""
    # Create ONLY the user_api_keys table to avoid FK issues with other models
    UserAPIKey.__table__.create(bind=engine, checkfirst=True)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        UserAPIKey.__table__.drop(bind=engine, checkfirst=True)


@pytest.fixture(scope="function")
def client(db_session):
    """Create FastAPI test client with test database."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Set encryption secret for tests
    old_secret = os.environ.get("ENCRYPTION_SECRET")
    os.environ["ENCRYPTION_SECRET"] = TEST_ENCRYPTION_SECRET

    yield TestClient(app)

    # Cleanup
    app.dependency_overrides.clear()
    if old_secret:
        os.environ["ENCRYPTION_SECRET"] = old_secret
    else:
        os.environ.pop("ENCRYPTION_SECRET", None)


@pytest.fixture
def workspace_id():
    """Generate a test workspace ID."""
    return str(uuid4())


class TestAddAPIKey:
    """Test POST /api/v1/settings/api-keys endpoint."""

    def test_add_api_key_success(self, client, workspace_id):
        """Test successfully adding a new API key."""
        response = client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": workspace_id,
                "provider": "anthropic",
                "api_key": "sk-ant-test-key-12345",
                "validate": False
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["workspace_id"] == workspace_id
        assert data["provider"] == "anthropic"
        assert data["masked_key"] == "sk-***...2345"
        assert data["is_active"] is True
        assert "id" in data

    def test_add_api_key_duplicate_returns_400(self, client, workspace_id):
        """Test that adding duplicate key returns 400."""
        # Add first key
        client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": workspace_id,
                "provider": "anthropic",
                "api_key": "sk-ant-test-key-12345",
                "validate": False
            }
        )

        # Try to add duplicate
        response = client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": workspace_id,
                "provider": "anthropic",
                "api_key": "sk-ant-another-key-67890",
                "validate": False
            }
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_add_api_key_invalid_workspace_id_returns_422(self, client):
        """Test that invalid workspace_id returns 422."""
        response = client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": "not-a-uuid",
                "provider": "anthropic",
                "api_key": "sk-ant-test-key-12345",
                "validate": False
            }
        )

        assert response.status_code == 422

    def test_add_api_key_empty_key_returns_422(self, client, workspace_id):
        """Test that empty API key returns 422."""
        response = client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": workspace_id,
                "provider": "anthropic",
                "api_key": "",
                "validate": False
            }
        )

        assert response.status_code == 422

    def test_add_api_key_unsupported_provider_returns_422(self, client, workspace_id):
        """Test that unsupported provider returns 422."""
        response = client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": workspace_id,
                "provider": "unsupported-provider",
                "api_key": "test-key",
                "validate": False
            }
        )

        assert response.status_code == 422

    def test_add_api_key_with_validation_invalid_key_returns_400(self, client, workspace_id):
        """Test that adding invalid key with validation=True returns 400."""
        response = client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": workspace_id,
                "provider": "anthropic",
                "api_key": "sk-ant-invalid-key-12345",
                "validate": True
            }
        )

        assert response.status_code == 400
        assert "validation failed" in response.json()["detail"].lower()


class TestListAPIKeys:
    """Test GET /api/v1/settings/api-keys endpoint."""

    def test_list_api_keys_success(self, client, workspace_id):
        """Test successfully listing API keys for a workspace."""
        # Add multiple keys
        client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": workspace_id,
                "provider": "anthropic",
                "api_key": "sk-ant-key-1",
                "validate": False
            }
        )
        client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": workspace_id,
                "provider": "openai",
                "api_key": "sk-proj-key-2",
                "validate": False
            }
        )

        # List keys
        response = client.get(
            f"/api/v1/settings/api-keys?workspace_id={workspace_id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Check both providers present
        providers = {key["provider"] for key in data}
        assert providers == {"anthropic", "openai"}

        # Check keys are masked
        for key in data:
            assert key["masked_key"].startswith("sk-***") or key["masked_key"] == "***"

    def test_list_api_keys_empty(self, client, workspace_id):
        """Test listing keys for workspace with no keys."""
        response = client.get(
            f"/api/v1/settings/api-keys?workspace_id={workspace_id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    def test_list_api_keys_missing_workspace_id_returns_422(self, client):
        """Test that missing workspace_id query param returns 422."""
        response = client.get("/api/v1/settings/api-keys")

        assert response.status_code == 422

    def test_list_api_keys_different_workspaces(self, client):
        """Test that listing keys is workspace-isolated."""
        workspace1 = str(uuid4())
        workspace2 = str(uuid4())

        # Add key for workspace1
        client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": workspace1,
                "provider": "anthropic",
                "api_key": "sk-ant-key-1",
                "validate": False
            }
        )

        # Add key for workspace2
        client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": workspace2,
                "provider": "openai",
                "api_key": "sk-proj-key-2",
                "validate": False
            }
        )

        # List keys for workspace1
        response1 = client.get(
            f"/api/v1/settings/api-keys?workspace_id={workspace1}"
        )
        assert len(response1.json()) == 1
        assert response1.json()[0]["provider"] == "anthropic"

        # List keys for workspace2
        response2 = client.get(
            f"/api/v1/settings/api-keys?workspace_id={workspace2}"
        )
        assert len(response2.json()) == 1
        assert response2.json()[0]["provider"] == "openai"


class TestDeleteAPIKey:
    """Test DELETE /api/v1/settings/api-keys/{key_id} endpoint."""

    def test_delete_api_key_success(self, client, workspace_id):
        """Test successfully deleting an API key."""
        # Add key
        add_response = client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": workspace_id,
                "provider": "anthropic",
                "api_key": "sk-ant-key-1",
                "validate": False
            }
        )
        key_id = add_response.json()["id"]

        # Delete key
        response = client.delete(f"/api/v1/settings/api-keys/{key_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["deleted_id"] == key_id

        # Verify key is deleted
        list_response = client.get(
            f"/api/v1/settings/api-keys?workspace_id={workspace_id}"
        )
        assert len(list_response.json()) == 0

    def test_delete_api_key_not_found_returns_404(self, client):
        """Test that deleting non-existent key returns 404."""
        fake_id = str(uuid4())
        response = client.delete(f"/api/v1/settings/api-keys/{fake_id}")

        assert response.status_code == 404

    def test_delete_api_key_invalid_id_returns_500_or_404(self, client):
        """Test that invalid key ID returns error."""
        response = client.delete("/api/v1/settings/api-keys/not-a-uuid")

        # Could be 500 (database error) or 404 (not found)
        assert response.status_code in [404, 500]


class TestTestAPIKey:
    """Test POST /api/v1/settings/api-keys/test endpoint."""

    def test_test_api_key_invalid_key(self, client):
        """Test testing an invalid API key."""
        response = client.post(
            "/api/v1/settings/api-keys/test",
            json={
                "provider": "anthropic",
                "api_key": "sk-ant-invalid-key-12345"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "anthropic"
        assert data["is_valid"] is False
        assert "fail" in data["message"].lower() or "invalid" in data["message"].lower()

    @pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set - skipping live API test"
    )
    def test_test_api_key_valid_key(self, client):
        """Test testing a valid API key (requires real key)."""
        api_key = os.getenv("ANTHROPIC_API_KEY")

        response = client.post(
            "/api/v1/settings/api-keys/test",
            json={
                "provider": "anthropic",
                "api_key": api_key
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "anthropic"
        assert data["is_valid"] is True
        assert "valid" in data["message"].lower() or "authenticated" in data["message"].lower()

    def test_test_api_key_unsupported_provider_returns_422(self, client):
        """Test that unsupported provider returns 422."""
        response = client.post(
            "/api/v1/settings/api-keys/test",
            json={
                "provider": "unsupported-provider",
                "api_key": "test-key"
            }
        )

        assert response.status_code == 422

    def test_test_api_key_empty_key_returns_422(self, client):
        """Test that empty API key returns 422."""
        response = client.post(
            "/api/v1/settings/api-keys/test",
            json={
                "provider": "anthropic",
                "api_key": ""
            }
        )

        assert response.status_code == 422


class TestSecurityFeatures:
    """Test security features of the API."""

    def test_keys_are_encrypted_at_rest(self, client, workspace_id, db_session):
        """Test that keys are encrypted in the database."""
        from backend.models.user_api_key import UserAPIKey

        plaintext_key = "sk-ant-test-key-12345"

        # Add key
        client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": workspace_id,
                "provider": "anthropic",
                "api_key": plaintext_key,
                "validate": False
            }
        )

        # Query database directly
        user_api_key = db_session.query(UserAPIKey).filter_by(
            workspace_id=workspace_id,
            provider="anthropic"
        ).first()

        # Verify encrypted key is not plaintext
        assert user_api_key.encrypted_key != plaintext_key
        # Verify it's base64-encoded Fernet ciphertext
        assert isinstance(user_api_key.encrypted_key, str)
        assert len(user_api_key.encrypted_key) > len(plaintext_key)

    def test_list_endpoint_never_exposes_plaintext_keys(self, client, workspace_id):
        """Test that list endpoint only returns masked keys."""
        plaintext_key = "sk-ant-test-key-12345"

        # Add key
        client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": workspace_id,
                "provider": "anthropic",
                "api_key": plaintext_key,
                "validate": False
            }
        )

        # List keys
        response = client.get(
            f"/api/v1/settings/api-keys?workspace_id={workspace_id}"
        )

        data = response.json()
        assert len(data) == 1
        assert data[0]["masked_key"] == "sk-***...2345"
        # Ensure plaintext key is not in response
        assert plaintext_key not in str(response.content)

    def test_add_endpoint_never_exposes_encrypted_keys(self, client, workspace_id):
        """Test that add endpoint never returns encrypted keys."""
        response = client.post(
            "/api/v1/settings/api-keys",
            json={
                "workspace_id": workspace_id,
                "provider": "anthropic",
                "api_key": "sk-ant-test-key-12345",
                "validate": False
            }
        )

        data = response.json()
        # Should only have masked_key, not encrypted_key
        assert "masked_key" in data
        assert "encrypted_key" not in data
        assert "key_hash" not in data
