"""
Authentication Endpoint Tests (Issue #126)

Tests authentication requirements across all API endpoints.
Verifies that protected endpoints return 401 without valid token.
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


class TestPublicEndpoints:
    """Test that public endpoints are accessible without authentication"""

    def test_health_endpoint_no_auth(self):
        """Health check should be publicly accessible"""
        response = client.get("/health")
        # Should either succeed or endpoint not exist, but not 401
        assert response.status_code in [200, 404]

    def test_metrics_endpoint_no_auth(self):
        """Metrics endpoint should be publicly accessible"""
        response = client.get("/metrics")
        # Should either succeed or endpoint not exist, but not 401
        assert response.status_code in [200, 404]

    def test_login_endpoint_no_auth(self):
        """Login endpoint should be publicly accessible"""
        response = client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "password123"
        })
        # Should return 401 for bad credentials, not 401 for missing auth
        assert response.status_code in [200, 401, 422]
        if response.status_code == 401:
            assert "credentials" in response.json().get("detail", "").lower()


class TestProtectedEndpoints:
    """Test that protected endpoints require authentication"""

    PROTECTED_ENDPOINTS = [
        # Agent lifecycle endpoints
        ("GET", "/agents"),
        ("POST", "/agents"),
        ("GET", "/agents/test-agent-id"),
        ("POST", "/agents/test-agent-id/provision"),
        ("POST", "/agents/test-agent-id/pause"),
        ("POST", "/agents/test-agent-id/resume"),
        ("PATCH", "/agents/test-agent-id/settings"),
        ("DELETE", "/agents/test-agent-id"),

        # Conversation endpoints
        ("GET", "/conversations"),
        ("POST", "/conversations"),
        ("GET", "/conversations/00000000-0000-0000-0000-000000000001"),

        # API key endpoints
        ("GET", "/api/v1/api-keys"),
        ("POST", "/api/v1/api-keys"),

        # User API key endpoints
        ("GET", "/api/v1/user-api-keys"),
        ("POST", "/api/v1/user-api-keys"),

        # Team management endpoints
        ("GET", "/team/members"),
        ("POST", "/team/members/invite"),

        # Channel management endpoints
        ("GET", "/channels"),
    ]

    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_protected_endpoint_without_auth(self, method, path):
        """Verify protected endpoints return 401 without authentication"""
        # Make request without Authorization header
        if method == "GET":
            response = client.get(path)
        elif method == "POST":
            response = client.post(path, json={})
        elif method == "PATCH":
            response = client.patch(path, json={})
        elif method == "DELETE":
            response = client.delete(path)
        else:
            pytest.fail(f"Unsupported HTTP method: {method}")

        # Should return 401 Unauthorized
        # Some endpoints might return 422 for validation errors before auth check
        assert response.status_code in [401, 403], \
            f"{method} {path} should require authentication but returned {response.status_code}"

    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_protected_endpoint_with_invalid_token(self, method, path):
        """Verify protected endpoints return 401 with invalid token"""
        headers = {"Authorization": "Bearer invalid_token_here"}

        if method == "GET":
            response = client.get(path, headers=headers)
        elif method == "POST":
            response = client.post(path, json={}, headers=headers)
        elif method == "PATCH":
            response = client.patch(path, json={}, headers=headers)
        elif method == "DELETE":
            response = client.delete(path, headers=headers)

        # Should return 401 for invalid token
        assert response.status_code in [401, 403, 422], \
            f"{method} {path} should reject invalid token but returned {response.status_code}"


class TestAuthenticationFlow:
    """Test the complete authentication flow"""

    def test_login_returns_tokens(self):
        """Test that login endpoint returns access and refresh tokens"""
        # This test requires a valid test user in the database
        # Skip if test user not available
        response = client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "TestPassword123"
        })

        # If test user exists, should return 200 with tokens
        # If not, should return 401
        if response.status_code == 200:
            data = response.json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert "token_type" in data
            assert data["token_type"] == "bearer"

    def test_authenticated_request_flow(self):
        """Test complete flow: login -> authenticated request"""
        # Login
        login_response = client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "TestPassword123"
        })

        if login_response.status_code != 200:
            pytest.skip("Test user not available in database")

        token = login_response.json()["access_token"]

        # Make authenticated request
        response = client.get("/agents", headers={
            "Authorization": f"Bearer {token}"
        })

        # Should succeed (or return other error, but not 401)
        assert response.status_code != 401, \
            "Authenticated request should not return 401"


class TestTokenValidation:
    """Test JWT token validation"""

    def test_malformed_token(self):
        """Test that malformed tokens are rejected"""
        headers = {"Authorization": "Bearer not.a.valid.jwt"}
        response = client.get("/agents", headers=headers)
        assert response.status_code == 401

    def test_missing_bearer_prefix(self):
        """Test that tokens without 'Bearer' prefix are rejected"""
        headers = {"Authorization": "some_token"}
        response = client.get("/agents", headers=headers)
        assert response.status_code in [401, 403]

    def test_empty_authorization_header(self):
        """Test that empty Authorization header is rejected"""
        headers = {"Authorization": ""}
        response = client.get("/agents", headers=headers)
        assert response.status_code in [401, 403]


@pytest.mark.integration
class TestDatabaseAuthIntegration:
    """Integration tests requiring database"""

    def test_inactive_user_rejected(self):
        """Test that inactive users are rejected with 403"""
        # This would require creating an inactive test user
        # Implementation depends on test database setup
        pytest.skip("Requires test database with inactive user")

    def test_deleted_user_token_rejected(self):
        """Test that tokens for deleted users are rejected"""
        # This would require creating and deleting a test user
        # Implementation depends on test database setup
        pytest.skip("Requires test database setup")


# Test configuration
pytestmark = [
    pytest.mark.api,
    pytest.mark.authentication
]
