"""
Integration tests for Recovery Workflow Orchestrator (E6-S6)

Tests unified recovery orchestration including failure type classification,
recovery workflow dispatch, progress tracking, and audit logging.
Follows BDD-style testing pattern.

Refs #E6-S6
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy.orm import Session
from unittest.mock import Mock, AsyncMock, patch

from backend.models.task_queue import Task, TaskLease, TaskStatus, TaskPriority
from backend.models.heartbeat import PeerState, PeerEvent
from backend.services.recovery_orchestrator import (
    RecoveryOrchestrator,
    FailureType,
    RecoveryAction,
    RecoveryStatus,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.db.base import Base


# Use SQLite for testing
TEST_DATABASE_URL = "sqlite:///./test_recovery_orchestrator.db"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """
    Create a fresh database session for each test
    """
    # Create all tables
    Base.metadata.create_all(bind=test_engine)

    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Clean up after test
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def heartbeat_subscriber_mock():
    """
    Mock heartbeat subscriber for crash detection
    """
    mock = Mock()
    mock.get_peer_state = Mock(return_value=None)
    mock.check_peer_health = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def lease_validation_service_mock():
    """
    Mock lease validation service
    """
    mock = Mock()
    mock.lease_store = {}
    return mock


@pytest.fixture
def task_requeue_service_mock():
    """
    Mock task requeue service
    """
    mock = Mock()
    mock.requeue_task = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def recovery_orchestrator(
    db_session,
    heartbeat_subscriber_mock,
    lease_validation_service_mock,
    task_requeue_service_mock
):
    """
    Create RecoveryOrchestrator instance with mocked dependencies
    """
    return RecoveryOrchestrator(
        db=db_session,
        heartbeat_subscriber=heartbeat_subscriber_mock,
        lease_validation_service=lease_validation_service_mock,
        task_requeue_service=task_requeue_service_mock
    )


@pytest.fixture
def create_task(db_session):
    """
    Factory fixture for creating test tasks
    """
    def _create_task(
        status=TaskStatus.QUEUED,
        retry_count=0,
        max_retries=3,
        assigned_peer_id=None,
        task_type="test_task"
    ):
        task = Task(
            id=uuid4(),
            task_type=task_type,
            payload={"test": "data"},
            priority=TaskPriority.NORMAL,
            status=status,
            retry_count=retry_count,
            max_retries=max_retries,
            assigned_peer_id=assigned_peer_id,
            created_at=datetime.now(timezone.utc)
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)
        return task

    return _create_task


@pytest.fixture
def create_lease(db_session):
    """
    Factory fixture for creating test leases
    """
    def _create_lease(task_id, peer_id="test-peer", expired=False):
        if expired:
            expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        else:
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        lease = TaskLease(
            id=uuid4(),
            task_id=task_id,
            peer_id=peer_id,
            lease_token=f"token-{uuid4()}",
            expires_at=expires_at,
            is_expired=1 if expired else 0,
            lease_duration_seconds=300
        )
        db_session.add(lease)
        db_session.commit()
        db_session.refresh(lease)
        return lease

    return _create_lease


class TestRecoveryFromNodeCrash:
    """
    Test suite for node crash recovery workflow

    Scenario: Detect node crash, classify failure, revoke leases, requeue tasks
    """

    @pytest.mark.asyncio
    async def test_recover_from_node_crash(
        self,
        recovery_orchestrator,
        create_task,
        create_lease,
        db_session,
        heartbeat_subscriber_mock,
        task_requeue_service_mock
    ):
        """
        Given node crash detected, when orchestrating recovery,
        then should revoke leases and requeue tasks
        """
        # Given: Node with offline status and assigned tasks
        peer_id = "peer-crashed-123"

        # Create tasks assigned to crashed peer
        task1 = create_task(
            status=TaskStatus.RUNNING,
            assigned_peer_id=peer_id
        )
        task2 = create_task(
            status=TaskStatus.LEASED,
            assigned_peer_id=peer_id
        )

        # Create leases for these tasks
        lease1 = create_lease(task_id=task1.id, peer_id=peer_id, expired=False)
        lease2 = create_lease(task_id=task2.id, peer_id=peer_id, expired=False)

        # Mock peer state as offline
        offline_peer = PeerState(
            peer_id=peer_id,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=65),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="offline"
        )
        heartbeat_subscriber_mock.get_peer_state.return_value = offline_peer

        # When: Orchestrate recovery for crashed node
        result = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer_id,
            failure_type=FailureType.NODE_CRASH
        )

        # Then: Recovery should succeed
        assert result.status == RecoveryStatus.COMPLETED
        assert result.failure_type == FailureType.NODE_CRASH
        assert result.actions_taken is not None
        assert RecoveryAction.REVOKE_LEASES in result.actions_taken
        assert RecoveryAction.REQUEUE_TASKS in result.actions_taken

        # Verify leases were revoked
        db_session.refresh(lease1)
        db_session.refresh(lease2)
        assert lease1.is_revoked == 1
        assert lease2.is_revoked == 1

        # Verify tasks were requeued
        assert task_requeue_service_mock.requeue_task.call_count == 2

        # Verify audit log entry was created
        assert len(result.audit_log) > 0
        audit_text = " ".join(result.audit_log).lower()
        assert "revoked" in audit_text


    @pytest.mark.asyncio
    async def test_recover_from_node_crash_no_tasks(
        self,
        recovery_orchestrator,
        heartbeat_subscriber_mock
    ):
        """
        Given node crash with no assigned tasks, when orchestrating recovery,
        then should complete successfully with no actions
        """
        # Given: Crashed peer with no tasks
        peer_id = "peer-no-tasks-456"

        offline_peer = PeerState(
            peer_id=peer_id,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=70),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="offline"
        )
        heartbeat_subscriber_mock.get_peer_state.return_value = offline_peer

        # When: Orchestrate recovery
        result = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer_id,
            failure_type=FailureType.NODE_CRASH
        )

        # Then: Should complete with no actions needed
        assert result.status == RecoveryStatus.COMPLETED
        assert len(result.actions_taken) == 0
        audit_text = " ".join(result.audit_log).lower()
        assert "no tasks" in audit_text


class TestRecoveryFromPartition:
    """
    Test suite for network partition recovery workflow

    Scenario: Partition healed, reconcile state, flush buffers
    """

    @pytest.mark.asyncio
    async def test_recover_from_partition(
        self,
        recovery_orchestrator,
        create_task,
        create_lease,
        db_session,
        heartbeat_subscriber_mock
    ):
        """
        Given partition healed, when orchestrating recovery,
        then should reconcile state and flush buffer
        """
        # Given: Peer that was partitioned but now reconnected
        peer_id = "peer-partitioned-789"

        # Create tasks that may have stale state
        task1 = create_task(
            status=TaskStatus.RUNNING,
            assigned_peer_id=peer_id
        )

        lease1 = create_lease(task_id=task1.id, peer_id=peer_id, expired=False)

        # Mock peer as recently recovered
        recovered_peer = PeerState(
            peer_id=peer_id,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=2),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="online"
        )
        heartbeat_subscriber_mock.get_peer_state.return_value = recovered_peer

        # When: Orchestrate partition recovery
        result = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer_id,
            failure_type=FailureType.PARTITION_HEALED
        )

        # Then: Recovery should reconcile state
        assert result.status == RecoveryStatus.COMPLETED
        assert result.failure_type == FailureType.PARTITION_HEALED
        assert RecoveryAction.RECONCILE_STATE in result.actions_taken
        assert RecoveryAction.FLUSH_BUFFER in result.actions_taken

        # Verify audit log
        assert len(result.audit_log) > 0
        assert "partition" in result.audit_log[0].lower()


    @pytest.mark.asyncio
    async def test_recover_from_partition_with_expired_leases(
        self,
        recovery_orchestrator,
        create_task,
        create_lease,
        db_session,
        heartbeat_subscriber_mock,
        task_requeue_service_mock
    ):
        """
        Given partition healed with expired leases, when orchestrating,
        then should revoke expired leases and requeue tasks
        """
        # Given: Partitioned peer with expired leases
        peer_id = "peer-partition-expired-999"

        task1 = create_task(
            status=TaskStatus.RUNNING,
            assigned_peer_id=peer_id
        )

        # Create expired lease (lease expired during partition)
        lease1 = create_lease(task_id=task1.id, peer_id=peer_id, expired=True)

        recovered_peer = PeerState(
            peer_id=peer_id,
            last_heartbeat=datetime.now(timezone.utc),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="online"
        )
        heartbeat_subscriber_mock.get_peer_state.return_value = recovered_peer

        # When: Orchestrate partition recovery
        result = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer_id,
            failure_type=FailureType.PARTITION_HEALED
        )

        # Then: Should handle expired leases
        assert result.status == RecoveryStatus.COMPLETED
        assert RecoveryAction.REVOKE_LEASES in result.actions_taken
        assert RecoveryAction.REQUEUE_TASKS in result.actions_taken

        # Verify expired lease was revoked
        db_session.refresh(lease1)
        assert lease1.is_revoked == 1


class TestRecoveryFromLeaseExpiry:
    """
    Test suite for lease expiry recovery workflow

    Scenario: Lease expired, detect expiry, requeue task
    """

    @pytest.mark.asyncio
    async def test_recover_from_lease_expiry(
        self,
        recovery_orchestrator,
        create_task,
        create_lease,
        db_session,
        task_requeue_service_mock
    ):
        """
        Given lease expired, when orchestrating recovery,
        then should mark lease expired and requeue task
        """
        # Given: Task with lease that's expired but not marked yet
        task1 = create_task(
            status=TaskStatus.RUNNING,
            assigned_peer_id="peer-lease-expired-111"
        )

        # Create lease that's past expiration time but not marked (is_expired=0)
        lease1 = TaskLease(
            id=uuid4(),
            task_id=task1.id,
            peer_id="peer-lease-expired-111",
            lease_token=f"token-{uuid4()}",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),  # Expired
            is_expired=0,  # Not yet marked as expired
            is_revoked=0,
            lease_duration_seconds=300
        )
        db_session.add(lease1)
        db_session.commit()
        db_session.refresh(lease1)

        # When: Orchestrate lease expiry recovery
        result = await recovery_orchestrator.orchestrate_recovery(
            task_id=task1.id,
            failure_type=FailureType.LEASE_EXPIRED
        )

        # Then: Should handle lease expiry
        assert result.status == RecoveryStatus.COMPLETED
        assert result.failure_type == FailureType.LEASE_EXPIRED
        assert RecoveryAction.MARK_LEASE_EXPIRED in result.actions_taken
        assert RecoveryAction.REQUEUE_TASKS in result.actions_taken

        # Verify lease marked as expired
        db_session.refresh(lease1)
        assert lease1.is_expired == 1

        # Verify task was requeued
        task_requeue_service_mock.requeue_task.assert_called_once_with(task1.id)


class TestRecoveryProgressTracking:
    """
    Test suite for recovery progress tracking

    Scenario: Track recovery workflow progress through multiple stages
    """

    @pytest.mark.asyncio
    async def test_track_recovery_progress(
        self,
        recovery_orchestrator,
        create_task,
        create_lease,
        db_session,
        heartbeat_subscriber_mock
    ):
        """
        Given recovery in progress, when querying status,
        then should return current progress
        """
        # Given: Initiate recovery
        peer_id = "peer-progress-222"

        task1 = create_task(
            status=TaskStatus.RUNNING,
            assigned_peer_id=peer_id
        )
        lease1 = create_lease(task_id=task1.id, peer_id=peer_id, expired=False)

        offline_peer = PeerState(
            peer_id=peer_id,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=65),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="offline"
        )
        heartbeat_subscriber_mock.get_peer_state.return_value = offline_peer

        # When: Start recovery and track progress
        result = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer_id,
            failure_type=FailureType.NODE_CRASH
        )

        # Then: Should have progress tracking
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0


    @pytest.mark.asyncio
    async def test_track_multiple_recoveries(
        self,
        recovery_orchestrator,
        create_task,
        create_lease,
        db_session,
        heartbeat_subscriber_mock
    ):
        """
        Given multiple recovery operations, when tracking,
        then should maintain separate progress for each
        """
        # Given: Multiple peers needing recovery
        peer1 = "peer-multi-333"
        peer2 = "peer-multi-444"

        task1 = create_task(status=TaskStatus.RUNNING, assigned_peer_id=peer1)
        task2 = create_task(status=TaskStatus.RUNNING, assigned_peer_id=peer2)

        lease1 = create_lease(task_id=task1.id, peer_id=peer1, expired=False)
        lease2 = create_lease(task_id=task2.id, peer_id=peer2, expired=False)

        offline_peer1 = PeerState(
            peer_id=peer1,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=65),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="offline"
        )
        offline_peer2 = PeerState(
            peer_id=peer2,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=65),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="offline"
        )

        heartbeat_subscriber_mock.get_peer_state.side_effect = [
            offline_peer1,
            offline_peer2
        ]

        # When: Orchestrate recovery for both peers
        result1 = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer1,
            failure_type=FailureType.NODE_CRASH
        )
        result2 = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer2,
            failure_type=FailureType.NODE_CRASH
        )

        # Then: Each should have independent tracking
        assert result1.peer_id == peer1
        assert result2.peer_id == peer2
        assert result1.started_at != result2.started_at


class TestRecoveryVerification:
    """
    Test suite for recovery success verification

    Scenario: Verify recovery completed successfully
    """

    @pytest.mark.asyncio
    async def test_verify_recovery_success(
        self,
        recovery_orchestrator,
        create_task,
        create_lease,
        db_session,
        heartbeat_subscriber_mock,
        task_requeue_service_mock
    ):
        """
        Given recovery completed, when verifying,
        then should confirm all tasks requeued and leases revoked
        """
        # Given: Complete recovery workflow
        peer_id = "peer-verify-555"

        task1 = create_task(status=TaskStatus.RUNNING, assigned_peer_id=peer_id)
        lease1 = create_lease(task_id=task1.id, peer_id=peer_id, expired=False)

        offline_peer = PeerState(
            peer_id=peer_id,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=65),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="offline"
        )
        heartbeat_subscriber_mock.get_peer_state.return_value = offline_peer

        # When: Orchestrate and verify recovery
        result = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer_id,
            failure_type=FailureType.NODE_CRASH
        )

        # Then: Verify recovery success
        verification = await recovery_orchestrator.verify_recovery(result.recovery_id)

        assert verification.is_successful is True
        assert verification.leases_revoked == 1
        assert verification.tasks_requeued == 1
        assert len(verification.issues) == 0


    @pytest.mark.asyncio
    async def test_verify_recovery_failure(
        self,
        recovery_orchestrator,
        create_task,
        create_lease,
        db_session,
        heartbeat_subscriber_mock,
        task_requeue_service_mock
    ):
        """
        Given recovery with failures, when verifying,
        then should report issues
        """
        # Given: Recovery with requeue failure
        peer_id = "peer-verify-fail-666"

        task1 = create_task(status=TaskStatus.RUNNING, assigned_peer_id=peer_id)
        lease1 = create_lease(task_id=task1.id, peer_id=peer_id, expired=False)

        offline_peer = PeerState(
            peer_id=peer_id,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=65),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="offline"
        )
        heartbeat_subscriber_mock.get_peer_state.return_value = offline_peer

        # Mock requeue failure
        task_requeue_service_mock.requeue_task.side_effect = Exception("Requeue failed")

        # When: Orchestrate recovery (should handle failure)
        result = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer_id,
            failure_type=FailureType.NODE_CRASH
        )

        # Then: Should report failure
        assert result.status == RecoveryStatus.PARTIAL_FAILURE

        verification = await recovery_orchestrator.verify_recovery(result.recovery_id)
        assert verification.is_successful is False
        assert len(verification.issues) > 0
        assert "requeue" in verification.issues[0].lower()


class TestRecoveryAuditTrail:
    """
    Test suite for recovery audit trail logging

    Scenario: All recovery actions logged for compliance
    """

    @pytest.mark.asyncio
    async def test_recovery_audit_trail(
        self,
        recovery_orchestrator,
        create_task,
        create_lease,
        db_session,
        heartbeat_subscriber_mock
    ):
        """
        Given recovery action, when executing,
        then should log full audit trail
        """
        # Given: Recovery scenario
        peer_id = "peer-audit-777"

        task1 = create_task(status=TaskStatus.RUNNING, assigned_peer_id=peer_id)
        task2 = create_task(status=TaskStatus.LEASED, assigned_peer_id=peer_id)

        lease1 = create_lease(task_id=task1.id, peer_id=peer_id, expired=False)
        lease2 = create_lease(task_id=task2.id, peer_id=peer_id, expired=False)

        offline_peer = PeerState(
            peer_id=peer_id,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=65),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="offline"
        )
        heartbeat_subscriber_mock.get_peer_state.return_value = offline_peer

        # When: Execute recovery
        result = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer_id,
            failure_type=FailureType.NODE_CRASH
        )

        # Then: Audit trail should be complete
        assert len(result.audit_log) > 0

        # Check for key audit entries
        audit_text = " ".join(result.audit_log).lower()
        assert "recovery started" in audit_text
        assert "revoked" in audit_text
        assert "requeued" in audit_text
        assert "recovery completed" in audit_text

        # Verify audit log has timestamps
        assert result.started_at is not None
        assert result.completed_at is not None


    @pytest.mark.asyncio
    async def test_audit_log_includes_metadata(
        self,
        recovery_orchestrator,
        create_task,
        create_lease,
        db_session,
        heartbeat_subscriber_mock
    ):
        """
        Given recovery with metadata, when logging,
        then should include all relevant context
        """
        # Given: Recovery with rich metadata
        peer_id = "peer-metadata-888"

        task1 = create_task(status=TaskStatus.RUNNING, assigned_peer_id=peer_id)
        lease1 = create_lease(task_id=task1.id, peer_id=peer_id, expired=False)

        offline_peer = PeerState(
            peer_id=peer_id,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=65),
            capabilities={"models": ["llama-3"]},
            load_metrics={"cpu_percent": 80.0},
            version="1.0.0",
            status="offline"
        )
        heartbeat_subscriber_mock.get_peer_state.return_value = offline_peer

        # When: Execute recovery
        result = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer_id,
            failure_type=FailureType.NODE_CRASH
        )

        # Then: Metadata should be captured
        assert result.metadata is not None
        assert "peer_id" in result.metadata
        assert result.metadata["peer_id"] == peer_id
        assert "failure_type" in result.metadata


class TestFailureTypeClassification:
    """
    Test suite for failure type classification

    Scenario: Identify failure type from system state
    """

    @pytest.mark.asyncio
    async def test_classify_node_crash(
        self,
        recovery_orchestrator,
        heartbeat_subscriber_mock
    ):
        """
        Given peer offline for >60s, when classifying failure,
        then should identify as NODE_CRASH
        """
        # Given: Offline peer
        peer_id = "peer-classify-crash-999"

        offline_peer = PeerState(
            peer_id=peer_id,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=65),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="offline"
        )
        heartbeat_subscriber_mock.get_peer_state.return_value = offline_peer

        # When: Classify failure
        failure_type = await recovery_orchestrator.classify_failure(peer_id=peer_id)

        # Then: Should identify as crash
        assert failure_type == FailureType.NODE_CRASH


    @pytest.mark.asyncio
    async def test_classify_partition_healed(
        self,
        recovery_orchestrator,
        heartbeat_subscriber_mock
    ):
        """
        Given peer recently recovered, when classifying failure,
        then should identify as PARTITION_HEALED
        """
        # Given: Recently recovered peer
        peer_id = "peer-classify-partition-1000"

        # Peer was offline, now online (recent status change)
        recovered_peer = PeerState(
            peer_id=peer_id,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=2),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="online"
        )
        heartbeat_subscriber_mock.get_peer_state.return_value = recovered_peer

        # When: Classify failure (with context of recent offline status)
        failure_type = await recovery_orchestrator.classify_failure(
            peer_id=peer_id,
            context={"previous_status": "offline"}
        )

        # Then: Should identify as partition healed
        assert failure_type == FailureType.PARTITION_HEALED


    @pytest.mark.asyncio
    async def test_classify_lease_expiry(
        self,
        recovery_orchestrator,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given expired lease, when classifying failure,
        then should identify as LEASE_EXPIRED
        """
        # Given: Task with expired lease
        task = create_task(status=TaskStatus.RUNNING)
        lease = create_lease(task_id=task.id, expired=True)

        # When: Classify failure by task
        failure_type = await recovery_orchestrator.classify_failure(task_id=task.id)

        # Then: Should identify as lease expiry
        assert failure_type == FailureType.LEASE_EXPIRED


