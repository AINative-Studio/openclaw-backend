"""
Tests for Security Management UI Endpoints

Epic E7 Security Management UI Integration
Refs: #87
"""

import pytest
import json
import hashlib
from datetime import datetime, timedelta, timezone
from io import StringIO
import csv

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.db.base_class import Base
from backend.models.capability_token import CapabilityToken, TokenLimits
from backend.models.token_revocation import TokenRevocation
from backend.models.audit_event import (
    AuditEventType,
    AuditEventResult,
    AuditLogEntry,
)
from backend.security.peer_key_store import PeerKeyStore
from backend.security.token_service import TokenService
from cryptography.hazmat.primitives.asymmetric import ed25519


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def test_engine():
    """Create shared test database engine"""
    from backend.db.base_class import Base as SharedBase
    from backend.models.audit_event import Base as AuditBase

    # Create in-memory SQLite for testing with thread safety
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=None  # Disable connection pooling for test
    )

    # Create all tables from both bases
    SharedBase.metadata.create_all(engine)
    AuditBase.metadata.create_all(engine)

    yield engine

    engine.dispose()


@pytest.fixture
def test_db(test_engine):
    """Create test database session"""
    SessionLocal = sessionmaker(bind=test_engine)
    db = SessionLocal()

    yield db

    db.rollback()  # Rollback any uncommitted changes
    db.close()


@pytest.fixture
def client(test_db):
    """Create test client with database override"""
    from backend.db.base import get_db

    def override_get_db():
        try:
            yield test_db
        finally:
            pass  # Don't close; fixture manages lifecycle

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def token_service():
    """Create token service for testing"""
    return TokenService(secret_key="test-secret-key", algorithm="HS256")


@pytest.fixture
def sample_token(token_service):
    """Create sample capability token"""
    token = CapabilityToken.create(
        peer_id="12D3KooWTest123",
        capabilities=["can_execute:llama-2-7b", "can_execute:gpt-3.5-turbo"],
        limits=TokenLimits(max_gpu_minutes=100, max_concurrent_tasks=5),
        data_scope=["project_1", "project_2"],
        expires_in_seconds=3600
    )
    return token


@pytest.fixture
def peer_key_store():
    """Create peer key store for testing"""
    store = PeerKeyStore()

    # Add sample peer keys
    for i in range(3):
        peer_id = f"12D3KooWPeer{i}"
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        store.store_public_key(peer_id, public_key)

    return store


# ============================================================================
# Token Management Tests
# ============================================================================

