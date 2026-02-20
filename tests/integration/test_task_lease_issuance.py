"""
Integration Tests for Task Lease Issuance Service

Tests task lease issuance workflow including capability matching,
JWT token generation, and lease management.

Refs #27 (E5-S1: Task Lease Issuance)
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import jwt

from backend.models.task import Task, TaskStatus
from backend.models.task_lease import TaskLease
from backend.models.task_lease_models import NodeCapability, TaskComplexity
from backend.schemas.task_lease_schemas import TaskLeaseRequest
from backend.services.task_lease_issuance_service import (
    TaskLeaseIssuanceService,
    CapabilityMismatchError,
    TaskNotAvailableError,
    LeaseIssuanceError
)


@pytest.fixture
def test_db_session():
    """
    Mock database session for testing.
    In production, this would use actual database connection.
    """
    from unittest.mock import MagicMock
    return MagicMock()


@pytest.fixture
def lease_service(test_db_session):
    """Create task lease issuance service instance"""
    return TaskLeaseIssuanceService(db=test_db_session)


@pytest.fixture
def queued_task():
    """Create a queued task for testing"""
    task_id = str(uuid4())
    task = Task()
    task.id = task_id
    task.task_type = "compute"
    task.description = "Test computation task"
    task.complexity = "medium"
    task.status = TaskStatus.QUEUED
    task.required_capabilities = {
        "cpu_cores": 2,
        "memory_mb": 4096,
        "gpu_available": False,
        "storage_mb": 10000
    }
    task.payload = {"operation": "matrix_multiply", "size": 1000}
    task.priority = 50
    task.created_at = datetime.now(timezone.utc)
    return task


@pytest.fixture
def gpu_task():
    """Create a GPU-required task for testing"""
    task_id = str(uuid4())
    task = Task()
    task.id = task_id
    task.task_type = "gpu_compute"
    task.description = "GPU computation task"
    task.complexity = "high"
    task.status = TaskStatus.QUEUED
    task.required_capabilities = {
        "cpu_cores": 4,
        "memory_mb": 8192,
        "gpu_available": True,
        "gpu_memory_mb": 8192,
        "storage_mb": 20000
    }
    task.payload = {"operation": "neural_network_training"}
    task.priority = 80
    task.created_at = datetime.now(timezone.utc)
    return task


@pytest.fixture
def capable_node():
    """Create a capable node for testing"""
    node = NodeCapability()
    node.id = uuid4()
    node.peer_id = "QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG"
    node.node_address = "/ip4/192.168.1.100/tcp/4001"
    node.capabilities = {
        "cpu_cores": 8,
        "memory_mb": 16384,
        "gpu_available": False,
        "storage_mb": 100000,
        "network_bandwidth_mbps": 1000
    }
    node.is_available = True
    node.current_task_count = 0
    node.max_concurrent_tasks = 5
    node.last_seen_at = datetime.now(timezone.utc)
    return node


@pytest.fixture
def gpu_node():
    """Create a GPU-capable node for testing"""
    node = NodeCapability()
    node.id = uuid4()
    node.peer_id = "QmXdNGRqXEbdVhFNhGvfLqNvHvKLqVGzJfBLqrMuaJTUvN"
    node.node_address = "/ip4/192.168.1.101/tcp/4001"
    node.capabilities = {
        "cpu_cores": 16,
        "memory_mb": 32768,
        "gpu_available": True,
        "gpu_memory_mb": 16384,
        "storage_mb": 500000,
        "network_bandwidth_mbps": 10000
    }
    node.is_available = True
    node.current_task_count = 0
    node.max_concurrent_tasks = 3
    node.last_seen_at = datetime.now(timezone.utc)
    return node


@pytest.fixture
def incapable_node():
    """Create an under-resourced node for testing"""
    node = NodeCapability()
    node.id = uuid4()
    node.peer_id = "QmPoorNodeWithLimitedResources123456789ABCDEF"
    node.node_address = "/ip4/192.168.1.102/tcp/4001"
    node.capabilities = {
        "cpu_cores": 1,
        "memory_mb": 1024,
        "gpu_available": False,
        "storage_mb": 5000,
        "network_bandwidth_mbps": 100
    }
    node.is_available = True
    node.current_task_count = 0
    node.max_concurrent_tasks = 1
    node.last_seen_at = datetime.now(timezone.utc)
    return node


class TestTaskLeaseIssuance:
    """Test suite for task lease issuance workflow"""

    async def test_issue_lease_to_capable_node(
        self,
        lease_service,
        queued_task,
        capable_node,
        test_db_session
    ):
        """
        Given a capable node and queued task
        When issuing lease
        Then should return valid token and update task status

        BDD Scenario:
          Given a queued task requiring 2 CPU cores and 4GB memory
          And a capable node with 8 CPU cores and 16GB memory
          When the coordinator issues a lease
          Then the lease should be created successfully
          And the task status should be updated to LEASED
          And a valid JWT token should be returned
        """
        # Arrange
        lease_request = TaskLeaseRequest(
            task_id=queued_task.id,
            peer_id=capable_node.peer_id,
            node_address=capable_node.node_address,
            node_capabilities=capable_node.capabilities
        )

        # Mock database query responses
        test_db_session.query().filter().first.side_effect = [
            queued_task,  # First call returns task
            capable_node   # Second call returns node capability
        ]

        # Act
        lease_response = await lease_service.issue_lease(lease_request)

        # Assert
        assert lease_response is not None
        assert lease_response.task_id == queued_task.id
        assert lease_response.peer_id == capable_node.peer_id
        assert lease_response.lease_token is not None
        assert len(lease_response.lease_token) > 0

        # Verify JWT token structure
        secret_key = lease_service._get_secret_key()
        decoded = jwt.decode(
            lease_response.lease_token,
            secret_key,
            algorithms=["HS256"]
        )
        assert decoded["task_id"] == str(queued_task.id)
        assert decoded["peer_id"] == capable_node.peer_id
        assert "exp" in decoded

        # Verify task was updated to LEASED status
        test_db_session.commit.assert_called()

    async def test_reject_lease_for_incapable_node(
        self,
        lease_service,
        queued_task,
        incapable_node,
        test_db_session
    ):
        """
        Given a node without sufficient resources
        When issuing lease for resource-intensive task
        Then should reject with capability error

        BDD Scenario:
          Given a task requiring 2 CPU cores and 4GB memory
          And an incapable node with only 1 CPU core and 1GB memory
          When the coordinator attempts to issue a lease
          Then the request should be rejected with CapabilityMismatchError
          And the error should detail the missing capabilities
        """
        # Arrange
        lease_request = TaskLeaseRequest(
            task_id=queued_task.id,
            peer_id=incapable_node.peer_id,
            node_address=incapable_node.node_address,
            node_capabilities=incapable_node.capabilities
        )

        test_db_session.query().filter().first.side_effect = [
            queued_task,
            incapable_node
        ]

        # Act & Assert
        with pytest.raises(CapabilityMismatchError) as exc_info:
            await lease_service.issue_lease(lease_request)

        error = exc_info.value
        assert "cpu_cores" in str(error).lower() or "memory" in str(error).lower()
        assert error.required_capabilities is not None
        assert error.provided_capabilities is not None

    async def test_reject_lease_for_gpu_task_without_gpu(
        self,
        lease_service,
        gpu_task,
        capable_node,
        test_db_session
    ):
        """
        Given a node without GPU
        When issuing GPU-required task
        Then should reject with capability error

        BDD Scenario:
          Given a task requiring GPU with 8GB GPU memory
          And a capable CPU-only node
          When the coordinator attempts to issue a lease
          Then the request should be rejected with CapabilityMismatchError
          And the error should indicate GPU requirement not met
        """
        # Arrange
        lease_request = TaskLeaseRequest(
            task_id=gpu_task.id,
            peer_id=capable_node.peer_id,
            node_address=capable_node.node_address,
            node_capabilities=capable_node.capabilities
        )

        test_db_session.query().filter().first.side_effect = [
            gpu_task,
            capable_node
        ]

        # Act & Assert
        with pytest.raises(CapabilityMismatchError) as exc_info:
            await lease_service.issue_lease(lease_request)

        error = exc_info.value
        assert "gpu" in str(error).lower()

    async def test_issue_lease_for_gpu_task_with_gpu_node(
        self,
        lease_service,
        gpu_task,
        gpu_node,
        test_db_session
    ):
        """
        Given a GPU-capable node
        When issuing GPU task
        Then should issue lease successfully

        BDD Scenario:
          Given a task requiring GPU with 8GB GPU memory
          And a GPU-capable node with 16GB GPU memory
          When the coordinator issues a lease
          Then the lease should be created successfully
          And the task should be updated to LEASED status
        """
        # Arrange
        lease_request = TaskLeaseRequest(
            task_id=gpu_task.id,
            peer_id=gpu_node.peer_id,
            node_address=gpu_node.node_address,
            node_capabilities=gpu_node.capabilities
        )

        test_db_session.query().filter().first.side_effect = [
            gpu_task,
            gpu_node
        ]

        # Act
        lease_response = await lease_service.issue_lease(lease_request)

        # Assert
        assert lease_response is not None
        assert lease_response.task_id == gpu_task.id
        assert lease_response.peer_id == gpu_node.peer_id

    async def test_lease_token_contains_claims(
        self,
        lease_service,
        queued_task,
        capable_node,
        test_db_session
    ):
        """
        Given an issued lease
        When decoding token
        Then should contain task_id, peer_id, expires_at

        BDD Scenario:
          Given a successfully issued lease
          When the JWT token is decoded
          Then it should contain task_id claim
          And it should contain peer_id claim
          And it should contain exp (expires_at) claim
          And the expiration should be 5-15 minutes in the future
        """
        # Arrange
        lease_request = TaskLeaseRequest(
            task_id=queued_task.id,
            peer_id=capable_node.peer_id,
            node_address=capable_node.node_address,
            node_capabilities=capable_node.capabilities
        )

        test_db_session.query().filter().first.side_effect = [
            queued_task,
            capable_node
        ]

        # Act
        lease_response = await lease_service.issue_lease(lease_request)

        # Assert - Decode and verify JWT claims
        secret_key = lease_service._get_secret_key()
        decoded = jwt.decode(
            lease_response.lease_token,
            secret_key,
            algorithms=["HS256"]
        )

        # Required claims
        assert "task_id" in decoded
        assert "peer_id" in decoded
        assert "exp" in decoded

        # Verify claim values
        assert decoded["task_id"] == str(queued_task.id)
        assert decoded["peer_id"] == capable_node.peer_id

        # Verify expiration is in future and within expected range
        exp_timestamp = decoded["exp"]
        now_timestamp = datetime.now(timezone.utc).timestamp()
        time_diff = exp_timestamp - now_timestamp

        # For MEDIUM complexity, expect ~10 minutes (600 seconds)
        assert 5 * 60 <= time_diff <= 15 * 60, \
            f"Expiration should be 5-15 minutes, got {time_diff / 60} minutes"

    async def test_lease_duration_based_on_complexity(
        self,
        lease_service,
        test_db_session,
        capable_node
    ):
        """
        Given tasks with different complexity levels
        When issuing leases
        Then lease duration should match complexity

        BDD Scenario:
          Given a LOW complexity task
          When a lease is issued
          Then the expiration should be ~5 minutes

          Given a MEDIUM complexity task
          When a lease is issued
          Then the expiration should be ~10 minutes

          Given a HIGH complexity task
          When a lease is issued
          Then the expiration should be ~15 minutes
        """
        # Test LOW complexity
        low_task = Task()
        low_task.id = str(uuid4())
        low_task.task_type = "simple"
        low_task.complexity = "low"
        low_task.status = TaskStatus.QUEUED
        low_task.required_capabilities = {"cpu_cores": 1, "memory_mb": 1024}
        low_task.payload = {}
        low_task.created_at = datetime.now(timezone.utc)

        lease_request_low = TaskLeaseRequest(
            task_id=low_task.id,
            peer_id=capable_node.peer_id,
            node_capabilities=capable_node.capabilities
        )

        test_db_session.query().filter().first.side_effect = [
            low_task,
            capable_node
        ]

        response_low = await lease_service.issue_lease(lease_request_low)
        duration_low = (response_low.expires_at - response_low.issued_at).total_seconds()
        assert 4.5 * 60 <= duration_low <= 5.5 * 60, \
            f"LOW complexity should have ~5 min lease, got {duration_low / 60} minutes"

    async def test_reject_lease_for_already_leased_task(
        self,
        lease_service,
        queued_task,
        capable_node,
        test_db_session
    ):
        """
        Given a task already leased to another node
        When attempting to issue another lease
        Then should reject with TaskNotAvailableError

        BDD Scenario:
          Given a task that is already in LEASED status
          When another node requests a lease
          Then the request should be rejected with TaskNotAvailableError
        """
        # Arrange - task is already leased
        queued_task.status = TaskStatus.LEASED

        lease_request = TaskLeaseRequest(
            task_id=queued_task.id,
            peer_id=capable_node.peer_id,
            node_capabilities=capable_node.capabilities
        )

        test_db_session.query().filter().first.return_value = queued_task

        # Act & Assert
        with pytest.raises(TaskNotAvailableError) as exc_info:
            await lease_service.issue_lease(lease_request)

        assert "already leased" in str(exc_info.value).lower() or \
               "not available" in str(exc_info.value).lower()

    async def test_reject_lease_for_nonexistent_task(
        self,
        lease_service,
        capable_node,
        test_db_session
    ):
        """
        Given a non-existent task ID
        When attempting to issue lease
        Then should reject with appropriate error

        BDD Scenario:
          Given a task ID that doesn't exist in the database
          When a node requests a lease
          Then the request should be rejected with TaskNotAvailableError
        """
        # Arrange
        fake_task_id = uuid4()
        lease_request = TaskLeaseRequest(
            task_id=fake_task_id,
            peer_id=capable_node.peer_id,
            node_capabilities=capable_node.capabilities
        )

        test_db_session.query().filter().first.return_value = None

        # Act & Assert
        with pytest.raises(TaskNotAvailableError):
            await lease_service.issue_lease(lease_request)

    async def test_lease_creates_database_record(
        self,
        lease_service,
        queued_task,
        capable_node,
        test_db_session
    ):
        """
        Given successful lease issuance
        When lease is created
        Then should create TaskLease database record

        BDD Scenario:
          Given a successful lease issuance
          When the lease is created
          Then a TaskLease record should be added to the database
          And the record should contain peer_id, task_id, and lease_token
          And the record should be committed to the database
        """
        # Arrange
        lease_request = TaskLeaseRequest(
            task_id=queued_task.id,
            peer_id=capable_node.peer_id,
            node_capabilities=capable_node.capabilities
        )

        test_db_session.query().filter().first.side_effect = [
            queued_task,
            capable_node
        ]

        # Act
        await lease_service.issue_lease(lease_request)

        # Assert
        test_db_session.add.assert_called()
        test_db_session.commit.assert_called()

        # Verify TaskLease object was created
        call_args = test_db_session.add.call_args_list
        lease_obj = call_args[-1][0][0]  # Get the object passed to add()
        assert hasattr(lease_obj, 'task_id')
        assert hasattr(lease_obj, 'peer_id')
        assert hasattr(lease_obj, 'lease_token')
