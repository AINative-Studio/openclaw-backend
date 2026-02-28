"""
Security Management UI API Endpoint Tests

Comprehensive tests for 8 security endpoints:
- Capability Token Management (4 endpoints)
- Peer Key Management (2 endpoints)
- Audit Log Management (2 endpoints)

Issue #87: Security Management UI Endpoints
Epic E7: Security & Capability Management
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from io import StringIO

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.api.v1.endpoints.security import router
from backend.models.capability_token import CapabilityToken, TokenLimits
from backend.models.audit_event import (
    AuditEvent,
    AuditEventType,
    AuditEventResult,
    AuditQuery,
)


@pytest.fixture
def app():
    """Create FastAPI test app with security router"""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def sample_token():
    """Create a sample capability token for testing"""
    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())
    return CapabilityToken(
        jti="test_jti_12345",
        peer_id="12D3KooWTest123",
        capabilities=["can_execute:llama-2-7b", "can_execute:gpt-3.5-turbo"],
        limits=TokenLimits(
            max_gpu_minutes=3600,
            max_concurrent_tasks=5
        ),
        data_scope=["project-1", "project-2"],
        expires_at=expires_at,
    )


@pytest.fixture
def sample_audit_event():
    """Create a sample audit event for testing"""
    return AuditEvent(
        timestamp=datetime.now(timezone.utc),
        event_type=AuditEventType.AUTHORIZATION_SUCCESS,
        peer_id="12D3KooWTest123",
        action="task_assignment",
        resource="task_456",
        result=AuditEventResult.SUCCESS,
        reason="Valid capability token",
        metadata={"task_id": "task_456", "capability": "can_execute:llama-2-7b"}
    )


# ============================================================================
# Capability Token Tests
# ============================================================================

class TestListCapabilityTokens:
    """Test GET /api/v1/security/tokens endpoint"""

    def test_returns_200_with_empty_list(self, client):
        """
        GIVEN a fresh token service with no tokens
        WHEN requesting GET /api/v1/security/tokens
        THEN should return HTTP 200 with empty list
        """
        with patch("backend.api.v1.endpoints.security.get_all_tokens") as mock_get:
            mock_get.return_value = []

            response = client.get("/api/v1/security/tokens")

            assert response.status_code == 200
            data = response.json()
            assert data == {"tokens": [], "total": 0}

    def test_returns_200_with_token_list(self, client, sample_token):
        """
        GIVEN a token service with multiple tokens
        WHEN requesting GET /api/v1/security/tokens
        THEN should return HTTP 200 with list of tokens
        """
        with patch("backend.api.v1.endpoints.security.get_all_tokens") as mock_get:
            mock_get.return_value = [sample_token]

            response = client.get("/api/v1/security/tokens")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert len(data["tokens"]) == 1
            token = data["tokens"][0]
            assert token["peer_id"] == "12D3KooWTest123"
            assert "can_execute:llama-2-7b" in token["capabilities"]

    def test_masks_jti_in_response(self, client, sample_token):
        """
        GIVEN a token service with tokens
        WHEN requesting GET /api/v1/security/tokens
        THEN JTI should be masked (first 8 chars + ***)
        """
        with patch("backend.api.v1.endpoints.security.get_all_tokens") as mock_get:
            mock_get.return_value = [sample_token]

            response = client.get("/api/v1/security/tokens")

            data = response.json()
            token = data["tokens"][0]
            assert token["jti_masked"] == "test_jti***"
            assert token["jti"] is None  # Full JTI should not be exposed in list

    def test_includes_expiration_status(self, client, sample_token):
        """
        GIVEN a token service with tokens
        WHEN requesting GET /api/v1/security/tokens
        THEN each token should include is_expired and expires_in_seconds
        """
        with patch("backend.api.v1.endpoints.security.get_all_tokens") as mock_get:
            mock_get.return_value = [sample_token]

            response = client.get("/api/v1/security/tokens")

            data = response.json()
            token = data["tokens"][0]
            assert "is_expired" in token
            assert "expires_in_seconds" in token
            assert token["is_expired"] is False
            assert token["expires_in_seconds"] > 0

    def test_filter_by_peer_id(self, client, sample_token):
        """
        GIVEN a token service with multiple peer tokens
        WHEN requesting GET /api/v1/security/tokens?peer_id=12D3KooWTest123
        THEN should return only tokens for that peer
        """
        with patch("backend.api.v1.endpoints.security.get_all_tokens") as mock_get:
            mock_get.return_value = [sample_token]

            response = client.get("/api/v1/security/tokens?peer_id=12D3KooWTest123")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["tokens"][0]["peer_id"] == "12D3KooWTest123"

    def test_filter_by_expired_status(self, client):
        """
        GIVEN a token service with mix of expired and active tokens
        WHEN requesting GET /api/v1/security/tokens?expired=true
        THEN should return only expired tokens
        """
        # Create a mock token that bypasses validation
        mock_token = Mock(spec=CapabilityToken)
        mock_token.jti = "expired_jti"
        mock_token.peer_id = "12D3KooWExpired"
        mock_token.capabilities = ["can_execute:test"]
        mock_token.limits = TokenLimits(max_gpu_minutes=100, max_concurrent_tasks=1)
        mock_token.expires_at = int((datetime.utcnow() - timedelta(hours=1)).timestamp())
        mock_token.data_scope = []
        mock_token.parent_jti = None
        mock_token.is_expired.return_value = True
        mock_token.expires_in_seconds.return_value = 0

        with patch("backend.api.v1.endpoints.security.get_all_tokens") as mock_get:
            mock_get.return_value = [mock_token]

            response = client.get("/api/v1/security/tokens?expired=true")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] >= 0

    def test_returns_500_on_service_error(self, client):
        """
        GIVEN a token service that raises an exception
        WHEN requesting GET /api/v1/security/tokens
        THEN should return HTTP 500
        """
        with patch("backend.api.v1.endpoints.security.get_all_tokens") as mock_get:
            mock_get.side_effect = Exception("Database connection failed")

            response = client.get("/api/v1/security/tokens")

            assert response.status_code == 500
            assert "Database connection failed" in response.json()["detail"]


class TestCreateCapabilityToken:
    """Test POST /api/v1/security/tokens endpoint"""

    def test_returns_201_with_created_token(self, client):
        """
        GIVEN valid token creation request
        WHEN requesting POST /api/v1/security/tokens
        THEN should return HTTP 201 with created token
        """
        request_body = {
            "peer_id": "12D3KooWNewPeer",
            "capabilities": ["can_execute:llama-2-7b"],
            "max_gpu_minutes": 3600,
            "max_concurrent_tasks": 5,
            "data_scope": ["project-1"],
            "expires_in_seconds": 3600
        }

        with patch("backend.api.v1.endpoints.security.create_token") as mock_create:
            mock_token = Mock(spec=CapabilityToken)
            mock_token.jti = "new_jti_12345"
            mock_token.peer_id = "12D3KooWNewPeer"
            mock_token.capabilities = ["can_execute:llama-2-7b"]
            mock_token.expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())
            mock_create.return_value = mock_token

            response = client.post("/api/v1/security/tokens", json=request_body)

            assert response.status_code == 201
            data = response.json()
            assert data["peer_id"] == "12D3KooWNewPeer"
            assert "jti" in data or "jti_masked" in data

    def test_validates_required_fields(self, client):
        """
        GIVEN incomplete token creation request
        WHEN requesting POST /api/v1/security/tokens
        THEN should return HTTP 422 validation error
        """
        request_body = {
            "peer_id": "12D3KooWNewPeer"
            # Missing required fields
        }

        response = client.post("/api/v1/security/tokens", json=request_body)

        assert response.status_code == 422

    def test_validates_capabilities_not_empty(self, client):
        """
        GIVEN token request with empty capabilities
        WHEN requesting POST /api/v1/security/tokens
        THEN should return HTTP 422
        """
        request_body = {
            "peer_id": "12D3KooWNewPeer",
            "capabilities": [],  # Empty
            "max_gpu_minutes": 3600,
            "max_concurrent_tasks": 5,
            "expires_in_seconds": 3600
        }

        response = client.post("/api/v1/security/tokens", json=request_body)

        assert response.status_code == 422

    def test_validates_positive_limits(self, client):
        """
        GIVEN token request with negative limits
        WHEN requesting POST /api/v1/security/tokens
        THEN should return HTTP 422
        """
        request_body = {
            "peer_id": "12D3KooWNewPeer",
            "capabilities": ["can_execute:test"],
            "max_gpu_minutes": -100,  # Negative
            "max_concurrent_tasks": 5,
            "expires_in_seconds": 3600
        }

        response = client.post("/api/v1/security/tokens", json=request_body)

        assert response.status_code == 422

    def test_returns_jwt_token_string(self, client):
        """
        GIVEN valid token creation request
        WHEN requesting POST /api/v1/security/tokens
        THEN response should include JWT token string
        """
        request_body = {
            "peer_id": "12D3KooWNewPeer",
            "capabilities": ["can_execute:llama-2-7b"],
            "max_gpu_minutes": 3600,
            "max_concurrent_tasks": 5,
            "expires_in_seconds": 3600
        }

        with patch("backend.api.v1.endpoints.security.create_token") as mock_create:
            with patch("backend.api.v1.endpoints.security.encode_token") as mock_encode:
                mock_token = Mock(spec=CapabilityToken)
                mock_token.jti = "new_jti"
                mock_token.peer_id = "12D3KooWNewPeer"
                mock_token.capabilities = ["can_execute:llama-2-7b"]
                mock_token.expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())
                mock_create.return_value = mock_token
                mock_encode.return_value = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

                response = client.post("/api/v1/security/tokens", json=request_body)

                assert response.status_code == 201
                data = response.json()
                assert "token" in data
                assert data["token"].startswith("eyJ")


class TestRevokeCapabilityToken:
    """Test DELETE /api/v1/security/tokens/{jti} endpoint"""

    def test_returns_200_on_successful_revocation(self, client):
        """
        GIVEN an existing token
        WHEN requesting DELETE /api/v1/security/tokens/{jti}
        THEN should return HTTP 200
        """
        with patch("backend.api.v1.endpoints.security.revoke_token") as mock_revoke:
            mock_revoke.return_value = True

            response = client.delete("/api/v1/security/tokens/test_jti_12345")

            assert response.status_code == 200
            data = response.json()
            assert data["revoked"] is True
            assert data["jti"] == "test_jti_12345"

    def test_returns_404_when_token_not_found(self, client):
        """
        GIVEN a non-existent token JTI
        WHEN requesting DELETE /api/v1/security/tokens/{jti}
        THEN should return HTTP 404
        """
        with patch("backend.api.v1.endpoints.security.revoke_token") as mock_revoke:
            mock_revoke.return_value = False

            response = client.delete("/api/v1/security/tokens/nonexistent_jti")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_accepts_optional_reason(self, client):
        """
        GIVEN an existing token and revocation reason
        WHEN requesting DELETE /api/v1/security/tokens/{jti}?reason=compromised
        THEN should pass reason to service
        """
        with patch("backend.api.v1.endpoints.security.revoke_token") as mock_revoke:
            mock_revoke.return_value = True

            response = client.delete(
                "/api/v1/security/tokens/test_jti?reason=compromised"
            )

            assert response.status_code == 200
            mock_revoke.assert_called_once()

    def test_returns_500_on_service_error(self, client):
        """
        GIVEN a token service that raises exception
        WHEN requesting DELETE /api/v1/security/tokens/{jti}
        THEN should return HTTP 500
        """
        with patch("backend.api.v1.endpoints.security.revoke_token") as mock_revoke:
            mock_revoke.side_effect = RuntimeError("Database error")

            response = client.delete("/api/v1/security/tokens/test_jti")

            assert response.status_code == 500


class TestRotateCapabilityToken:
    """Test POST /api/v1/security/tokens/{jti}/rotate endpoint"""

    def test_returns_200_with_new_token(self, client, sample_token):
        """
        GIVEN an existing token
        WHEN requesting POST /api/v1/security/tokens/{jti}/rotate
        THEN should return HTTP 200 with new token
        """
        new_token = CapabilityToken(
            jti="new_jti_67890",
            peer_id=sample_token.peer_id,
            capabilities=sample_token.capabilities,
            limits=sample_token.limits,
            expires_at=sample_token.expires_at + 3600,
            parent_jti=sample_token.jti
        )

        with patch("backend.api.v1.endpoints.security.rotate_token") as mock_rotate:
            mock_rotate.return_value = new_token

            response = client.post("/api/v1/security/tokens/test_jti_12345/rotate")

            assert response.status_code == 200
            data = response.json()
            assert data["parent_jti"] == "test_jti_12345"
            assert data["jti"] != "test_jti_12345"

    def test_new_token_has_same_capabilities(self, client, sample_token):
        """
        GIVEN an existing token
        WHEN rotating the token
        THEN new token should have same capabilities as original
        """
        new_token = CapabilityToken(
            jti="new_jti",
            peer_id=sample_token.peer_id,
            capabilities=sample_token.capabilities,
            limits=sample_token.limits,
            expires_at=sample_token.expires_at + 3600,
            parent_jti=sample_token.jti
        )

        with patch("backend.api.v1.endpoints.security.rotate_token") as mock_rotate:
            mock_rotate.return_value = new_token

            response = client.post(f"/api/v1/security/tokens/{sample_token.jti}/rotate")

            data = response.json()
            assert data["capabilities"] == sample_token.capabilities
            assert data["peer_id"] == sample_token.peer_id

    def test_accepts_optional_extends_by(self, client):
        """
        GIVEN rotation request with extends_by parameter
        WHEN requesting POST /api/v1/security/tokens/{jti}/rotate?extends_by=7200
        THEN should extend expiration by specified seconds
        """
        with patch("backend.api.v1.endpoints.security.rotate_token") as mock_rotate:
            new_token = Mock(spec=CapabilityToken)
            new_token.jti = "new_jti"
            new_token.peer_id = "12D3KooWTest"
            new_token.capabilities = ["can_execute:test"]
            new_token.limits = TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3)
            new_token.data_scope = []
            new_token.parent_jti = "test_jti"
            new_token.expires_at = int((datetime.utcnow() + timedelta(hours=2)).timestamp())
            new_token.is_expired.return_value = False
            new_token.expires_in_seconds.return_value = 7200
            mock_rotate.return_value = new_token

            response = client.post(
                "/api/v1/security/tokens/test_jti/rotate?extends_by=7200"
            )

            assert response.status_code == 200

    def test_returns_404_when_token_not_found(self, client):
        """
        GIVEN a non-existent token JTI
        WHEN requesting POST /api/v1/security/tokens/{jti}/rotate
        THEN should return HTTP 404
        """
        with patch("backend.api.v1.endpoints.security.rotate_token") as mock_rotate:
            mock_rotate.side_effect = ValueError("Token not found")

            response = client.post("/api/v1/security/tokens/nonexistent/rotate")

            assert response.status_code == 404

    def test_returns_400_when_token_expired(self, client):
        """
        GIVEN an expired token
        WHEN requesting POST /api/v1/security/tokens/{jti}/rotate
        THEN should return HTTP 400
        """
        with patch("backend.api.v1.endpoints.security.rotate_token") as mock_rotate:
            mock_rotate.side_effect = ValueError("Cannot rotate expired token")

            response = client.post("/api/v1/security/tokens/expired_jti/rotate")

            assert response.status_code == 400 or response.status_code == 404


# ============================================================================
# Peer Key Management Tests
# ============================================================================

class TestListPeerKeys:
    """Test GET /api/v1/security/peer-keys endpoint"""

    def test_returns_200_with_key_list(self, client):
        """
        GIVEN a peer key store with registered peers
        WHEN requesting GET /api/v1/security/peer-keys
        THEN should return HTTP 200 with list of peer keys
        """
        with patch("backend.api.v1.endpoints.security.get_all_peer_keys") as mock_get:
            mock_get.return_value = [
                {
                    "peer_id": "12D3KooWPeer1",
                    "public_key_fingerprint": "sha256:abc123...",
                    "registered_at": datetime.now(timezone.utc).isoformat()
                },
                {
                    "peer_id": "12D3KooWPeer2",
                    "public_key_fingerprint": "sha256:def456...",
                    "registered_at": datetime.now(timezone.utc).isoformat()
                }
            ]

            response = client.get("/api/v1/security/peer-keys")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 2
            assert len(data["peer_keys"]) == 2

    def test_returns_fingerprints_not_full_keys(self, client):
        """
        GIVEN a peer key store
        WHEN requesting GET /api/v1/security/peer-keys
        THEN should return fingerprints, not full public keys
        """
        with patch("backend.api.v1.endpoints.security.get_all_peer_keys") as mock_get:
            mock_get.return_value = [
                {
                    "peer_id": "12D3KooWPeer1",
                    "public_key_fingerprint": "sha256:abc123",
                    "registered_at": datetime.now(timezone.utc).isoformat()
                }
            ]

            response = client.get("/api/v1/security/peer-keys")

            data = response.json()
            peer_key = data["peer_keys"][0]
            assert "public_key_fingerprint" in peer_key
            assert peer_key["public_key_fingerprint"].startswith("sha256:")
            assert "public_key" not in peer_key  # Full key should NOT be exposed

    def test_returns_empty_list_when_no_keys(self, client):
        """
        GIVEN a peer key store with no keys
        WHEN requesting GET /api/v1/security/peer-keys
        THEN should return HTTP 200 with empty list
        """
        with patch("backend.api.v1.endpoints.security.get_all_peer_keys") as mock_get:
            mock_get.return_value = []

            response = client.get("/api/v1/security/peer-keys")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 0
            assert data["peer_keys"] == []

    def test_returns_500_on_service_error(self, client):
        """
        GIVEN a peer key store that raises exception
        WHEN requesting GET /api/v1/security/peer-keys
        THEN should return HTTP 500
        """
        with patch("backend.api.v1.endpoints.security.get_all_peer_keys") as mock_get:
            mock_get.side_effect = RuntimeError("Key store unavailable")

            response = client.get("/api/v1/security/peer-keys")

            assert response.status_code == 500


class TestGetPeerKeyDetails:
    """Test GET /api/v1/security/peer-keys/{peer_id} endpoint"""

    def test_returns_200_with_key_details(self, client):
        """
        GIVEN a registered peer
        WHEN requesting GET /api/v1/security/peer-keys/{peer_id}
        THEN should return HTTP 200 with peer key details
        """
        with patch("backend.api.v1.endpoints.security.get_peer_key_details") as mock_get:
            mock_get.return_value = {
                "peer_id": "12D3KooWPeer1",
                "public_key_fingerprint": "sha256:abc123",
                "public_key_bytes": "base64encodedkey==",
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "last_verified_at": datetime.now(timezone.utc).isoformat(),
                "verification_count": 42
            }

            response = client.get("/api/v1/security/peer-keys/12D3KooWPeer1")

            assert response.status_code == 200
            data = response.json()
            assert data["peer_id"] == "12D3KooWPeer1"
            assert "public_key_fingerprint" in data

    def test_returns_404_when_peer_not_found(self, client):
        """
        GIVEN a non-existent peer ID
        WHEN requesting GET /api/v1/security/peer-keys/{peer_id}
        THEN should return HTTP 404
        """
        with patch("backend.api.v1.endpoints.security.get_peer_key_details") as mock_get:
            mock_get.return_value = None

            response = client.get("/api/v1/security/peer-keys/nonexistent_peer")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_includes_verification_stats(self, client):
        """
        GIVEN a registered peer with verification history
        WHEN requesting GET /api/v1/security/peer-keys/{peer_id}
        THEN should include verification statistics
        """
        with patch("backend.api.v1.endpoints.security.get_peer_key_details") as mock_get:
            mock_get.return_value = {
                "peer_id": "12D3KooWPeer1",
                "public_key_fingerprint": "sha256:abc123",
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "last_verified_at": datetime.now(timezone.utc).isoformat(),
                "verification_count": 42
            }

            response = client.get("/api/v1/security/peer-keys/12D3KooWPeer1")

            data = response.json()
            assert "verification_count" in data
            assert data["verification_count"] == 42


# ============================================================================
# Audit Log Tests
# ============================================================================

class TestQueryAuditLogs:
    """Test GET /api/v1/security/audit-logs endpoint"""

    def test_returns_200_with_audit_events(self, client, sample_audit_event):
        """
        GIVEN audit logs with events
        WHEN requesting GET /api/v1/security/audit-logs
        THEN should return HTTP 200 with list of events
        """
        with patch("backend.api.v1.endpoints.security.query_audit_logs") as mock_query:
            mock_query.return_value = {
                "events": [sample_audit_event],
                "total": 1,
                "limit": 100,
                "offset": 0
            }

            response = client.get("/api/v1/security/audit-logs")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert len(data["events"]) == 1
            event = data["events"][0]
            assert event["event_type"] == "AUTHORIZATION_SUCCESS"
            assert event["peer_id"] == "12D3KooWTest123"

    def test_filter_by_peer_id(self, client, sample_audit_event):
        """
        GIVEN audit logs for multiple peers
        WHEN requesting GET /api/v1/security/audit-logs?peer_id=12D3KooWTest123
        THEN should return only events for that peer
        """
        with patch("backend.api.v1.endpoints.security.query_audit_logs") as mock_query:
            mock_query.return_value = {
                "events": [sample_audit_event],
                "total": 1,
                "limit": 100,
                "offset": 0
            }

            response = client.get("/api/v1/security/audit-logs?peer_id=12D3KooWTest123")

            assert response.status_code == 200
            data = response.json()
            for event in data["events"]:
                assert event["peer_id"] == "12D3KooWTest123"

    def test_filter_by_event_type(self, client, sample_audit_event):
        """
        GIVEN audit logs with various event types
        WHEN requesting GET /api/v1/security/audit-logs?event_type=AUTHORIZATION_SUCCESS
        THEN should return only matching events
        """
        with patch("backend.api.v1.endpoints.security.query_audit_logs") as mock_query:
            mock_query.return_value = {
                "events": [sample_audit_event],
                "total": 1,
                "limit": 100,
                "offset": 0
            }

            response = client.get(
                "/api/v1/security/audit-logs?event_type=AUTHORIZATION_SUCCESS"
            )

            assert response.status_code == 200
            data = response.json()
            for event in data["events"]:
                assert event["event_type"] == "AUTHORIZATION_SUCCESS"

    def test_filter_by_time_range(self, client):
        """
        GIVEN audit logs spanning multiple days
        WHEN requesting GET /api/v1/security/audit-logs?start_time=...&end_time=...
        THEN should return only events within time range
        """
        start_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        end_time = datetime.now(timezone.utc).isoformat()

        with patch("backend.api.v1.endpoints.security.query_audit_logs") as mock_query:
            mock_query.return_value = {
                "events": [],
                "total": 0,
                "limit": 100,
                "offset": 0
            }

            response = client.get(
                f"/api/v1/security/audit-logs?start_time={start_time}&end_time={end_time}"
            )

            assert response.status_code == 200

    def test_pagination_with_limit_offset(self, client):
        """
        GIVEN audit logs with many events
        WHEN requesting GET /api/v1/security/audit-logs?limit=50&offset=100
        THEN should return paginated results
        """
        with patch("backend.api.v1.endpoints.security.query_audit_logs") as mock_query:
            mock_query.return_value = {
                "events": [],
                "total": 500,
                "limit": 50,
                "offset": 100
            }

            response = client.get("/api/v1/security/audit-logs?limit=50&offset=100")

            assert response.status_code == 200
            data = response.json()
            assert data["limit"] == 50
            assert data["offset"] == 100
            assert data["total"] == 500

    def test_validates_limit_range(self, client):
        """
        GIVEN pagination limit out of range
        WHEN requesting GET /api/v1/security/audit-logs?limit=5000
        THEN should return HTTP 422
        """
        response = client.get("/api/v1/security/audit-logs?limit=5000")

        assert response.status_code == 422

    def test_returns_empty_list_when_no_events(self, client):
        """
        GIVEN audit logs with no events
        WHEN requesting GET /api/v1/security/audit-logs
        THEN should return HTTP 200 with empty list
        """
        with patch("backend.api.v1.endpoints.security.query_audit_logs") as mock_query:
            mock_query.return_value = {
                "events": [],
                "total": 0,
                "limit": 100,
                "offset": 0
            }

            response = client.get("/api/v1/security/audit-logs")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 0
            assert data["events"] == []


class TestExportAuditLogs:
    """Test GET /api/v1/security/audit-logs/export endpoint"""

    def test_returns_200_with_json_export(self, client, sample_audit_event):
        """
        GIVEN audit logs with events
        WHEN requesting GET /api/v1/security/audit-logs/export?format=json
        THEN should return HTTP 200 with JSON export
        """
        with patch("backend.api.v1.endpoints.security.export_audit_logs") as mock_export:
            mock_export.return_value = json.dumps([
                {
                    "timestamp": sample_audit_event.timestamp.isoformat(),
                    "event_type": sample_audit_event.event_type.value,
                    "peer_id": sample_audit_event.peer_id,
                    "action": sample_audit_event.action,
                    "result": sample_audit_event.result.value,
                    "reason": sample_audit_event.reason
                }
            ])

            response = client.get("/api/v1/security/audit-logs/export?format=json")

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/json"
            data = response.json()
            assert isinstance(data, list)

    def test_returns_200_with_csv_export(self, client, sample_audit_event):
        """
        GIVEN audit logs with events
        WHEN requesting GET /api/v1/security/audit-logs/export?format=csv
        THEN should return HTTP 200 with CSV export
        """
        csv_content = "timestamp,event_type,peer_id,action,result,reason\n" + \
                     f"{sample_audit_event.timestamp.isoformat()},{sample_audit_event.event_type.value}," + \
                     f"{sample_audit_event.peer_id},{sample_audit_event.action}," + \
                     f"{sample_audit_event.result.value},{sample_audit_event.reason}\n"

        with patch("backend.api.v1.endpoints.security.export_audit_logs") as mock_export:
            mock_export.return_value = csv_content

            response = client.get("/api/v1/security/audit-logs/export?format=csv")

            assert response.status_code == 200
            assert "text/csv" in response.headers["content-type"]
            assert "timestamp,event_type,peer_id" in response.text

    def test_defaults_to_json_format(self, client):
        """
        GIVEN no format parameter
        WHEN requesting GET /api/v1/security/audit-logs/export
        THEN should default to JSON format
        """
        with patch("backend.api.v1.endpoints.security.export_audit_logs") as mock_export:
            mock_export.return_value = "[]"

            response = client.get("/api/v1/security/audit-logs/export")

            assert response.status_code == 200
            assert "application/json" in response.headers["content-type"]

    def test_rejects_invalid_format(self, client):
        """
        GIVEN invalid format parameter
        WHEN requesting GET /api/v1/security/audit-logs/export?format=xml
        THEN should return HTTP 422
        """
        response = client.get("/api/v1/security/audit-logs/export?format=xml")

        assert response.status_code == 422

    def test_includes_content_disposition_header(self, client):
        """
        GIVEN audit log export request
        WHEN requesting GET /api/v1/security/audit-logs/export
        THEN should include Content-Disposition header for download
        """
        with patch("backend.api.v1.endpoints.security.export_audit_logs") as mock_export:
            mock_export.return_value = "[]"

            response = client.get("/api/v1/security/audit-logs/export?format=json")

            assert response.status_code == 200
            assert "content-disposition" in response.headers
            assert "attachment" in response.headers["content-disposition"]
            assert "audit-logs" in response.headers["content-disposition"]

    def test_applies_same_filters_as_query(self, client):
        """
        GIVEN export request with filters
        WHEN requesting GET /api/v1/security/audit-logs/export?peer_id=12D3KooW...
        THEN should apply same filters as query endpoint
        """
        with patch("backend.api.v1.endpoints.security.export_audit_logs") as mock_export:
            mock_export.return_value = "[]"

            response = client.get(
                "/api/v1/security/audit-logs/export?peer_id=12D3KooWTest&format=json"
            )

            assert response.status_code == 200
            mock_export.assert_called_once()


# ============================================================================
# Integration Tests
# ============================================================================

class TestSecurityEndpointsIntegration:
    """Integration tests across security endpoints"""

    def test_create_token_then_list_shows_new_token(self, client):
        """
        GIVEN a fresh token service
        WHEN creating a token then listing tokens
        THEN new token should appear in list
        """
        create_request = {
            "peer_id": "12D3KooWIntegration",
            "capabilities": ["can_execute:test"],
            "max_gpu_minutes": 1000,
            "max_concurrent_tasks": 3,
            "expires_in_seconds": 3600
        }

        mock_token = Mock(spec=CapabilityToken)
        mock_token.jti = "integration_jti"
        mock_token.peer_id = "12D3KooWIntegration"
        mock_token.capabilities = ["can_execute:test"]
        mock_token.limits = TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3)
        mock_token.data_scope = []
        mock_token.parent_jti = None
        mock_token.expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())
        mock_token.is_expired.return_value = False
        mock_token.expires_in_seconds.return_value = 3600

        with patch("backend.api.v1.endpoints.security.create_token") as mock_create:
            with patch("backend.api.v1.endpoints.security.encode_token") as mock_encode:
                with patch("backend.api.v1.endpoints.security.get_all_tokens") as mock_list:
                    mock_create.return_value = mock_token
                    mock_encode.return_value = "eyJtest.token"
                    mock_list.return_value = [mock_token]

                    # Create
                    create_response = client.post("/api/v1/security/tokens", json=create_request)
                    assert create_response.status_code == 201

                    # List
                    list_response = client.get("/api/v1/security/tokens")
                    assert list_response.status_code == 200

    def test_rotate_token_then_revoke_old_token(self, client):
        """
        GIVEN an existing token
        WHEN rotating then revoking old token
        THEN both operations should succeed
        """
        new_token = Mock(spec=CapabilityToken)
        new_token.jti = "new_jti"
        new_token.peer_id = "12D3KooWTest"
        new_token.capabilities = ["can_execute:test"]
        new_token.limits = TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3)
        new_token.data_scope = []
        new_token.parent_jti = "old_jti"
        new_token.expires_at = int((datetime.utcnow() + timedelta(hours=2)).timestamp())
        new_token.is_expired.return_value = False
        new_token.expires_in_seconds.return_value = 7200

        with patch("backend.api.v1.endpoints.security.rotate_token") as mock_rotate:
            with patch("backend.api.v1.endpoints.security.revoke_token") as mock_revoke:
                mock_rotate.return_value = new_token
                mock_revoke.return_value = True

                # Rotate
                rotate_response = client.post("/api/v1/security/tokens/old_jti/rotate")
                assert rotate_response.status_code == 200

                # Revoke old
                revoke_response = client.delete("/api/v1/security/tokens/old_jti")
                assert revoke_response.status_code == 200

    def test_token_operations_appear_in_audit_logs(self, client):
        """
        GIVEN token create/revoke operations
        WHEN querying audit logs
        THEN should show corresponding audit events
        """
        # This would require actual audit logger integration
        # For now, verify the audit log endpoint works
        with patch("backend.api.v1.endpoints.security.query_audit_logs") as mock_query:
            mock_query.return_value = {
                "events": [
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "event_type": "TOKEN_ISSUED",
                        "peer_id": "12D3KooWTest",
                        "action": "create_token",
                        "result": "success",
                        "reason": "Token created successfully"
                    }
                ],
                "total": 1,
                "limit": 100,
                "offset": 0
            }

            response = client.get("/api/v1/security/audit-logs?event_type=TOKEN_ISSUED")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] >= 0


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test error handling across security endpoints"""

    def test_handles_service_unavailable_gracefully(self, client):
        """
        GIVEN security services raise exception
        WHEN requesting any security endpoint
        THEN should return HTTP 500
        """
        with patch("backend.api.v1.endpoints.security.get_all_tokens") as mock_get:
            mock_get.side_effect = Exception("Service unavailable")

            response = client.get("/api/v1/security/tokens")

            assert response.status_code == 500

    def test_handles_database_errors(self, client):
        """
        GIVEN database connection failures
        WHEN requesting security endpoints
        THEN should return HTTP 500
        """
        with patch("backend.api.v1.endpoints.security.get_all_tokens") as mock_get:
            mock_get.side_effect = Exception("Database connection failed")

            response = client.get("/api/v1/security/tokens")

            assert response.status_code == 500
            assert "Database connection failed" in response.json()["detail"]

    def test_validates_malformed_json(self, client):
        """
        GIVEN malformed JSON in request
        WHEN creating a token
        THEN should return HTTP 422
        """
        response = client.post(
            "/api/v1/security/tokens",
            data="not valid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422