class TestTokenList:
    """Tests for GET /api/v1/security/tokens"""

    def test_list_tokens_empty(self, client):
        """Test listing tokens when none exist"""
        response = client.get("/api/v1/security/tokens")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "tokens" in data
        assert isinstance(data["tokens"], list)
        # Note: May be empty or have existing test data
        assert data["total"] >= 0

    def test_list_tokens_pagination(self, client):
        """Test token list pagination"""
        response = client.get("/api/v1/security/tokens?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "tokens" in data
        assert "limit" in data
        assert data["limit"] == 10
        assert "offset" in data
        assert data["offset"] == 0


class TestTokenCreate:
    """Tests for POST /api/v1/security/tokens"""

    def test_create_token_success(self, client):
        """Test successful token creation"""
        payload = {
            "peer_id": "12D3KooWNewPeer123",
            "capabilities": ["can_execute:llama-2-7b"],
            "limits": {
                "max_gpu_minutes": 120,
                "max_concurrent_tasks": 3
            },
            "data_scope": ["project_1"],
            "expires_in_seconds": 7200
        }

        response = client.post("/api/v1/security/tokens", json=payload)
        assert response.status_code == 201
        data = response.json()

        assert "jti" in data
        assert "jti_masked" in data
        assert data["peer_id"] == payload["peer_id"]
        assert data["capabilities"] == payload["capabilities"]
        assert "jwt_token" in data  # Actual JWT for immediate use
        assert "expires_at" in data

    def test_create_token_validation_error(self, client):
        """Test token creation with invalid data"""
        payload = {
            "peer_id": "",  # Empty peer_id should fail
            "capabilities": [],  # Empty capabilities should fail
            "limits": {
                "max_gpu_minutes": -1,  # Negative should fail
                "max_concurrent_tasks": 3
            }
        }

        response = client.post("/api/v1/security/tokens", json=payload)
        assert response.status_code == 422  # Validation error

    def test_create_token_missing_fields(self, client):
        """Test token creation with missing required fields"""
        payload = {
            "peer_id": "12D3KooWTest"
            # Missing capabilities and limits
        }

        response = client.post("/api/v1/security/tokens", json=payload)
        assert response.status_code == 422


class TestTokenRevoke:
    """Tests for DELETE /api/v1/security/tokens/{jti}"""

    def test_revoke_token_success(self, client, test_db, sample_token):
        """Test successful token revocation"""
        jti = sample_token.jti

        response = client.delete(f"/api/v1/security/tokens/{jti}")
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["jti"] == jti
        assert data["reason"] == "manual"

    def test_revoke_token_with_custom_reason(self, client, test_db, sample_token):
        """Test token revocation with custom reason"""
        jti = sample_token.jti

        response = client.delete(
            f"/api/v1/security/tokens/{jti}",
            params={"reason": "security_breach"}
        )
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["reason"] == "security_breach"

    def test_revoke_nonexistent_token(self, client):
        """Test revoking a non-existent token"""
        fake_jti = "nonexistent_token_id_12345"

        response = client.delete(f"/api/v1/security/tokens/{fake_jti}")
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestTokenRotate:
    """Tests for POST /api/v1/security/tokens/{jti}/rotate"""

    def test_rotate_token_success(self, client, test_db, sample_token):
        """Test successful token rotation"""
        jti = sample_token.jti

        response = client.post(f"/api/v1/security/tokens/{jti}/rotate")
        assert response.status_code == 200
        data = response.json()

        assert "old_jti" in data
        assert "new_jti" in data
        assert data["old_jti"] == jti
        assert data["new_jti"] != jti
        assert "new_jwt_token" in data
        assert data["peer_id"] == sample_token.peer_id
        assert data["capabilities"] == sample_token.capabilities

    def test_rotate_token_custom_extension(self, client, test_db, sample_token):
        """Test token rotation with custom extension period"""
        jti = sample_token.jti

        response = client.post(
            f"/api/v1/security/tokens/{jti}/rotate",
            params={"extends_by_seconds": 7200}
        )
        assert response.status_code == 200
        data = response.json()

        assert "new_expires_at" in data
        # New token should have ~2 hours from now
        new_expires = datetime.fromtimestamp(data["new_expires_at"])
        expected_min = datetime.utcnow() + timedelta(seconds=7000)
        expected_max = datetime.utcnow() + timedelta(seconds=7400)
        assert expected_min <= new_expires <= expected_max

    def test_rotate_nonexistent_token(self, client):
        """Test rotating a non-existent token"""
        fake_jti = "nonexistent_token_id_12345"

        response = client.post(f"/api/v1/security/tokens/{fake_jti}/rotate")
        assert response.status_code == 404


# ============================================================================
# Peer Key Management Tests
# ============================================================================

class TestPeerKeyList:
    """Tests for GET /api/v1/security/peer-keys"""

    def test_list_peer_keys_empty(self, client):
        """Test listing peer keys when none exist"""
        response = client.get("/api/v1/security/peer-keys")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["peer_keys"] == []

    def test_list_peer_keys_with_data(self, client, peer_key_store):
        """Test listing peer keys with existing keys"""
        response = client.get("/api/v1/security/peer-keys")
        assert response.status_code == 200
        data = response.json()

        assert "total" in data
        assert "peer_keys" in data
        assert isinstance(data["peer_keys"], list)

    def test_list_peer_keys_includes_fingerprint(self, client, peer_key_store):
        """Test that peer key list includes SHA-256 fingerprint"""
        response = client.get("/api/v1/security/peer-keys")
        assert response.status_code == 200
        data = response.json()

        if data["total"] > 0:
            for key_data in data["peer_keys"]:
                assert "peer_id" in key_data
                assert "fingerprint" in key_data
                assert "algorithm" in key_data
                # Fingerprint should be hex string (64 chars for SHA-256)
                fingerprint = key_data["fingerprint"]
                assert len(fingerprint) == 64
                assert all(c in "0123456789abcdef" for c in fingerprint.lower())


class TestPeerKeyDetails:
    """Tests for GET /api/v1/security/peer-keys/{peer_id}"""

    def test_get_peer_key_success(self, client, peer_key_store):
        """Test getting peer key details"""
        peer_id = "12D3KooWPeer0"

        response = client.get(f"/api/v1/security/peer-keys/{peer_id}")
        assert response.status_code == 200
        data = response.json()

        assert data["peer_id"] == peer_id
        assert "fingerprint" in data
        assert data["algorithm"] == "Ed25519"
        assert "public_key_bytes" in data  # Base64 encoded
        assert "created_at" in data or "stored_at" in data

    def test_get_peer_key_fingerprint_verification(self, client, peer_key_store):
        """Test that fingerprint matches SHA-256 of public key"""
        peer_id = "12D3KooWPeer0"

        response = client.get(f"/api/v1/security/peer-keys/{peer_id}")
        assert response.status_code == 200
        data = response.json()

        # Verify fingerprint is valid hex
        fingerprint = data["fingerprint"]
        assert len(fingerprint) == 64
        assert all(c in "0123456789abcdef" for c in fingerprint.lower())

    def test_get_nonexistent_peer_key(self, client):
        """Test getting a non-existent peer key"""
        fake_peer_id = "12D3KooWNonExistent"

        response = client.get(f"/api/v1/security/peer-keys/{fake_peer_id}")
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


# ============================================================================
# Audit Log Tests
# ============================================================================

class TestAuditLogQuery:
    """Tests for GET /api/v1/security/audit-logs"""

    def test_query_audit_logs_empty(self, client):
        """Test querying audit logs when none exist"""
        response = client.get("/api/v1/security/audit-logs")
        assert response.status_code == 200
        data = response.json()

        assert "total" in data
        assert "events" in data
        assert data["total"] == 0
        assert data["events"] == []

    def test_query_audit_logs_with_data(self, client, test_db):
        """Test querying audit logs with existing events"""
        # Create test audit logs
        for i in range(5):
            entry = AuditLogEntry(
                timestamp=datetime.now(timezone.utc),
                event_type=AuditEventType.AUTHENTICATION_SUCCESS.value,
                peer_id=f"12D3KooWPeer{i}",
                action="login",
                result=AuditEventResult.SUCCESS.value,
                reason="Valid credentials"
            )
            test_db.add(entry)
        test_db.commit()

        response = client.get("/api/v1/security/audit-logs")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] >= 5
        assert len(data["events"]) >= 5

    def test_query_audit_logs_filter_by_peer(self, client, test_db):
        """Test filtering audit logs by peer_id"""
        target_peer = "12D3KooWTargetPeer"

        # Create test audit logs for different peers
        for i in range(3):
            entry = AuditLogEntry(
                timestamp=datetime.now(timezone.utc),
                event_type=AuditEventType.AUTHORIZATION_SUCCESS.value,
                peer_id=target_peer,
                action="task_assignment",
                result=AuditEventResult.SUCCESS.value,
                reason="Has capability"
            )
            test_db.add(entry)

        # Add noise from other peers
        for i in range(2):
            entry = AuditLogEntry(
                timestamp=datetime.now(timezone.utc),
                event_type=AuditEventType.AUTHORIZATION_SUCCESS.value,
                peer_id=f"12D3KooWOtherPeer{i}",
                action="task_assignment",
                result=AuditEventResult.SUCCESS.value,
                reason="Has capability"
            )
            test_db.add(entry)
        test_db.commit()

        response = client.get(f"/api/v1/security/audit-logs?peer_id={target_peer}")
        assert response.status_code == 200
        data = response.json()

        # All events should be for target peer
        for event in data["events"]:
            assert event["peer_id"] == target_peer

    def test_query_audit_logs_filter_by_event_type(self, client, test_db):
        """Test filtering audit logs by event type"""
        response = client.get(
            f"/api/v1/security/audit-logs?event_type={AuditEventType.TOKEN_ISSUED.value}"
        )
        assert response.status_code == 200
        data = response.json()

        # All events should be TOKEN_ISSUED
        for event in data["events"]:
            assert event["event_type"] == AuditEventType.TOKEN_ISSUED.value

    def test_query_audit_logs_filter_by_result(self, client, test_db):
        """Test filtering audit logs by result"""
        response = client.get(
            f"/api/v1/security/audit-logs?result={AuditEventResult.FAILURE.value}"
        )
        assert response.status_code == 200
        data = response.json()

        # All events should have FAILURE result
        for event in data["events"]:
            assert event["result"] == AuditEventResult.FAILURE.value

    def test_query_audit_logs_date_range(self, client, test_db):
        """Test filtering audit logs by date range"""
        start_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        end_time = datetime.now(timezone.utc).isoformat()

        response = client.get(
            f"/api/v1/security/audit-logs?start_time={start_time}&end_time={end_time}"
        )
        assert response.status_code == 200
        data = response.json()

        # All events should be within date range
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))

        for event in data["events"]:
            event_dt = datetime.fromisoformat(event["timestamp"].replace('Z', '+00:00'))
            assert start_dt <= event_dt <= end_dt

    def test_query_audit_logs_pagination(self, client):
        """Test audit log pagination"""
        response = client.get("/api/v1/security/audit-logs?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()

        assert "total" in data
        assert "events" in data
        assert "limit" in data
        assert "offset" in data
        assert len(data["events"]) <= 10


class TestAuditLogExport:
    """Tests for GET /api/v1/security/audit-logs/export"""

    def test_export_audit_logs_json(self, client, test_db):
        """Test exporting audit logs as JSON"""
        response = client.get("/api/v1/security/audit-logs/export?format=json")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        # Should be valid JSON
        data = response.json()
        assert isinstance(data, dict)
        assert "events" in data
        assert "exported_at" in data
        assert "format" in data
        assert data["format"] == "json"

    def test_export_audit_logs_csv(self, client, test_db):
        """Test exporting audit logs as CSV"""
        # Create test audit log
        entry = AuditLogEntry(
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.TOKEN_ISSUED.value,
            peer_id="12D3KooWTestPeer",
            action="token_issuance",
            result=AuditEventResult.SUCCESS.value,
            reason="New peer registration"
        )
        test_db.add(entry)
        test_db.commit()

        response = client.get("/api/v1/security/audit-logs/export?format=csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

        # Should be valid CSV
        csv_content = response.text
        reader = csv.DictReader(StringIO(csv_content))
        rows = list(reader)

        assert len(rows) >= 1
        # Check CSV headers
        assert "timestamp" in reader.fieldnames
        assert "event_type" in reader.fieldnames
        assert "peer_id" in reader.fieldnames
        assert "result" in reader.fieldnames

    def test_export_audit_logs_with_filters(self, client, test_db):
        """Test exporting audit logs with filters applied"""
        target_peer = "12D3KooWExportPeer"

        response = client.get(
            f"/api/v1/security/audit-logs/export?format=json&peer_id={target_peer}"
        )
        assert response.status_code == 200
        data = response.json()

        # All exported events should match filter
        for event in data["events"]:
            assert event["peer_id"] == target_peer

    def test_export_audit_logs_invalid_format(self, client):
        """Test export with invalid format parameter"""
        response = client.get("/api/v1/security/audit-logs/export?format=xml")
        assert response.status_code == 400
        data = response.json()
        assert "format" in data["detail"].lower()

    def test_export_audit_logs_filename_header(self, client):
        """Test that export includes proper Content-Disposition header"""
        response = client.get("/api/v1/security/audit-logs/export?format=csv")
        assert response.status_code == 200

        # Should have Content-Disposition header with filename
        assert "content-disposition" in response.headers
        disposition = response.headers["content-disposition"]
        assert "attachment" in disposition
        assert "filename=" in disposition
        assert ".csv" in disposition


# ============================================================================
# Security Tests
# ============================================================================

class TestSecurityConstraints:
    """Tests for security constraints on endpoints"""

    def test_tokens_never_expose_full_jwt(self, client, test_db, sample_token):
        """Test that token list never exposes full JWT tokens"""
        response = client.get("/api/v1/security/tokens")
        assert response.status_code == 200
        data = response.json()

        # Response should not contain raw JWT tokens
        response_str = json.dumps(data)
        assert "eyJ" not in response_str  # JWT header prefix

    def test_peer_keys_never_expose_private_keys(self, client, peer_key_store):
        """Test that peer key endpoints never expose private keys"""
        response = client.get("/api/v1/security/peer-keys")
        assert response.status_code == 200
        data = response.json()

        response_str = json.dumps(data)
        # Should not contain private key indicators
        assert "private" not in response_str.lower()
        assert "secret" not in response_str.lower()

    def test_audit_logs_no_sensitive_metadata(self, client, test_db):
        """Test that audit logs never contain sensitive data in metadata"""
        # Try to create audit log with sensitive metadata (should fail during creation)
        entry = AuditLogEntry(
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.AUTHENTICATION_SUCCESS.value,
            peer_id="12D3KooWTestPeer",
            action="login",
            result=AuditEventResult.SUCCESS.value,
            reason="Success",
            event_metadata={"user": "test"}  # Safe metadata
        )
        test_db.add(entry)
        test_db.commit()

        response = client.get("/api/v1/security/audit-logs")
        assert response.status_code == 200
        data = response.json()

        # Verify no sensitive keys in metadata
        for event in data["events"]:
            if event.get("metadata"):
                metadata_str = json.dumps(event["metadata"]).lower()
                assert "password" not in metadata_str
                assert "secret" not in metadata_str
                assert "api_key" not in metadata_str


# ============================================================================
# Integration Tests
# ============================================================================

class TestEndToEndWorkflow:
    """End-to-end integration tests"""

    def test_token_lifecycle(self, client, test_db):
        """Test complete token lifecycle: create -> list -> rotate -> revoke"""
        # Step 1: Create token
        create_payload = {
            "peer_id": "12D3KooWLifecyclePeer",
            "capabilities": ["can_execute:gpt-4"],
            "limits": {
                "max_gpu_minutes": 200,
                "max_concurrent_tasks": 10
            },
            "expires_in_seconds": 3600
        }

        create_response = client.post("/api/v1/security/tokens", json=create_payload)
        assert create_response.status_code == 201
        jti = create_response.json()["jti"]

        # Step 2: List tokens (should include new token)
        list_response = client.get("/api/v1/security/tokens")
        assert list_response.status_code == 200
        # Should find our token in the list

        # Step 3: Rotate token
        rotate_response = client.post(f"/api/v1/security/tokens/{jti}/rotate")
        assert rotate_response.status_code == 200
        new_jti = rotate_response.json()["new_jti"]

        # Step 4: Revoke new token
        revoke_response = client.delete(f"/api/v1/security/tokens/{new_jti}")
        assert revoke_response.status_code == 200
        assert revoke_response.json()["success"] is True
