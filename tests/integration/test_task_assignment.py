"""
Task Assignment Orchestrator Integration Tests

Tests end-to-end task assignment flow including:
- Capability matching
- Lease issuance via DBOS
- TaskRequest via libp2p
- Assignment tracking
- Failure handling

Refs #35 (E5-S9: Task Assignment Orchestrator)
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid

from backend.models.task_models import Base, Task, TaskLease, TaskStatus
from backend.services.task_assignment_orchestrator import (
    TaskAssignmentOrchestrator,
    AssignmentResult,
    AssignmentStatus,
    NoCapableNodesError,
    PeerUnreachableError,
)


# Test database setup
@pytest.fixture(scope="function")
def db_engine():
    """Create in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create database session for each test"""
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def mock_libp2p_client():
    """Mock libp2p client for P2P communication"""
    client = AsyncMock()
    client.send_task_request = AsyncMock()
    client.is_peer_reachable = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_dbos_service():
    """Mock DBOS service for lease issuance"""
    service = AsyncMock()
    service.issue_task_lease = AsyncMock()
    service.revoke_task_lease = AsyncMock()
    return service


@pytest.fixture
def orchestrator(db_session, mock_libp2p_client, mock_dbos_service):
    """Create TaskAssignmentOrchestrator instance"""
    return TaskAssignmentOrchestrator(
        db_session=db_session,
        libp2p_client=mock_libp2p_client,
        dbos_service=mock_dbos_service,
    )


class TestTaskAssignmentEndToEnd:
    """Test complete task assignment flow"""

    @pytest.mark.asyncio
    async def test_assign_task_end_to_end(
        self, orchestrator, db_session, mock_libp2p_client, mock_dbos_service
    ):
        """
        GIVEN a queued task and an available node with capabilities
        WHEN orchestrating task assignment
        THEN it should complete full flow:
        - Match task to capable node
        - Issue lease via DBOS
        - Send TaskRequest via libp2p
        - Track assignment successfully
        """
        # Arrange: Create task
        task_id = f"task-{uuid.uuid4()}"
        task = Task(
            task_id=task_id,
            status=TaskStatus.QUEUED.value,
            payload={
                "type": "model_inference",
                "model": "llama-2-7b",
                "input": "test input",
            },
            idempotency_key=f"idem-{uuid.uuid4()}",
        )
        db_session.add(task)
        db_session.commit()

        # Arrange: Mock available node with capabilities
        available_node = {
            "peer_id": "12D3KooWTest123",
            "capabilities": {
                "cpu_cores": 8,
                "memory_mb": 16384,
                "gpu_available": True,
                "models": ["llama-2-7b", "gpt-3.5-turbo"],
            },
            "status": "healthy",
        }

        # Arrange: Mock DBOS lease issuance
        lease_token = "lease-token-abc123"
        mock_dbos_service.issue_task_lease.return_value = {
            "token": lease_token,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            "owner_peer_id": available_node["peer_id"],
        }

        # Arrange: Mock libp2p successful request
        mock_libp2p_client.send_task_request.return_value = {
            "status": "accepted",
            "message_id": "msg-123",
        }

        # Act: Assign task
        result = await orchestrator.assign_task(
            task_id=task_id,
            available_nodes=[available_node],
        )

        # Assert: Assignment successful
        assert result.status == AssignmentStatus.SUCCESS
        assert result.task_id == task_id
        assert result.assigned_peer_id == available_node["peer_id"]
        assert result.lease_token == lease_token

        # Assert: Task status updated
        db_session.refresh(task)
        assert task.status == TaskStatus.LEASED.value

        # Assert: Lease created in database
        lease = db_session.query(TaskLease).filter_by(task_id=task_id).first()
        assert lease is not None
        assert lease.owner_peer_id == available_node["peer_id"]
        assert lease.token == lease_token

        # Assert: DBOS service called
        mock_dbos_service.issue_task_lease.assert_called_once()

        # Assert: libp2p request sent
        mock_libp2p_client.send_task_request.assert_called_once()
        call_args = mock_libp2p_client.send_task_request.call_args
        assert call_args[1]["peer_id"] == available_node["peer_id"]
        assert call_args[1]["task_id"] == task_id
        assert call_args[1]["lease_token"] == lease_token

    @pytest.mark.asyncio
    async def test_assignment_no_capable_nodes(
        self, orchestrator, db_session
    ):
        """
        GIVEN a task requiring GPU capabilities
        WHEN no nodes have GPU available
        THEN task should remain queued with appropriate error
        """
        # Arrange: Create GPU task
        task_id = f"task-{uuid.uuid4()}"
        task = Task(
            task_id=task_id,
            status=TaskStatus.QUEUED.value,
            payload={
                "type": "gpu_training",
                "requires_gpu": True,
            },
            idempotency_key=f"idem-{uuid.uuid4()}",
        )
        db_session.add(task)
        db_session.commit()

        # Arrange: Only CPU nodes available
        available_nodes = [
            {
                "peer_id": "12D3KooWCPU1",
                "capabilities": {
                    "cpu_cores": 4,
                    "memory_mb": 8192,
                    "gpu_available": False,
                },
                "status": "healthy",
            },
            {
                "peer_id": "12D3KooWCPU2",
                "capabilities": {
                    "cpu_cores": 8,
                    "memory_mb": 16384,
                    "gpu_available": False,
                },
                "status": "healthy",
            },
        ]

        # Act & Assert: Should raise NoCapableNodesError
        with pytest.raises(NoCapableNodesError) as exc_info:
            await orchestrator.assign_task(
                task_id=task_id,
                available_nodes=available_nodes,
                required_capabilities={"gpu_available": True},
            )

        # Assert: Task remains queued
        db_session.refresh(task)
        assert task.status == TaskStatus.QUEUED.value

        # Assert: No lease created
        lease_count = db_session.query(TaskLease).filter_by(task_id=task_id).count()
        assert lease_count == 0

        # Assert: Error message contains details
        assert "No capable nodes" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_assignment_peer_unreachable(
        self, orchestrator, db_session, mock_libp2p_client, mock_dbos_service
    ):
        """
        GIVEN a peer that appears available
        WHEN peer becomes offline during task request
        THEN should revoke lease and requeue task
        """
        # Arrange: Create task
        task_id = f"task-{uuid.uuid4()}"
        task = Task(
            task_id=task_id,
            status=TaskStatus.QUEUED.value,
            payload={"type": "simple_task"},
            idempotency_key=f"idem-{uuid.uuid4()}",
        )
        db_session.add(task)
        db_session.commit()

        # Arrange: Node appears available
        available_node = {
            "peer_id": "12D3KooWOffline",
            "capabilities": {"cpu_cores": 4},
            "status": "healthy",
        }

        # Arrange: DBOS issues lease
        lease_token = "lease-token-offline"
        mock_dbos_service.issue_task_lease.return_value = {
            "token": lease_token,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            "owner_peer_id": available_node["peer_id"],
        }

        # Arrange: libp2p peer unreachable (timeout)
        mock_libp2p_client.send_task_request.side_effect = Exception(
            "Peer unreachable: connection timeout"
        )

        # Act & Assert: Should handle gracefully
        with pytest.raises(PeerUnreachableError) as exc_info:
            await orchestrator.assign_task(
                task_id=task_id,
                available_nodes=[available_node],
            )

        # Assert: Task requeued
        db_session.refresh(task)
        assert task.status == TaskStatus.QUEUED.value

        # Assert: Lease revoked via DBOS
        mock_dbos_service.revoke_task_lease.assert_called_once()
        revoke_call = mock_dbos_service.revoke_task_lease.call_args
        assert revoke_call[1]["lease_token"] == lease_token
        assert "unreachable" in revoke_call[1]["reason"].lower()

        # Assert: Lease marked as revoked in DB
        lease = db_session.query(TaskLease).filter_by(task_id=task_id).first()
        if lease:
            # If lease was created before failure, verify it's not active
            # Use naive datetime for SQLite comparison
            assert lease.expires_at < datetime.now(timezone.utc).replace(tzinfo=None)


class TestCapabilityMatching:
    """Test capability matching logic"""

    @pytest.mark.asyncio
    async def test_match_simple_cpu_requirement(self, orchestrator):
        """
        GIVEN task requiring 4 CPU cores
        WHEN matching against available nodes
        THEN should select node with sufficient CPU
        """
        # Arrange
        task_requirements = {"cpu_cores": 4}
        available_nodes = [
            {
                "peer_id": "node1",
                "capabilities": {"cpu_cores": 2},
                "status": "healthy",
            },
            {
                "peer_id": "node2",
                "capabilities": {"cpu_cores": 8},
                "status": "healthy",
            },
        ]

        # Act
        matched_node = orchestrator._match_node_to_task(
            task_requirements, available_nodes
        )

        # Assert
        assert matched_node is not None
        assert matched_node["peer_id"] == "node2"
        assert matched_node["capabilities"]["cpu_cores"] >= 4

    @pytest.mark.asyncio
    async def test_match_gpu_requirement(self, orchestrator):
        """
        GIVEN task requiring GPU
        WHEN matching against mixed nodes
        THEN should select only GPU-enabled node
        """
        # Arrange
        task_requirements = {"gpu_available": True, "gpu_memory_mb": 8000}
        available_nodes = [
            {
                "peer_id": "cpu-node",
                "capabilities": {"cpu_cores": 16, "gpu_available": False},
                "status": "healthy",
            },
            {
                "peer_id": "gpu-node",
                "capabilities": {
                    "cpu_cores": 8,
                    "gpu_available": True,
                    "gpu_memory_mb": 16384,
                },
                "status": "healthy",
            },
        ]

        # Act
        matched_node = orchestrator._match_node_to_task(
            task_requirements, available_nodes
        )

        # Assert
        assert matched_node is not None
        assert matched_node["peer_id"] == "gpu-node"
        assert matched_node["capabilities"]["gpu_available"] is True

    @pytest.mark.asyncio
    async def test_no_match_insufficient_resources(self, orchestrator):
        """
        GIVEN task requiring 32GB RAM
        WHEN all nodes have less RAM
        THEN should return None
        """
        # Arrange
        task_requirements = {"memory_mb": 32768}
        available_nodes = [
            {
                "peer_id": "node1",
                "capabilities": {"memory_mb": 8192},
                "status": "healthy",
            },
            {
                "peer_id": "node2",
                "capabilities": {"memory_mb": 16384},
                "status": "healthy",
            },
        ]

        # Act
        matched_node = orchestrator._match_node_to_task(
            task_requirements, available_nodes
        )

        # Assert
        assert matched_node is None


class TestLeaseIssuance:
    """Test lease issuance integration"""

    @pytest.mark.asyncio
    async def test_create_lease_in_database(
        self, orchestrator, db_session, mock_dbos_service
    ):
        """
        GIVEN a matched task and node
        WHEN creating lease
        THEN should persist lease with correct fields
        """
        # Arrange: Create task
        task_id = f"task-{uuid.uuid4()}"
        task = Task(
            task_id=task_id,
            status=TaskStatus.QUEUED.value,
            payload={},
            idempotency_key=f"idem-{uuid.uuid4()}",
        )
        db_session.add(task)
        db_session.commit()

        peer_id = "12D3KooWTest"
        lease_token = f"token-{uuid.uuid4()}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

        # Act: Create lease
        lease = orchestrator._create_task_lease(
            task_id=task_id,
            owner_peer_id=peer_id,
            lease_token=lease_token,
            expires_at=expires_at,
        )

        # Assert: Lease persisted
        assert lease.id is not None
        assert lease.task_id == task_id
        assert lease.owner_peer_id == peer_id
        assert lease.token == lease_token
        # Compare in naive format since SQLite stores naive datetimes
        assert lease.expires_at == expires_at.replace(tzinfo=None)

        # Assert: Can be queried
        db_lease = db_session.query(TaskLease).filter_by(token=lease_token).first()
        assert db_lease is not None
        assert db_lease.task_id == task_id

    @pytest.mark.asyncio
    async def test_lease_expiration_check(self, db_session):
        """
        GIVEN an expired lease
        WHEN checking expiration
        THEN should correctly identify as expired
        """
        # Arrange: Create expired lease
        task_id = f"task-{uuid.uuid4()}"
        task = Task(
            task_id=task_id,
            status=TaskStatus.LEASED.value,
            payload={},
            idempotency_key=f"idem-{uuid.uuid4()}",
        )
        db_session.add(task)

        expired_lease = TaskLease(
            task_id=task_id,
            owner_peer_id="12D3KooWExpired",
            token="expired-token",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        db_session.add(expired_lease)
        db_session.commit()

        # Act: Check expiration
        is_expired = expired_lease.is_expired()

        # Assert
        assert is_expired is True


class TestAssignmentTracking:
    """Test assignment state tracking"""

    @pytest.mark.asyncio
    async def test_track_assignment_metadata(
        self, orchestrator, db_session, mock_libp2p_client, mock_dbos_service
    ):
        """
        GIVEN a successful assignment
        WHEN tracking assignment
        THEN should store metadata for monitoring
        """
        # Arrange
        task_id = f"task-{uuid.uuid4()}"
        task = Task(
            task_id=task_id,
            status=TaskStatus.QUEUED.value,
            payload={},
            idempotency_key=f"idem-{uuid.uuid4()}",
        )
        db_session.add(task)
        db_session.commit()

        available_node = {
            "peer_id": "12D3KooWTrack",
            "capabilities": {"cpu_cores": 4},
            "status": "healthy",
        }

        mock_dbos_service.issue_task_lease.return_value = {
            "token": "track-token",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            "owner_peer_id": available_node["peer_id"],
        }

        mock_libp2p_client.send_task_request.return_value = {
            "status": "accepted",
            "message_id": "msg-track",
        }

        # Act
        result = await orchestrator.assign_task(
            task_id=task_id,
            available_nodes=[available_node],
        )

        # Assert: Metadata tracked
        assert result.assignment_timestamp is not None
        assert result.libp2p_message_id == "msg-track"
        assert result.is_successful() is True

    @pytest.mark.asyncio
    async def test_update_task_status_on_assignment(
        self, orchestrator, db_session, mock_libp2p_client, mock_dbos_service
    ):
        """
        GIVEN task in QUEUED status
        WHEN successfully assigned
        THEN task status should update to LEASED
        """
        # Arrange
        task_id = f"task-{uuid.uuid4()}"
        task = Task(
            task_id=task_id,
            status=TaskStatus.QUEUED.value,
            payload={},
            idempotency_key=f"idem-{uuid.uuid4()}",
        )
        db_session.add(task)
        db_session.commit()

        available_node = {
            "peer_id": "12D3KooWStatus",
            "capabilities": {},
            "status": "healthy",
        }

        mock_dbos_service.issue_task_lease.return_value = {
            "token": "status-token",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            "owner_peer_id": available_node["peer_id"],
        }

        mock_libp2p_client.send_task_request.return_value = {
            "status": "accepted"
        }

        # Act
        await orchestrator.assign_task(
            task_id=task_id,
            available_nodes=[available_node],
        )

        # Assert
        db_session.refresh(task)
        assert task.status == TaskStatus.LEASED.value

    @pytest.mark.asyncio
    async def test_get_assignment_status(
        self, orchestrator, db_session, mock_libp2p_client, mock_dbos_service
    ):
        """
        GIVEN an assigned task with active lease
        WHEN getting assignment status
        THEN should return lease information
        """
        # Arrange: Create task and lease
        task_id = f"task-{uuid.uuid4()}"
        task = Task(
            task_id=task_id,
            status=TaskStatus.LEASED.value,
            payload={},
            idempotency_key=f"idem-{uuid.uuid4()}",
        )
        db_session.add(task)

        lease = TaskLease(
            task_id=task_id,
            owner_peer_id="12D3KooWActive",
            token="active-token",
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5),
        )
        db_session.add(lease)
        db_session.commit()

        # Act
        status = await orchestrator.get_assignment_status(task_id)

        # Assert
        assert status["task_id"] == task_id
        assert status["status"] == TaskStatus.LEASED.value
        assert status["has_active_lease"] is True
        assert status["active_lease"] is not None
        assert status["active_lease"]["owner_peer_id"] == "12D3KooWActive"


class TestErrorHandling:
    """Test error handling scenarios"""

    @pytest.mark.asyncio
    async def test_task_not_found(self, orchestrator):
        """
        GIVEN non-existent task
        WHEN trying to assign
        THEN should raise TaskAssignmentError
        """
        from backend.services.task_assignment_orchestrator import TaskAssignmentError

        with pytest.raises(TaskAssignmentError) as exc_info:
            await orchestrator.assign_task(
                task_id="non-existent-task",
                available_nodes=[],
            )

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_task_not_queued(self, orchestrator, db_session):
        """
        GIVEN task already in LEASED status
        WHEN trying to assign again
        THEN should raise TaskAssignmentError
        """
        from backend.services.task_assignment_orchestrator import TaskAssignmentError

        # Arrange: Create task in LEASED status
        task_id = f"task-{uuid.uuid4()}"
        task = Task(
            task_id=task_id,
            status=TaskStatus.LEASED.value,
            payload={},
            idempotency_key=f"idem-{uuid.uuid4()}",
        )
        db_session.add(task)
        db_session.commit()

        # Act & Assert
        with pytest.raises(TaskAssignmentError) as exc_info:
            await orchestrator.assign_task(
                task_id=task_id,
                available_nodes=[{"peer_id": "test", "capabilities": {}}],
            )

        assert "not in QUEUED status" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_to_dict_methods(self, db_session):
        """
        GIVEN task and lease models
        WHEN converting to dict
        THEN should include all fields
        """
        # Arrange
        task_id = f"task-{uuid.uuid4()}"
        task = Task(
            task_id=task_id,
            status=TaskStatus.QUEUED.value,
            payload={"test": "data"},
            idempotency_key=f"idem-{uuid.uuid4()}",
        )
        db_session.add(task)

        lease = TaskLease(
            task_id=task_id,
            owner_peer_id="12D3KooWTest",
            token="test-token",
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(lease)
        db_session.commit()

        # Act
        task_dict = task.to_dict()
        lease_dict = lease.to_dict()

        # Assert
        assert task_dict["task_id"] == task_id
        assert task_dict["status"] == TaskStatus.QUEUED.value
        assert task_dict["payload"] == {"test": "data"}

        assert lease_dict["task_id"] == task_id
        assert lease_dict["owner_peer_id"] == "12D3KooWTest"
        assert lease_dict["token"] == "test-token"
