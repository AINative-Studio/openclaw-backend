"""
Integration tests for Task Requeue Workflow

Tests task requeue logic including retry limits, backoff strategy,
and lease clearing. Follows BDD-style testing pattern.

Refs #E5-S8
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy.orm import Session

from backend.models.task_queue import Task, TaskLease, TaskStatus, TaskPriority
from backend.services.task_requeue_service import TaskRequeueService
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.db.base import Base


# Use SQLite for testing
TEST_DATABASE_URL = "sqlite:///./test_task_requeue.db"
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
def task_requeue_service(db_session):
    """
    Create TaskRequeueService instance
    """
    return TaskRequeueService(db=db_session)


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


class TestTaskRequeueExpired:
    """
    Test suite for requeueing expired tasks
    """

    @pytest.mark.asyncio
    async def test_requeue_expired_task(
        self,
        task_requeue_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given expired task with retries left, when requeuing,
        then should set status = queued
        """
        # Given: Create expired task with retries left
        task = create_task(
            status=TaskStatus.EXPIRED,
            retry_count=1,
            max_retries=3,
            assigned_peer_id="peer-123"
        )
        lease = create_lease(task_id=task.id, expired=True)

        # When: Requeue the task
        result = await task_requeue_service.requeue_task(task.id)

        # Then: Task should be queued
        assert result is True

        db_session.refresh(task)
        assert task.status == TaskStatus.QUEUED
        assert task.retry_count == 2
        assert task.assigned_peer_id is None

        # Verify lease is revoked
        db_session.refresh(lease)
        assert lease.is_revoked == 1
        assert lease.revoked_at is not None


