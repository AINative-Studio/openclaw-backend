"""
Test suite for lease expiration detection service.

Tests follow BDD-style naming (Given/When/Then) as per project standards.
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session

from backend.services.lease_expiration_service import LeaseExpirationService
from backend.models.task_models import TaskLease, Task, TaskStatus


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = MagicMock(spec=Session)
    return session


@pytest.fixture
def lease_expiration_service(mock_db_session):
    """Create a LeaseExpirationService instance with mocked dependencies."""
    service = LeaseExpirationService(
        db_session=mock_db_session,
        scan_interval=10,
        grace_period=2
    )
    return service


@pytest.fixture
def expired_lease():
    """Create an expired task lease for testing."""
    return TaskLease(
        id=1,
        task_id="task-123",
        owner_peer_id="peer-abc",
        token="expired-token-123",
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10),
        created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    )


@pytest.fixture
def recently_expired_lease():
    """Create a recently expired lease within grace period."""
    return TaskLease(
        id=2,
        task_id="task-456",
        owner_peer_id="peer-xyz",
        token="recent-token-456",
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1),
        created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=3)
    )


@pytest.fixture
def active_lease():
    """Create an active (not expired) lease."""
    return TaskLease(
        id=3,
        task_id="task-789",
        owner_peer_id="peer-123",
        token="active-token-789",
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5),
        created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=2)
    )


class TestLeaseExpirationDetection:
    """Test lease expiration detection logic."""

    @pytest.mark.asyncio
    async def test_detect_expired_lease(
        self, lease_expiration_service, mock_db_session, expired_lease
    ):
        """
        Given lease expired 10s ago, when scanning,
        then should mark as expired.
        """
        # Arrange
        mock_db_session.query.return_value.filter.return_value.all.return_value = [
            expired_lease
        ]

        # Act
        expired_leases = await lease_expiration_service.scan_expired_leases()

        # Assert
        assert len(expired_leases) == 1
        assert expired_leases[0].id == 1
        assert expired_leases[0].task_id == "task-123"
        mock_db_session.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_ignore_recently_expired(
        self, lease_expiration_service, mock_db_session, recently_expired_lease
    ):
        """
        Given lease expired 2s ago, when in grace period,
        then should not immediately requeue.
        """
        # Arrange
        # Configure service with 3s grace period
        service = LeaseExpirationService(
            db_session=mock_db_session,
            scan_interval=10,
            grace_period=3
        )
        # The query should return empty list because grace period filters it out
        mock_db_session.query.return_value.filter.return_value.all.return_value = []

        # Act
        expired_leases = await service.scan_expired_leases()

        # Assert
        # Should not find the lease because it's within grace period
        assert len(expired_leases) == 0

    @pytest.mark.asyncio
    async def test_ignore_active_leases(
        self, lease_expiration_service, mock_db_session, active_lease
    ):
        """
        Given active (non-expired) lease, when scanning,
        then should not mark as expired.
        """
        # Arrange
        mock_db_session.query.return_value.filter.return_value.all.return_value = []

        # Act
        expired_leases = await lease_expiration_service.scan_expired_leases()

        # Assert
        assert len(expired_leases) == 0

    @pytest.mark.asyncio
    async def test_mark_lease_as_expired(
        self, lease_expiration_service, mock_db_session, expired_lease
    ):
        """
        Given expired lease, when processing,
        then should delete the lease.
        """
        # Arrange
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            expired_lease
        )

        # Act
        await lease_expiration_service.mark_lease_expired(expired_lease.id)

        # Assert
        mock_db_session.delete.assert_called_once_with(expired_lease)
        mock_db_session.commit.assert_called_once()


class TestRequeueTrigger:
    """Test requeue workflow triggering."""

    @pytest.mark.asyncio
    async def test_trigger_requeue_on_expiration(
        self, lease_expiration_service, mock_db_session, expired_lease
    ):
        """
        Given expired task, when processing,
        then should requeue if retries available.
        """
        # Arrange
        task = Task(
            task_id="task-123",
            status=TaskStatus.LEASED.value,
            payload={}
        )
        mock_db_session.query.return_value.filter.return_value.first.return_value = task
        mock_requeue_service = AsyncMock()
        lease_expiration_service.requeue_service = mock_requeue_service

        # Act
        await lease_expiration_service.handle_expired_lease(expired_lease)

        # Assert
        mock_requeue_service.requeue_task.assert_called_once_with("task-123")


class TestEventEmission:
    """Test event emission for expired leases."""

    @pytest.mark.asyncio
    async def test_emit_lease_expired_event(
        self, lease_expiration_service, mock_db_session, expired_lease
    ):
        """
        Given expired lease, when processing,
        then should emit lease_expired event.
        """
        # Arrange
        mock_event_emitter = AsyncMock()
        lease_expiration_service.event_emitter = mock_event_emitter
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        # Act
        await lease_expiration_service.handle_expired_lease(expired_lease)

        # Assert
        mock_event_emitter.emit.assert_called_once()
        call_args = mock_event_emitter.emit.call_args
        assert call_args[0][0] == "lease_expired"
        assert call_args[1]["lease_id"] == expired_lease.id
        assert call_args[1]["task_id"] == expired_lease.task_id


class TestPeriodicScanning:
    """Test periodic lease scanning."""

    @pytest.mark.asyncio
    async def test_start_periodic_scanner(
        self, lease_expiration_service, mock_db_session
    ):
        """
        Given service started, when running,
        then should scan periodically every 10s.
        """
        # Arrange
        # Use a shorter interval for testing
        service = LeaseExpirationService(
            db_session=mock_db_session,
            scan_interval=0.1,  # 100ms for fast testing
            grace_period=2
        )
        scan_count = 0

        async def mock_scan():
            nonlocal scan_count
            scan_count += 1
            if scan_count >= 3:
                # Stop after 3 scans
                service.stop()
            return []

        service.scan_expired_leases = mock_scan

        # Act
        task = asyncio.create_task(service.start())
        await asyncio.sleep(0.5)  # Wait for scan cycles
        service.stop()
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            pass

        # Assert
        assert scan_count >= 2

    @pytest.mark.asyncio
    async def test_stop_scanner_gracefully(
        self, lease_expiration_service, mock_db_session
    ):
        """
        Given running scanner, when stopping,
        then should shutdown gracefully.
        """
        # Arrange
        async def mock_scan():
            await asyncio.sleep(0.1)
            return []

        lease_expiration_service.scan_expired_leases = mock_scan

        # Act
        task = asyncio.create_task(lease_expiration_service.start())
        await asyncio.sleep(0.2)
        lease_expiration_service.stop()
        await task

        # Assert
        assert lease_expiration_service._running is False

    @pytest.mark.asyncio
    async def test_handle_scan_errors_gracefully(
        self, lease_expiration_service, mock_db_session
    ):
        """
        Given scan failure, when continuing,
        then should log error and continue scanning.
        """
        # Arrange
        # Use shorter interval for testing
        service = LeaseExpirationService(
            db_session=mock_db_session,
            scan_interval=0.1,
            grace_period=2
        )
        scan_count = 0

        async def mock_scan():
            nonlocal scan_count
            scan_count += 1
            if scan_count == 1:
                raise Exception("Database error")
            if scan_count >= 3:
                service.stop()
            return []

        service.scan_expired_leases = mock_scan

        # Act
        task = asyncio.create_task(service.start())
        await asyncio.sleep(0.5)
        service.stop()
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            pass

        # Assert
        assert scan_count >= 2  # Should continue after error


class TestBatchProcessing:
    """Test batch processing of expired leases."""

    @pytest.mark.asyncio
    async def test_process_multiple_expired_leases(
        self, lease_expiration_service, mock_db_session
    ):
        """
        Given 5 expired leases, when processing,
        then should handle all in batch.
        """
        # Arrange
        expired_leases = [
            TaskLease(
                id=i,
                task_id=f"task-{i}",
                owner_peer_id=f"peer-{i}",
                token=f"token-{i}",
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
            )
            for i in range(5)
        ]
        mock_db_session.query.return_value.filter.return_value.all.return_value = (
            expired_leases
        )

        # Act
        result = await lease_expiration_service.scan_expired_leases()

        # Assert
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_batch_processing_continues_on_individual_failure(
        self, lease_expiration_service, mock_db_session
    ):
        """
        Given batch with one failing lease, when processing,
        then should continue with remaining leases.
        """
        # Arrange
        expired_leases = [
            TaskLease(
                id=i,
                task_id=f"task-{i}",
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
            )
            for i in range(3)
        ]

        processed_count = 0

        async def mock_handle(lease):
            nonlocal processed_count
            if lease.id == 1:
                raise Exception("Processing error")
            processed_count += 1

        lease_expiration_service.handle_expired_lease = mock_handle
        mock_db_session.query.return_value.filter.return_value.all.return_value = (
            expired_leases
        )

        # Act
        await lease_expiration_service.process_expired_leases(expired_leases)

        # Assert
        assert processed_count == 2  # Should process the other 2


class TestStatistics:
    """Test expiration statistics."""

    def test_get_expiration_stats(self, lease_expiration_service, mock_db_session):
        """
        Given leases in database, when getting stats,
        then should return statistics summary.
        """
        # Arrange
        mock_db_session.query.return_value.count.return_value = 10
        mock_db_session.query.return_value.filter.return_value.count.return_value = 2

        # Act
        stats = lease_expiration_service.get_expiration_stats()

        # Assert
        assert stats["active_leases"] == 10
        assert stats["upcoming_expirations"] == 2
        assert stats["scan_interval"] == 10
        assert stats["grace_period"] == 2

    def test_get_expiration_stats_handles_errors(
        self, lease_expiration_service, mock_db_session
    ):
        """
        Given database error, when getting stats,
        then should return empty dict.
        """
        # Arrange
        mock_db_session.query.side_effect = Exception("Database error")

        # Act
        stats = lease_expiration_service.get_expiration_stats()

        # Assert
        assert stats == {}


class TestDatabaseErrors:
    """Test database error handling."""

    @pytest.mark.asyncio
    async def test_scan_handles_database_errors(
        self, lease_expiration_service, mock_db_session
    ):
        """
        Given database error during scan, when scanning,
        then should return empty list and log error.
        """
        # Arrange
        mock_db_session.query.side_effect = Exception("Database connection lost")

        # Act
        result = await lease_expiration_service.scan_expired_leases()

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_mark_expired_handles_not_found(
        self, lease_expiration_service, mock_db_session
    ):
        """
        Given lease not found, when marking expired,
        then should log warning and not raise error.
        """
        # Arrange
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        # Act
        await lease_expiration_service.mark_lease_expired(999)

        # Assert - should not raise exception
        mock_db_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_mark_expired_rollback_on_error(
        self, lease_expiration_service, mock_db_session
    ):
        """
        Given database error during mark expired, when processing,
        then should rollback transaction.
        """
        # Arrange
        mock_db_session.commit.side_effect = Exception("Database error")
        mock_lease = MagicMock()
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_lease

        # Act & Assert
        with pytest.raises(Exception):
            await lease_expiration_service.mark_lease_expired(1)

        mock_db_session.rollback.assert_called_once()
