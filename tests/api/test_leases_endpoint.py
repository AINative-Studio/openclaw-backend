"""
Tests for lease management API endpoints.

Tests:
- POST /leases/issue - Issue task lease
- GET /leases/{lease_id}/validate - Validate lease token
- POST /leases/{lease_id}/revoke - Revoke active lease

Refs: Issue #122 - MCP Evaluation (native tools approach)
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import Mock, patch, MagicMock
from fastapi import status
from fastapi.testclient import TestClient

# Import schemas
from backend.schemas.lease_schemas import (
    LeaseIssueRequest,
    LeaseIssueResponse,
    LeaseValidateResponse,
    LeaseRevokeRequest,
    LeaseRevokeResponse,
    NodeCapabilitiesSnapshot,
)

# Import test fixtures
from tests.conftest import client, db_session


class TestLeaseIssueEndpoint:
    """Tests for POST /api/v1/leases/issue endpoint."""

    @pytest.mark.asyncio
    async def test_issue_lease_success(self, client: TestClient, db_session):
        """Test successful lease issuance."""
        # Arrange
        task_id = uuid4()
        peer_id = "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI"

        request_data = {
            "task_id": str(task_id),
            "peer_id": peer_id,
            "node_capabilities": {
                "cpu_cores": 8,
                "memory_mb": 16384,
                "gpu_available": True,
                "gpu_memory_mb": 8192,
                "storage_mb": 102400
            }
        }

        # Mock the service layer
        mock_lease = MagicMock()
        mock_lease.id = uuid4()
        mock_lease.task_id = task_id
        mock_lease.peer_id = peer_id
        mock_lease.lease_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
        mock_lease.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        mock_lease.task_complexity = "MEDIUM"
        mock_lease.lease_duration_seconds = 600

        with patch('backend.api.v1.endpoints.leases.TaskLeaseIssuanceService') as MockService:
            mock_service = MockService.return_value
            mock_service.issue_lease = Mock(return_value=mock_lease)

            # Act
            response = client.post("/api/v1/leases/issue", json=request_data)

            # Assert
            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["task_id"] == str(task_id)
            assert data["peer_id"] == peer_id
            assert "lease_token" in data
            assert data["task_complexity"] == "MEDIUM"
            assert data["lease_duration_seconds"] == 600

    @pytest.mark.asyncio
    async def test_issue_lease_invalid_peer_id(self, client: TestClient):
        """Test lease issuance with invalid peer ID format."""
        # Arrange
        request_data = {
            "task_id": str(uuid4()),
            "peer_id": "invalid-peer-id",  # Not a valid libp2p ID
        }

        # Act
        response = client.post("/api/v1/leases/issue", json=request_data)

        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "peer_id must be a valid libp2p peer ID" in response.text

    @pytest.mark.asyncio
    async def test_issue_lease_task_not_found(self, client: TestClient, db_session):
        """Test lease issuance for non-existent task."""
        # Arrange
        request_data = {
            "task_id": str(uuid4()),
            "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
        }

        with patch('backend.api.v1.endpoints.leases.TaskLeaseIssuanceService') as MockService:
            mock_service = MockService.return_value
            mock_service.issue_lease = Mock(side_effect=ValueError("Task not found"))

            # Act
            response = client.post("/api/v1/leases/issue", json=request_data)

            # Assert
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Task not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_issue_lease_task_already_leased(self, client: TestClient, db_session):
        """Test lease issuance for already-leased task."""
        # Arrange
        request_data = {
            "task_id": str(uuid4()),
            "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
        }

        with patch('backend.api.v1.endpoints.leases.TaskLeaseIssuanceService') as MockService:
            mock_service = MockService.return_value
            mock_service.issue_lease = Mock(side_effect=ValueError("Task is not in QUEUED status"))

            # Act
            response = client.post("/api/v1/leases/issue", json=request_data)

            # Assert
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "not in QUEUED status" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_issue_lease_insufficient_capabilities(self, client: TestClient, db_session):
        """Test lease issuance with insufficient node capabilities."""
        # Arrange
        request_data = {
            "task_id": str(uuid4()),
            "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
            "node_capabilities": {
                "cpu_cores": 2,
                "memory_mb": 2048,
                "gpu_available": False,
                "storage_mb": 10240
            }
        }

        with patch('backend.api.v1.endpoints.leases.TaskLeaseIssuanceService') as MockService:
            mock_service = MockService.return_value
            mock_service.issue_lease = Mock(
                side_effect=ValueError("Node capabilities do not meet task requirements")
            )

            # Act
            response = client.post("/api/v1/leases/issue", json=request_data)

            # Assert
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "capabilities" in response.json()["detail"].lower()


class TestLeaseValidateEndpoint:
    """Tests for GET /api/v1/leases/{lease_id}/validate endpoint."""

    @pytest.mark.asyncio
    async def test_validate_lease_success(self, client: TestClient, db_session):
        """Test successful lease validation."""
        # Arrange
        lease_id = uuid4()
        task_id = uuid4()
        peer_id = "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI"

        with patch('backend.api.v1.endpoints.leases.LeaseValidationService') as MockService:
            mock_service = MockService.return_value
            mock_service.validate_lease = Mock(return_value={
                "is_valid": True,
                "lease_id": lease_id,
                "task_id": task_id,
                "peer_id": peer_id,
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
                "is_expired": False,
                "is_revoked": False,
            })

            # Act
            response = client.get(f"/api/v1/leases/{lease_id}/validate")

            # Assert
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["is_valid"] is True
            assert data["lease_id"] == str(lease_id)
            assert data["is_expired"] is False
            assert data["is_revoked"] is False

    @pytest.mark.asyncio
    async def test_validate_lease_expired(self, client: TestClient, db_session):
        """Test validation of expired lease."""
        # Arrange
        lease_id = uuid4()

        with patch('backend.api.v1.endpoints.leases.LeaseValidationService') as MockService:
            mock_service = MockService.return_value
            mock_service.validate_lease = Mock(return_value={
                "is_valid": False,
                "lease_id": lease_id,
                "is_expired": True,
                "is_revoked": False,
                "error_message": "Lease has expired"
            })

            # Act
            response = client.get(f"/api/v1/leases/{lease_id}/validate")

            # Assert
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["is_valid"] is False
            assert data["is_expired"] is True
            assert "expired" in data["error_message"].lower()

    @pytest.mark.asyncio
    async def test_validate_lease_revoked(self, client: TestClient, db_session):
        """Test validation of revoked lease."""
        # Arrange
        lease_id = uuid4()

        with patch('backend.api.v1.endpoints.leases.LeaseValidationService') as MockService:
            mock_service = MockService.return_value
            mock_service.validate_lease = Mock(return_value={
                "is_valid": False,
                "lease_id": lease_id,
                "is_expired": False,
                "is_revoked": True,
                "error_message": "Lease has been revoked"
            })

            # Act
            response = client.get(f"/api/v1/leases/{lease_id}/validate")

            # Assert
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["is_valid"] is False
            assert data["is_revoked"] is True

    @pytest.mark.asyncio
    async def test_validate_lease_not_found(self, client: TestClient, db_session):
        """Test validation of non-existent lease."""
        # Arrange
        lease_id = uuid4()

        with patch('backend.api.v1.endpoints.leases.LeaseValidationService') as MockService:
            mock_service = MockService.return_value
            mock_service.validate_lease = Mock(return_value={
                "is_valid": False,
                "error_message": f"Lease {lease_id} not found"
            })

            # Act
            response = client.get(f"/api/v1/leases/{lease_id}/validate")

            # Assert
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["is_valid"] is False
            assert "not found" in data["error_message"].lower()


class TestLeaseRevokeEndpoint:
    """Tests for POST /api/v1/leases/{lease_id}/revoke endpoint."""

    @pytest.mark.asyncio
    async def test_revoke_lease_success(self, client: TestClient, db_session):
        """Test successful lease revocation."""
        # Arrange
        lease_id = uuid4()
        task_id = uuid4()
        peer_id = "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI"

        request_data = {
            "reason": "Node crashed - detected heartbeat timeout",
            "requeue_task": True
        }

        with patch('backend.api.v1.endpoints.leases.LeaseRevocationService') as MockService:
            mock_service = MockService.return_value
            mock_service.revoke_lease = Mock(return_value={
                "lease_id": lease_id,
                "task_id": task_id,
                "peer_id": peer_id,
                "revoked_at": datetime.now(timezone.utc),
                "reason": request_data["reason"],
                "task_requeued": True,
                "task_status": "queued"
            })

            # Act
            response = client.post(
                f"/api/v1/leases/{lease_id}/revoke",
                json=request_data
            )

            # Assert
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["lease_id"] == str(lease_id)
            assert data["task_requeued"] is True
            assert data["task_status"] == "queued"
            assert data["reason"] == request_data["reason"]

    @pytest.mark.asyncio
    async def test_revoke_lease_without_requeue(self, client: TestClient, db_session):
        """Test lease revocation without requeueing task."""
        # Arrange
        lease_id = uuid4()
        task_id = uuid4()
        peer_id = "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI"

        request_data = {
            "reason": "Manual revocation for testing",
            "requeue_task": False
        }

        with patch('backend.api.v1.endpoints.leases.LeaseRevocationService') as MockService:
            mock_service = MockService.return_value
            mock_service.revoke_lease = Mock(return_value={
                "lease_id": lease_id,
                "task_id": task_id,
                "peer_id": peer_id,
                "revoked_at": datetime.now(timezone.utc),
                "reason": request_data["reason"],
                "task_requeued": False,
                "task_status": "expired"
            })

            # Act
            response = client.post(
                f"/api/v1/leases/{lease_id}/revoke",
                json=request_data
            )

            # Assert
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["task_requeued"] is False
            assert data["task_status"] == "expired"

    @pytest.mark.asyncio
    async def test_revoke_lease_not_found(self, client: TestClient, db_session):
        """Test revocation of non-existent lease."""
        # Arrange
        lease_id = uuid4()
        request_data = {
            "reason": "Testing error handling",
            "requeue_task": True
        }

        with patch('backend.api.v1.endpoints.leases.LeaseRevocationService') as MockService:
            mock_service = MockService.return_value
            mock_service.revoke_lease = Mock(
                side_effect=ValueError(f"Lease {lease_id} not found")
            )

            # Act
            response = client.post(
                f"/api/v1/leases/{lease_id}/revoke",
                json=request_data
            )

            # Assert
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_revoke_lease_already_revoked(self, client: TestClient, db_session):
        """Test revocation of already-revoked lease."""
        # Arrange
        lease_id = uuid4()
        request_data = {
            "reason": "Double revocation test",
            "requeue_task": True
        }

        with patch('backend.api.v1.endpoints.leases.LeaseRevocationService') as MockService:
            mock_service = MockService.return_value
            mock_service.revoke_lease = Mock(
                side_effect=ValueError("Lease is already revoked")
            )

            # Act
            response = client.post(
                f"/api/v1/leases/{lease_id}/revoke",
                json=request_data
            )

            # Assert
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "already revoked" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_revoke_lease_empty_reason(self, client: TestClient):
        """Test lease revocation with empty reason."""
        # Arrange
        lease_id = uuid4()
        request_data = {
            "reason": "",  # Empty reason should be rejected
            "requeue_task": True
        }

        # Act
        response = client.post(
            f"/api/v1/leases/{lease_id}/revoke",
            json=request_data
        )

        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_revoke_lease_reason_too_long(self, client: TestClient):
        """Test lease revocation with excessively long reason."""
        # Arrange
        lease_id = uuid4()
        request_data = {
            "reason": "x" * 501,  # Exceeds 500 char limit
            "requeue_task": True
        }

        # Act
        response = client.post(
            f"/api/v1/leases/{lease_id}/revoke",
            json=request_data
        )

        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestLeaseSchemaValidation:
    """Tests for Pydantic schema validation."""

    def test_node_capabilities_snapshot_validation(self):
        """Test NodeCapabilitiesSnapshot schema validation."""
        # Valid data
        valid_data = {
            "cpu_cores": 8,
            "memory_mb": 16384,
            "gpu_available": True,
            "gpu_memory_mb": 8192,
            "storage_mb": 102400
        }
        snapshot = NodeCapabilitiesSnapshot(**valid_data)
        assert snapshot.cpu_cores == 8
        assert snapshot.gpu_available is True

        # Invalid: negative CPU cores
        with pytest.raises(ValueError):
            NodeCapabilitiesSnapshot(
                cpu_cores=-1,
                memory_mb=16384,
                storage_mb=102400
            )

        # Invalid: too little memory
        with pytest.raises(ValueError):
            NodeCapabilitiesSnapshot(
                cpu_cores=8,
                memory_mb=256,  # Below 512 MB minimum
                storage_mb=102400
            )

    def test_lease_issue_request_validation(self):
        """Test LeaseIssueRequest schema validation."""
        # Valid request
        valid_data = {
            "task_id": str(uuid4()),
            "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI"
        }
        request = LeaseIssueRequest(**valid_data)
        assert request.peer_id.startswith("12D3KooW")

        # Invalid: bad peer ID format
        with pytest.raises(ValueError, match="must be a valid libp2p peer ID"):
            LeaseIssueRequest(
                task_id=str(uuid4()),
                peer_id="not-a-libp2p-id"
            )

        # Invalid: peer ID too short
        with pytest.raises(ValueError, match="appears to be too short"):
            LeaseIssueRequest(
                task_id=str(uuid4()),
                peer_id="12D3KooW123"  # Too short
            )

    def test_lease_revoke_request_validation(self):
        """Test LeaseRevokeRequest schema validation."""
        # Valid request
        valid_data = {
            "reason": "Node crashed",
            "requeue_task": True
        }
        request = LeaseRevokeRequest(**valid_data)
        assert request.reason == "Node crashed"
        assert request.requeue_task is True

        # Invalid: empty reason
        with pytest.raises(ValueError):
            LeaseRevokeRequest(
                reason="",
                requeue_task=True
            )

        # Invalid: reason too long
        with pytest.raises(ValueError):
            LeaseRevokeRequest(
                reason="x" * 501,
                requeue_task=True
            )