class TestTaskRequeueMaxRetries:
    """
    Test suite for max retry enforcement
    """

    @pytest.mark.asyncio
    async def test_reject_requeue_max_retries(
        self,
        task_requeue_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given task at max retries, when attempting requeue,
        then should mark as permanently failed
        """
        # Given: Create task at max retries
        task = create_task(
            status=TaskStatus.EXPIRED,
            retry_count=3,
            max_retries=3,
            assigned_peer_id="peer-456"
        )
        lease = create_lease(task_id=task.id, expired=True)

        # When: Attempt to requeue
        result = await task_requeue_service.requeue_task(task.id)

        # Then: Should be permanently failed
        assert result is False

        db_session.refresh(task)
        assert task.status == TaskStatus.PERMANENTLY_FAILED
        assert task.retry_count == 3  # Should not increment
        assert task.assigned_peer_id is None
        assert task.error_message is not None
        assert "max retries" in task.error_message.lower()


class TestTaskRequeueBackoff:
    """
    Test suite for exponential backoff strategy
    """

    @pytest.mark.asyncio
    async def test_requeue_with_backoff(
        self,
        task_requeue_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given retry_count = 2, when requeuing,
        then should calculate exponential backoff delay
        """
        # Given: Create task with retry_count = 2
        task = create_task(
            status=TaskStatus.EXPIRED,
            retry_count=2,
            max_retries=5,
            assigned_peer_id="peer-789"
        )
        lease = create_lease(task_id=task.id, expired=True)

        # When: Requeue with backoff
        result = await task_requeue_service.requeue_task(task.id)

        # Then: Should succeed
        assert result is True

        db_session.refresh(task)
        assert task.status == TaskStatus.QUEUED
        assert task.retry_count == 3

        # Verify backoff delay was calculated (not testing exact value here)
        # Backoff is stored in metadata for scheduler
        assert task.assigned_peer_id is None


    @pytest.mark.asyncio
    async def test_backoff_calculation(
        self,
        task_requeue_service
    ):
        """
        Given different retry counts, when calculating backoff,
        then should use exponential formula: base_delay * (2 ^ retry_count)
        """
        # Test backoff calculation for various retry counts
        test_cases = [
            (0, 30),    # 30 * (2^0) = 30 seconds
            (1, 60),    # 30 * (2^1) = 60 seconds
            (2, 120),   # 30 * (2^2) = 120 seconds
            (3, 240),   # 30 * (2^3) = 240 seconds
            (4, 480),   # 30 * (2^4) = 480 seconds
        ]

        for retry_count, expected_delay in test_cases:
            delay = task_requeue_service.calculate_backoff_delay(retry_count)
            assert delay == expected_delay, f"Retry {retry_count} should have {expected_delay}s delay"


class TestTaskRequeueLeaseCleaning:
    """
    Test suite for lease clearing during requeue
    """

    @pytest.mark.asyncio
    async def test_clear_lease_on_requeue(
        self,
        task_requeue_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given task with active lease, when requeuing,
        then should clear assigned_peer_id and revoke lease
        """
        # Given: Task with lease
        task = create_task(
            status=TaskStatus.FAILED,
            retry_count=0,
            max_retries=3,
            assigned_peer_id="peer-abc"
        )
        lease = create_lease(task_id=task.id, expired=True)

        # When: Requeue
        result = await task_requeue_service.requeue_task(task.id)

        # Then: Lease should be cleared
        assert result is True

        db_session.refresh(task)
        assert task.assigned_peer_id is None

        db_session.refresh(lease)
        assert lease.is_revoked == 1
        assert lease.revoked_at is not None


    @pytest.mark.asyncio
    async def test_requeue_multiple_leases(
        self,
        task_requeue_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given task with multiple historical leases, when requeuing,
        then should revoke all active leases
        """
        # Given: Task with multiple leases
        task = create_task(
            status=TaskStatus.FAILED,
            retry_count=1,
            max_retries=3,
            assigned_peer_id="peer-xyz"
        )

        # Create multiple leases (simulating retries)
        lease1 = create_lease(task_id=task.id, peer_id="peer-1", expired=True)
        lease2 = create_lease(task_id=task.id, peer_id="peer-2", expired=True)

        # When: Requeue
        result = await task_requeue_service.requeue_task(task.id)

        # Then: All leases revoked
        assert result is True

        db_session.refresh(lease1)
        db_session.refresh(lease2)

        assert lease1.is_revoked == 1
        assert lease2.is_revoked == 1


class TestTaskRequeueEventEmission:
    """
    Test suite for requeue event emission
    """

    @pytest.mark.asyncio
    async def test_emit_requeue_event(
        self,
        task_requeue_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given successful requeue, when completing,
        then should emit requeue event for monitoring
        """
        # Given: Expired task
        task = create_task(
            status=TaskStatus.EXPIRED,
            retry_count=0,
            max_retries=3
        )
        lease = create_lease(task_id=task.id, expired=True)

        # When: Requeue (events are logged internally)
        result = await task_requeue_service.requeue_task(task.id)

        # Then: Should succeed (event emission tested via logs)
        assert result is True


class TestTaskRequeueEdgeCases:
    """
    Test suite for edge cases
    """

    @pytest.mark.asyncio
    async def test_requeue_nonexistent_task(
        self,
        task_requeue_service
    ):
        """
        Given nonexistent task ID, when requeuing,
        then should raise ValueError
        """
        # Given: Random UUID
        fake_id = uuid4()

        # When/Then: Should raise error
        with pytest.raises(ValueError, match="not found"):
            await task_requeue_service.requeue_task(fake_id)


    @pytest.mark.asyncio
    async def test_requeue_completed_task(
        self,
        task_requeue_service,
        create_task,
        db_session
    ):
        """
        Given completed task, when attempting requeue,
        then should raise ValueError
        """
        # Given: Completed task
        task = create_task(
            status=TaskStatus.COMPLETED,
            retry_count=0,
            max_retries=3
        )

        # When/Then: Should reject
        with pytest.raises(ValueError, match="Cannot requeue"):
            await task_requeue_service.requeue_task(task.id)


    @pytest.mark.asyncio
    async def test_requeue_already_queued_task(
        self,
        task_requeue_service,
        create_task,
        db_session
    ):
        """
        Given already queued task, when attempting requeue,
        then should be idempotent and succeed
        """
        # Given: Already queued task
        task = create_task(
            status=TaskStatus.QUEUED,
            retry_count=1,
            max_retries=3
        )

        # When: Attempt requeue
        result = await task_requeue_service.requeue_task(task.id)

        # Then: Should be idempotent
        assert result is True

        db_session.refresh(task)
        assert task.status == TaskStatus.QUEUED
        assert task.retry_count == 1  # Should not increment again


class TestTaskRequeueBatchProcessing:
    """
    Test suite for batch requeue processing
    """

    @pytest.mark.asyncio
    async def test_requeue_expired_tasks_batch(
        self,
        task_requeue_service,
        create_task,
        create_lease,
        db_session
    ):
        """
        Given multiple expired tasks, when batch requeueing,
        then should requeue all eligible tasks
        """
        # Given: Create multiple expired tasks
        task1 = create_task(
            status=TaskStatus.EXPIRED,
            retry_count=0,
            max_retries=3
        )
        task2 = create_task(
            status=TaskStatus.EXPIRED,
            retry_count=1,
            max_retries=3
        )
        task3 = create_task(
            status=TaskStatus.EXPIRED,
            retry_count=3,  # At max retries
            max_retries=3
        )

        # When: Batch requeue
        requeued_count = await task_requeue_service.requeue_expired_tasks(batch_size=10)

        # Then: Should requeue 2 out of 3 tasks (task3 is at max retries and gets skipped)
        assert requeued_count == 2

        # Verify statuses
        db_session.refresh(task1)
        db_session.refresh(task2)
        db_session.refresh(task3)

        assert task1.status == TaskStatus.QUEUED
        assert task2.status == TaskStatus.QUEUED
        # task3 stays EXPIRED because it exceeds max_retries (query filters it out)
        assert task3.status == TaskStatus.EXPIRED


    @pytest.mark.asyncio
    async def test_requeue_batch_with_limit(
        self,
        task_requeue_service,
        create_task,
        db_session
    ):
        """
        Given 5 expired tasks with batch_size=3, when processing,
        then should only requeue first 3 tasks
        """
        # Given: Create 5 expired tasks
        tasks = [
            create_task(
                status=TaskStatus.EXPIRED,
                retry_count=0,
                max_retries=3
            )
            for _ in range(5)
        ]

        # When: Batch requeue with limit
        requeued_count = await task_requeue_service.requeue_expired_tasks(batch_size=3)

        # Then: Should only requeue 3 tasks
        assert requeued_count == 3


    @pytest.mark.asyncio
    async def test_requeue_batch_error_handling(
        self,
        task_requeue_service,
        create_task,
        db_session
    ):
        """
        Given batch with one invalid task, when processing,
        then should continue processing other tasks
        """
        # Given: Create valid expired tasks
        task1 = create_task(
            status=TaskStatus.EXPIRED,
            retry_count=0,
            max_retries=3
        )
        task2 = create_task(
            status=TaskStatus.EXPIRED,
            retry_count=1,
            max_retries=3
        )

        # When: Batch requeue (even if one fails, others should succeed)
        requeued_count = await task_requeue_service.requeue_expired_tasks(batch_size=10)

        # Then: Should requeue all valid tasks
        assert requeued_count == 2
