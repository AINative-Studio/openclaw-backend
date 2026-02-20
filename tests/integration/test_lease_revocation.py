"""
Integration tests for Lease Revocation Service

Tests lease revocation on node crash, batch processing, and audit logging.
Follows BDD-style testing pattern.

Refs #E6-S2
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy.orm import Session

from backend.models.task_queue import Task, TaskLease, TaskStatus, TaskPriority
from backend.services.lease_revocation_service import LeaseRevocationService
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.db.base import Base


# Use SQLite for testing
TEST_DATABASE_URL = "sqlite:///./test_lease_revocation.db"
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
def lease_revocation_service(db_session):
    """
    Create LeaseRevocationService instance
    """
    return LeaseRevocationService(db=db_session)


@pytest.fixture
def create_task(db_session):
    """
    Factory fixture for creating test tasks
    """
    def _create_task(
        status=TaskStatus.LEASED,
        assigned_peer_id=None,
        task_type="test_task"
    ):
        task = Task(
            id=uuid4(),
            task_type=task_type,
            payload={"test": "data"},
            priority=TaskPriority.NORMAL,
            status=status,
            retry_count=0,
            max_retries=3,
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
            is_revoked=0,
            lease_duration_seconds=300
        )
        db_session.add(lease)
        db_session.commit()
        db_session.refresh(lease)
        return lease

    return _create_lease


class TestRevokeLeasesOnCrash:
    """
    Test suite for revoking leases when node crashes
    """

    @pytest.mark.asyncio
    async def test_revoke_leases_on_crash(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given crashed node with 5 leases, when revoking,
        then should revoke all 5 leases
        """
        # Given: Crashed node with 5 active leases
        crashed_peer_id = "peer-crashed-123"
        tasks = []
        leases = []

        for i in range(5):
            task = create_task(
                status=TaskStatus.LEASED,
                assigned_peer_id=crashed_peer_id
            )
            tasks.append(task)
            lease = create_lease(task_id=task.id, peer_id=crashed_peer_id)
            leases.append(lease)

        # When: Revoke leases for crashed node
        result = await lease_revocation_service.revoke_leases_on_crash(
            crashed_peer_id=crashed_peer_id,
            reason="node_offline"
        )

        # Then: All 5 leases should be revoked
        assert result["revoked_count"] == 5
        assert result["success"] is True

        # Verify each lease is marked as revoked
        for lease in leases:
            db_session.refresh(lease)
            assert lease.is_revoked == 1
            assert lease.revoked_at is not None

        # Verify tasks are updated to expired status
        for task in tasks:
            db_session.refresh(task)
            assert task.status == TaskStatus.EXPIRED
            assert task.assigned_peer_id is None


    @pytest.mark.asyncio
    async def test_revoke_no_leases_for_healthy_node(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given healthy node, when attempting revocation,
        then should return zero revocations
        """
        # Given: Healthy node with active leases
        healthy_peer_id = "peer-healthy-456"
        task = create_task(
            status=TaskStatus.LEASED,
            assigned_peer_id=healthy_peer_id
        )
        lease = create_lease(task_id=task.id, peer_id=healthy_peer_id)

        # When: Revoke leases for different crashed node
        result = await lease_revocation_service.revoke_leases_on_crash(
            crashed_peer_id="peer-different-789",
            reason="node_offline"
        )

        # Then: Should not affect healthy node's leases
        assert result["revoked_count"] == 0
        assert result["success"] is True

        db_session.refresh(lease)
        assert lease.is_revoked == 0


    @pytest.mark.asyncio
    async def test_skip_already_revoked_leases(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given node with already revoked leases, when revoking,
        then should skip already revoked leases
        """
        # Given: Crashed node with mix of active and revoked leases
        crashed_peer_id = "peer-crashed-mix"

        # Active lease
        task1 = create_task(
            status=TaskStatus.LEASED,
            assigned_peer_id=crashed_peer_id
        )
        lease1 = create_lease(task_id=task1.id, peer_id=crashed_peer_id)

        # Already revoked lease
        task2 = create_task(
            status=TaskStatus.EXPIRED,
            assigned_peer_id=None
        )
        lease2 = create_lease(task_id=task2.id, peer_id=crashed_peer_id)
        lease2.is_revoked = 1
        lease2.revoked_at = datetime.now(timezone.utc)
        db_session.commit()

        # When: Revoke leases
        result = await lease_revocation_service.revoke_leases_on_crash(
            crashed_peer_id=crashed_peer_id,
            reason="node_offline"
        )

        # Then: Should only revoke the active lease
        assert result["revoked_count"] == 1
        assert result["success"] is True


class TestRequeueRevokedTasks:
    """
    Test suite for requeueing tasks after lease revocation
    """

    @pytest.mark.asyncio
    async def test_requeue_revoked_tasks(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given revoked leases, when processing,
        then should trigger requeue for all tasks
        """
        # Given: Crashed node with leases
        crashed_peer_id = "peer-crashed-requeue"
        tasks = []

        for i in range(3):
            task = create_task(
                status=TaskStatus.LEASED,
                assigned_peer_id=crashed_peer_id
            )
            tasks.append(task)
            create_lease(task_id=task.id, peer_id=crashed_peer_id)

        # When: Revoke and requeue
        result = await lease_revocation_service.revoke_leases_on_crash(
            crashed_peer_id=crashed_peer_id,
            reason="node_offline",
            requeue=True
        )

        # Then: All tasks should be requeued
        assert result["revoked_count"] == 3
        assert result["requeued_count"] == 3

        for task in tasks:
            db_session.refresh(task)
            # Tasks should be set to expired, then requeue service handles queueing
            assert task.status in [TaskStatus.EXPIRED, TaskStatus.QUEUED]
            assert task.assigned_peer_id is None


    @pytest.mark.asyncio
    async def test_requeue_respects_retry_limits(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given task at max retries, when requeueing,
        then should mark as permanently failed
        """
        # Given: Task at max retries
        crashed_peer_id = "peer-crashed-maxretry"
        task = Task(
            id=uuid4(),
            task_type="test_task",
            payload={"test": "data"},
            priority=TaskPriority.NORMAL,
            status=TaskStatus.LEASED,
            retry_count=3,
            max_retries=3,
            assigned_peer_id=crashed_peer_id,
            created_at=datetime.now(timezone.utc)
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        create_lease(task_id=task.id, peer_id=crashed_peer_id)

        # When: Revoke and attempt requeue
        result = await lease_revocation_service.revoke_leases_on_crash(
            crashed_peer_id=crashed_peer_id,
            reason="node_offline",
            requeue=True
        )

        # Then: Should revoke but not requeue (max retries reached)
        assert result["revoked_count"] == 1
        # Task at max retries won't be requeued
        db_session.refresh(task)
        assert task.status == TaskStatus.EXPIRED


class TestAuditLogRevocations:
    """
    Test suite for audit logging of lease revocations
    """

    @pytest.mark.asyncio
    async def test_audit_log_revocations(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given lease revocation, when processing,
        then should log revocation with reason
        """
        # Given: Crashed node with lease
        crashed_peer_id = "peer-crashed-audit"
        task = create_task(
            status=TaskStatus.LEASED,
            assigned_peer_id=crashed_peer_id
        )
        lease = create_lease(task_id=task.id, peer_id=crashed_peer_id)

        # When: Revoke with audit reason
        result = await lease_revocation_service.revoke_leases_on_crash(
            crashed_peer_id=crashed_peer_id,
            reason="node_offline_detected_by_heartbeat_monitor"
        )

        # Then: Should include audit metadata
        assert result["success"] is True
        assert result["revoked_count"] == 1
        assert "reason" in result
        assert result["reason"] == "node_offline_detected_by_heartbeat_monitor"
        assert "timestamp" in result


    @pytest.mark.asyncio
    async def test_audit_log_batch_revocation(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given batch revocation, when processing,
        then should log summary with counts
        """
        # Given: Crashed node with multiple leases
        crashed_peer_id = "peer-crashed-batch"
        for i in range(10):
            task = create_task(
                status=TaskStatus.LEASED,
                assigned_peer_id=crashed_peer_id
            )
            create_lease(task_id=task.id, peer_id=crashed_peer_id)

        # When: Batch revoke
        result = await lease_revocation_service.revoke_leases_on_crash(
            crashed_peer_id=crashed_peer_id,
            reason="node_crash_detected"
        )

        # Then: Should log batch summary
        assert result["success"] is True
        assert result["revoked_count"] == 10
        assert result["peer_id"] == crashed_peer_id


class TestBatchRevocation:
    """
    Test suite for batch lease revocation
    """

    @pytest.mark.asyncio
    async def test_batch_revocation_performance(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given large batch of leases, when revoking,
        then should process efficiently in batches
        """
        # Given: Crashed node with many leases
        crashed_peer_id = "peer-crashed-batch-perf"
        num_leases = 50

        for i in range(num_leases):
            task = create_task(
                status=TaskStatus.LEASED,
                assigned_peer_id=crashed_peer_id
            )
            create_lease(task_id=task.id, peer_id=crashed_peer_id)

        # When: Batch revoke
        result = await lease_revocation_service.revoke_leases_on_crash(
            crashed_peer_id=crashed_peer_id,
            reason="node_crash",
            batch_size=20
        )

        # Then: Should process all leases
        assert result["success"] is True
        assert result["revoked_count"] == num_leases


    @pytest.mark.asyncio
    async def test_revoke_multiple_crashed_nodes(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given multiple crashed nodes, when batch revoking,
        then should revoke all crashed nodes' leases
        """
        # Given: Multiple crashed nodes
        crashed_peers = ["peer-crash-1", "peer-crash-2", "peer-crash-3"]
        expected_total = 0

        for peer_id in crashed_peers:
            for i in range(5):
                task = create_task(
                    status=TaskStatus.LEASED,
                    assigned_peer_id=peer_id
                )
                create_lease(task_id=task.id, peer_id=peer_id)
                expected_total += 1

        # When: Revoke for each crashed node
        total_revoked = 0
        for peer_id in crashed_peers:
            result = await lease_revocation_service.revoke_leases_on_crash(
                crashed_peer_id=peer_id,
                reason="node_offline"
            )
            total_revoked += result["revoked_count"]

        # Then: Should revoke all leases
        assert total_revoked == expected_total


class TestEdgeCases:
    """
    Test suite for edge cases
    """

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_peer(
        self,
        lease_revocation_service
    ):
        """
        Given nonexistent peer ID, when revoking,
        then should return zero revocations gracefully
        """
        # Given: Random peer ID with no leases
        fake_peer_id = "peer-nonexistent-999"

        # When: Attempt revocation
        result = await lease_revocation_service.revoke_leases_on_crash(
            crashed_peer_id=fake_peer_id,
            reason="test"
        )

        # Then: Should succeed with zero revocations
        assert result["success"] is True
        assert result["revoked_count"] == 0


    @pytest.mark.asyncio
    async def test_revoke_with_empty_peer_id(
        self,
        lease_revocation_service
    ):
        """
        Given empty peer ID, when revoking,
        then should raise ValueError
        """
        # Given: Empty peer ID
        empty_peer_id = ""

        # When/Then: Should raise error
        with pytest.raises(ValueError, match="peer_id cannot be empty"):
            await lease_revocation_service.revoke_leases_on_crash(
                crashed_peer_id=empty_peer_id,
                reason="test"
            )


    @pytest.mark.asyncio
    async def test_concurrent_revocation_same_peer(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given concurrent revocation requests for same peer,
        then should handle idempotently
        """
        # Given: Crashed node with leases
        crashed_peer_id = "peer-crashed-concurrent"
        for i in range(5):
            task = create_task(
                status=TaskStatus.LEASED,
                assigned_peer_id=crashed_peer_id
            )
            create_lease(task_id=task.id, peer_id=crashed_peer_id)

        # When: Concurrent revocation attempts
        results = await asyncio.gather(
            lease_revocation_service.revoke_leases_on_crash(
                crashed_peer_id=crashed_peer_id,
                reason="test1"
            ),
            lease_revocation_service.revoke_leases_on_crash(
                crashed_peer_id=crashed_peer_id,
                reason="test2"
            )
        )

        # Then: Should handle gracefully (one revokes, other finds nothing)
        total_revoked = sum(r["revoked_count"] for r in results)
        assert total_revoked == 5  # All leases revoked exactly once


class TestRevokeLeaseBySingleToken:
    """
    Test suite for single lease revocation by token
    """

    @pytest.mark.asyncio
    async def test_revoke_lease_by_token(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given valid lease token, when revoking by token,
        then should revoke specific lease
        """
        # Given: Active lease
        task = create_task(status=TaskStatus.LEASED, assigned_peer_id="peer-123")
        lease = create_lease(task_id=task.id, peer_id="peer-123")

        # When: Revoke by token
        result = await lease_revocation_service.revoke_lease_by_token(
            lease_token=lease.lease_token,
            reason="manual_intervention"
        )

        # Then: Should revoke successfully
        assert result is True

        db_session.refresh(lease)
        assert lease.is_revoked == 1
        assert lease.revoked_at is not None

        db_session.refresh(task)
        assert task.status == TaskStatus.EXPIRED


    @pytest.mark.asyncio
    async def test_revoke_already_revoked_token(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given already revoked lease, when revoking by token,
        then should return False
        """
        # Given: Already revoked lease
        task = create_task(status=TaskStatus.EXPIRED)
        lease = create_lease(task_id=task.id)
        lease.is_revoked = 1
        lease.revoked_at = datetime.now(timezone.utc)
        db_session.commit()

        # When: Attempt to revoke again
        result = await lease_revocation_service.revoke_lease_by_token(
            lease_token=lease.lease_token,
            reason="test"
        )

        # Then: Should return False
        assert result is False


    @pytest.mark.asyncio
    async def test_revoke_nonexistent_token(
        self,
        lease_revocation_service
    ):
        """
        Given nonexistent token, when revoking,
        then should return False
        """
        # Given: Random token
        fake_token = f"token-{uuid4()}"

        # When: Attempt revocation
        result = await lease_revocation_service.revoke_lease_by_token(
            lease_token=fake_token,
            reason="test"
        )

        # Then: Should return False
        assert result is False


class TestGetActiveLeasesForPeer:
    """
    Test suite for querying active leases by peer
    """

    @pytest.mark.asyncio
    async def test_get_active_leases_for_peer(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given peer with active leases, when querying,
        then should return all active leases
        """
        # Given: Peer with 3 active leases
        peer_id = "peer-active-123"
        for i in range(3):
            task = create_task(status=TaskStatus.LEASED, assigned_peer_id=peer_id)
            create_lease(task_id=task.id, peer_id=peer_id)

        # When: Query active leases
        active_leases = await lease_revocation_service.get_active_leases_for_peer(
            peer_id=peer_id
        )

        # Then: Should return 3 leases
        assert len(active_leases) == 3
        assert all(lease.peer_id == peer_id for lease in active_leases)
        assert all(lease.is_revoked == 0 for lease in active_leases)


    @pytest.mark.asyncio
    async def test_get_active_leases_excludes_revoked(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given peer with mix of active and revoked leases, when querying,
        then should only return active leases
        """
        # Given: Peer with active and revoked leases
        peer_id = "peer-mixed-456"

        # Active lease
        task1 = create_task(status=TaskStatus.LEASED, assigned_peer_id=peer_id)
        create_lease(task_id=task1.id, peer_id=peer_id)

        # Revoked lease
        task2 = create_task(status=TaskStatus.EXPIRED)
        lease2 = create_lease(task_id=task2.id, peer_id=peer_id)
        lease2.is_revoked = 1
        db_session.commit()

        # When: Query active leases
        active_leases = await lease_revocation_service.get_active_leases_for_peer(
            peer_id=peer_id
        )

        # Then: Should only return 1 active lease
        assert len(active_leases) == 1
        assert active_leases[0].is_revoked == 0


    @pytest.mark.asyncio
    async def test_get_active_leases_empty_result(
        self,
        lease_revocation_service
    ):
        """
        Given peer with no leases, when querying,
        then should return empty list
        """
        # Given: Peer with no leases
        peer_id = "peer-nodata-789"

        # When: Query active leases
        active_leases = await lease_revocation_service.get_active_leases_for_peer(
            peer_id=peer_id
        )

        # Then: Should return empty list
        assert len(active_leases) == 0


class TestRevokeExpiredLeases:
    """
    Test suite for automatic expired lease revocation
    """

    @pytest.mark.asyncio
    async def test_revoke_expired_leases(
        self,
        lease_revocation_service,
        create_task,
        db_session
    ):
        """
        Given expired leases, when running revocation,
        then should revoke expired leases
        """
        # Given: Create expired leases
        peer_id = "peer-expired-123"
        expired_count = 0

        for i in range(3):
            task = create_task(status=TaskStatus.LEASED, assigned_peer_id=peer_id)

            # Create expired lease
            lease = TaskLease(
                id=uuid4(),
                task_id=task.id,
                peer_id=peer_id,
                lease_token=f"token-{uuid4()}",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
                is_expired=0,
                is_revoked=0,
                lease_duration_seconds=300
            )
            db_session.add(lease)
            expired_count += 1

        db_session.commit()

        # When: Revoke expired leases
        revoked_count = await lease_revocation_service.revoke_expired_leases()

        # Then: Should revoke all expired leases
        assert revoked_count == expired_count


    @pytest.mark.asyncio
    async def test_revoke_expired_leases_batch_limit(
        self,
        lease_revocation_service,
        create_task,
        db_session
    ):
        """
        Given 10 expired leases with batch_size=5, when processing,
        then should only revoke first 5
        """
        # Given: Create 10 expired leases
        peer_id = "peer-batch-limit"

        for i in range(10):
            task = create_task(status=TaskStatus.LEASED, assigned_peer_id=peer_id)

            lease = TaskLease(
                id=uuid4(),
                task_id=task.id,
                peer_id=peer_id,
                lease_token=f"token-{uuid4()}",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
                is_expired=0,
                is_revoked=0,
                lease_duration_seconds=300
            )
            db_session.add(lease)

        db_session.commit()

        # When: Revoke with batch limit
        revoked_count = await lease_revocation_service.revoke_expired_leases(
            batch_size=5
        )

        # Then: Should only revoke 5
        assert revoked_count == 5


    @pytest.mark.asyncio
    async def test_revoke_expired_leases_skips_active(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given mix of expired and active leases, when revoking,
        then should only revoke expired ones
        """
        # Given: Mix of expired and active
        peer_id = "peer-mixed-expiry"

        # Active lease (not expired)
        task1 = create_task(status=TaskStatus.LEASED, assigned_peer_id=peer_id)
        create_lease(task_id=task1.id, peer_id=peer_id, expired=False)

        # Expired lease
        task2 = create_task(status=TaskStatus.LEASED, assigned_peer_id=peer_id)
        lease_expired = TaskLease(
            id=uuid4(),
            task_id=task2.id,
            peer_id=peer_id,
            lease_token=f"token-{uuid4()}",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            is_expired=0,
            is_revoked=0,
            lease_duration_seconds=300
        )
        db_session.add(lease_expired)
        db_session.commit()

        # When: Revoke expired
        revoked_count = await lease_revocation_service.revoke_expired_leases()

        # Then: Should only revoke 1 (the expired one)
        assert revoked_count == 1


class TestRevocationStats:
    """
    Test suite for revocation statistics
    """

    @pytest.mark.asyncio
    async def test_get_revocation_stats(
        self,
        lease_revocation_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given mix of active and revoked leases, when getting stats,
        then should return accurate counts
        """
        # Given: Create mix of leases
        peer_id = "peer-stats"

        # 3 active leases
        for i in range(3):
            task = create_task(status=TaskStatus.LEASED, assigned_peer_id=peer_id)
            create_lease(task_id=task.id, peer_id=peer_id)

        # 2 revoked leases
        for i in range(2):
            task = create_task(status=TaskStatus.EXPIRED)
            lease = create_lease(task_id=task.id, peer_id=peer_id)
            lease.is_revoked = 1
            lease.revoked_at = datetime.now(timezone.utc)

        db_session.commit()

        # When: Get stats
        stats = await lease_revocation_service.get_revocation_stats()

        # Then: Should return accurate stats
        assert stats["total_leases"] == 5
        assert stats["active_leases"] == 3
        assert stats["revoked_leases"] == 2
        assert stats["revocation_rate"] == 40.0  # 2/5 * 100


    @pytest.mark.asyncio
    async def test_get_revocation_stats_empty_db(
        self,
        lease_revocation_service
    ):
        """
        Given empty database, when getting stats,
        then should return zeros
        """
        # Given: Empty database (fresh db_session)

        # When: Get stats
        stats = await lease_revocation_service.get_revocation_stats()

        # Then: Should return zeros
        assert stats["total_leases"] == 0
        assert stats["active_leases"] == 0
        assert stats["revoked_leases"] == 0
        assert stats["revocation_rate"] == 0.0