class TestRecoveryEdgeCases:
    """
    Test suite for edge cases and error handling
    """

    @pytest.mark.asyncio
    async def test_recover_nonexistent_peer(
        self,
        recovery_orchestrator,
        heartbeat_subscriber_mock
    ):
        """
        Given nonexistent peer, when orchestrating recovery,
        then should handle gracefully
        """
        # Given: Peer not in cache
        peer_id = "peer-nonexistent-1111"
        heartbeat_subscriber_mock.get_peer_state.return_value = None

        # When: Attempt recovery
        result = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer_id,
            failure_type=FailureType.NODE_CRASH
        )

        # Then: Should handle gracefully
        assert result.status == RecoveryStatus.COMPLETED
        audit_text = " ".join(result.audit_log).lower()
        assert "no tasks" in audit_text or "not found" in audit_text


    @pytest.mark.asyncio
    async def test_recover_with_partial_failures(
        self,
        recovery_orchestrator,
        create_task,
        create_lease,
        db_session,
        heartbeat_subscriber_mock,
        task_requeue_service_mock
    ):
        """
        Given some tasks fail to requeue, when orchestrating recovery,
        then should mark as partial failure
        """
        # Given: Multiple tasks, one fails to requeue
        peer_id = "peer-partial-1212"

        task1 = create_task(status=TaskStatus.RUNNING, assigned_peer_id=peer_id)
        task2 = create_task(status=TaskStatus.RUNNING, assigned_peer_id=peer_id)

        lease1 = create_lease(task_id=task1.id, peer_id=peer_id, expired=False)
        lease2 = create_lease(task_id=task2.id, peer_id=peer_id, expired=False)

        offline_peer = PeerState(
            peer_id=peer_id,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=65),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="offline"
        )
        heartbeat_subscriber_mock.get_peer_state.return_value = offline_peer

        # Mock partial failure: first succeeds, second fails
        task_requeue_service_mock.requeue_task.side_effect = [
            True,  # First task succeeds
            Exception("Requeue failed")  # Second task fails
        ]

        # When: Orchestrate recovery
        result = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer_id,
            failure_type=FailureType.NODE_CRASH
        )

        # Then: Should be partial failure
        assert result.status == RecoveryStatus.PARTIAL_FAILURE
        assert len(result.audit_log) > 0


    @pytest.mark.asyncio
    async def test_idempotent_recovery(
        self,
        create_task,
        create_lease,
        db_session,
        heartbeat_subscriber_mock,
        lease_validation_service_mock
    ):
        """
        Given recovery already executed, when re-executing,
        then should be idempotent
        """
        # Given: Use real TaskRequeueService for this test to ensure DB updates
        from backend.services.task_requeue_service import TaskRequeueService
        real_requeue_service = TaskRequeueService(db=db_session)

        # Create orchestrator with real requeue service
        from backend.services.recovery_orchestrator import RecoveryOrchestrator
        recovery_orchestrator = RecoveryOrchestrator(
            db=db_session,
            heartbeat_subscriber=heartbeat_subscriber_mock,
            lease_validation_service=lease_validation_service_mock,
            task_requeue_service=real_requeue_service
        )

        peer_id = "peer-idempotent-1313"

        task1 = create_task(status=TaskStatus.RUNNING, assigned_peer_id=peer_id)
        lease1 = create_lease(task_id=task1.id, peer_id=peer_id, expired=False)

        offline_peer = PeerState(
            peer_id=peer_id,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=65),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="offline"
        )
        heartbeat_subscriber_mock.get_peer_state.return_value = offline_peer

        # When: Execute recovery twice
        result1 = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer_id,
            failure_type=FailureType.NODE_CRASH
        )

        result2 = await recovery_orchestrator.orchestrate_recovery(
            peer_id=peer_id,
            failure_type=FailureType.NODE_CRASH
        )

        # Then: Both should succeed (second is idempotent)
        assert result1.status == RecoveryStatus.COMPLETED
        assert result2.status == RecoveryStatus.COMPLETED

        # First recovery should have found and requeued tasks
        audit_text1 = " ".join(result1.audit_log).lower()
        assert "requeued" in audit_text1

        # Second execution should find no tasks (already recovered and cleared)
        # The task's assigned_peer_id is cleared after first recovery
        audit_text2 = " ".join(result2.audit_log).lower()
        assert "no tasks" in audit_text2
