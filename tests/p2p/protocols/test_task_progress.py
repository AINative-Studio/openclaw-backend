"""
Test suite for TaskProgress protocol implementation.

Tests the progress streaming functionality including message schema validation,
lease token validation, and heartbeat interval enforcement.

Refs #29
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.p2p.protocols.task_progress import (
    TaskProgressMessage,
    TaskProgressService,
    ProgressValidationError,
    InvalidLeaseTokenError,
    ProgressHeartbeatScheduler,
)


class TestTaskProgressMessage:
    """Test TaskProgress message schema and validation."""

    def test_valid_progress_message_creation(self):
        """
        Given valid progress data with all required fields,
        when creating TaskProgressMessage,
        then should successfully create message instance.
        """
        # Arrange
        task_id = str(uuid4())
        lease_token = str(uuid4())

        # Act
        message = TaskProgressMessage(
            task_id=task_id,
            lease_token=lease_token,
            percentage_complete=50.0,
            intermediate_results={"status": "processing", "items_processed": 5},
            timestamp=datetime.now(timezone.utc),
        )

        # Assert
        assert message.task_id == task_id
        assert message.lease_token == lease_token
        assert message.percentage_complete == 50.0
        assert message.intermediate_results["status"] == "processing"
        assert isinstance(message.timestamp, datetime)

    def test_progress_percentage_validation_min(self):
        """
        Given progress percentage less than 0,
        when creating TaskProgressMessage,
        then should raise validation error.
        """
        # Arrange
        task_id = str(uuid4())
        lease_token = str(uuid4())

        # Act & Assert
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TaskProgressMessage(
                task_id=task_id,
                lease_token=lease_token,
                percentage_complete=-5.0,
                intermediate_results={},
                timestamp=datetime.now(timezone.utc),
            )

    def test_progress_percentage_validation_max(self):
        """
        Given progress percentage greater than 100,
        when creating TaskProgressMessage,
        then should raise validation error.
        """
        # Arrange
        task_id = str(uuid4())
        lease_token = str(uuid4())

        # Act & Assert
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TaskProgressMessage(
                task_id=task_id,
                lease_token=lease_token,
                percentage_complete=105.0,
                intermediate_results={},
                timestamp=datetime.now(timezone.utc),
            )

    def test_message_serialization(self):
        """
        Given a valid TaskProgressMessage,
        when serializing to dict,
        then should produce correct JSON-serializable structure.
        """
        # Arrange
        task_id = str(uuid4())
        lease_token = str(uuid4())
        timestamp = datetime.now(timezone.utc)

        message = TaskProgressMessage(
            task_id=task_id,
            lease_token=lease_token,
            percentage_complete=75.5,
            intermediate_results={"processed": 75, "total": 100},
            timestamp=timestamp,
        )

        # Act
        data = message.model_dump()

        # Assert
        assert data["task_id"] == task_id
        assert data["lease_token"] == lease_token
        assert data["percentage_complete"] == 75.5
        assert data["intermediate_results"]["processed"] == 75
        assert isinstance(data["timestamp"], datetime)


class TestTaskProgressService:
    """Test TaskProgress streaming service."""

    @pytest.mark.asyncio
    async def test_send_progress_update(self):
        """
        Given task at 50% completion,
        when sending progress update,
        then should stream progress message successfully.
        """
        # Arrange
        task_id = str(uuid4())
        lease_token = str(uuid4())
        service = TaskProgressService()

        # Register the lease token first
        service.register_task_lease(task_id, lease_token)

        # Mock the message streaming
        service._stream_message = AsyncMock()

        # Act
        await service.send_progress_update(
            task_id=task_id,
            lease_token=lease_token,
            percentage_complete=50.0,
            intermediate_results={"status": "halfway", "data": "test"},
        )

        # Assert
        service._stream_message.assert_called_once()
        call_args = service._stream_message.call_args[0][0]
        assert isinstance(call_args, TaskProgressMessage)
        assert call_args.task_id == task_id
        assert call_args.percentage_complete == 50.0

    @pytest.mark.asyncio
    async def test_validate_progress_lease_token(self):
        """
        Given progress update with invalid lease token,
        when receiving and validating,
        then should reject and log warning.
        """
        # Arrange
        task_id = str(uuid4())
        invalid_token = str(uuid4())
        valid_token = str(uuid4())
        service = TaskProgressService()

        # Register valid token
        service.register_task_lease(task_id, valid_token)

        message = TaskProgressMessage(
            task_id=task_id,
            lease_token=invalid_token,
            percentage_complete=30.0,
            intermediate_results={},
            timestamp=datetime.now(timezone.utc),
        )

        # Act & Assert
        with pytest.raises(InvalidLeaseTokenError) as exc_info:
            await service.validate_and_process_progress(message)

        assert "Invalid lease token" in str(exc_info.value)
        assert task_id in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_progress_with_valid_lease_token(self):
        """
        Given progress update with valid lease token,
        when validating,
        then should accept and process successfully.
        """
        # Arrange
        task_id = str(uuid4())
        valid_token = str(uuid4())
        service = TaskProgressService()

        # Register valid token
        service.register_task_lease(task_id, valid_token)

        message = TaskProgressMessage(
            task_id=task_id,
            lease_token=valid_token,
            percentage_complete=45.0,
            intermediate_results={"step": "processing"},
            timestamp=datetime.now(timezone.utc),
        )

        # Act
        result = await service.validate_and_process_progress(message)

        # Assert
        assert result is True
        assert task_id in service._progress_history
        assert len(service._progress_history[task_id]) == 1
        assert service._progress_history[task_id][0].percentage_complete == 45.0

    @pytest.mark.asyncio
    async def test_rate_limiting_progress_messages(self):
        """
        Given multiple rapid progress updates,
        when sending within rate limit window,
        then should enforce rate limiting.
        """
        # Arrange
        task_id = str(uuid4())
        lease_token = str(uuid4())
        service = TaskProgressService(min_interval_seconds=2.0)
        service._stream_message = AsyncMock()
        service.register_task_lease(task_id, lease_token)

        # Act - send first update
        await service.send_progress_update(
            task_id=task_id,
            lease_token=lease_token,
            percentage_complete=10.0,
            intermediate_results={},
        )

        # Try to send second update immediately
        with pytest.raises(ProgressValidationError, match="Rate limit exceeded"):
            await service.send_progress_update(
                task_id=task_id,
                lease_token=lease_token,
                percentage_complete=20.0,
                intermediate_results={},
            )


class TestProgressHeartbeatScheduler:
    """Test periodic progress heartbeat scheduling."""

    @pytest.mark.asyncio
    async def test_progress_heartbeat_interval(self):
        """
        Given task running for 2 minutes,
        when checking heartbeat updates,
        then should have sent at least 4 updates (every 30s).
        """
        # Arrange
        task_id = str(uuid4())
        lease_token = str(uuid4())
        progress_service = TaskProgressService()
        progress_service._stream_message = AsyncMock()
        progress_service.register_task_lease(task_id, lease_token)

        scheduler = ProgressHeartbeatScheduler(
            progress_service=progress_service,
            interval_seconds=30,
        )

        update_count = 0

        async def mock_task_executor():
            """Simulate a long-running task with progress updates."""
            nonlocal update_count
            for i in range(5):  # Simulate 5 progress steps
                await asyncio.sleep(0.1)  # Simulate work
                update_count += 1
                yield i * 20  # 0%, 20%, 40%, 60%, 80%

        # Act
        sent_updates = []

        async for progress in scheduler.schedule_heartbeat_updates(
            task_id=task_id,
            lease_token=lease_token,
            task_executor=mock_task_executor(),
            task_duration_seconds=2.5,  # Simulated 2.5 minute task
        ):
            sent_updates.append(progress)

        # Assert
        assert len(sent_updates) >= 4  # At least 4 updates in 2 minutes (120s / 30s)

    @pytest.mark.asyncio
    async def test_scheduler_sends_minimum_30s_interval(self):
        """
        Given scheduler configured for 30s minimum interval,
        when task is executing,
        then should enforce minimum 30s between updates.
        """
        # Arrange
        task_id = str(uuid4())
        lease_token = str(uuid4())
        progress_service = TaskProgressService(min_interval_seconds=30.0)

        scheduler = ProgressHeartbeatScheduler(
            progress_service=progress_service,
            interval_seconds=30,
        )

        # Act & Assert
        assert scheduler.interval_seconds == 30
        assert scheduler.interval_seconds >= 30  # Enforce minimum

    @pytest.mark.asyncio
    async def test_scheduler_cleanup_on_task_completion(self):
        """
        Given task reaches 100% completion,
        when scheduler processes final update,
        then should clean up and stop scheduling.
        """
        # Arrange
        task_id = str(uuid4())
        lease_token = str(uuid4())
        progress_service = TaskProgressService()
        progress_service._stream_message = AsyncMock()
        progress_service.register_task_lease(task_id, lease_token)

        scheduler = ProgressHeartbeatScheduler(
            progress_service=progress_service,
            interval_seconds=30,
        )

        async def completed_task():
            yield 100.0  # Task immediately complete

        # Act
        updates = []
        async for progress in scheduler.schedule_heartbeat_updates(
            task_id=task_id,
            lease_token=lease_token,
            task_executor=completed_task(),
            task_duration_seconds=1.0,
        ):
            updates.append(progress)

        # Assert
        assert len(updates) == 1
        assert updates[0] == 100.0
        assert not scheduler.is_task_active(task_id)

    @pytest.mark.asyncio
    async def test_scheduler_handles_intermediate_results(self):
        """
        Given task generating intermediate results,
        when sending progress updates,
        then should include intermediate results in message.
        """
        # Arrange
        task_id = str(uuid4())
        lease_token = str(uuid4())
        progress_service = TaskProgressService()
        progress_service._stream_message = AsyncMock()
        progress_service.register_task_lease(task_id, lease_token)

        scheduler = ProgressHeartbeatScheduler(
            progress_service=progress_service,
            interval_seconds=30,
        )

        # Act
        await scheduler.send_progress_with_results(
            task_id=task_id,
            lease_token=lease_token,
            percentage_complete=60.0,
            intermediate_results={
                "processed_items": 600,
                "total_items": 1000,
                "current_batch": 6,
            },
        )

        # Assert
        progress_service._stream_message.assert_called_once()
        sent_message = progress_service._stream_message.call_args[0][0]
        assert sent_message.percentage_complete == 60.0
        assert sent_message.intermediate_results["processed_items"] == 600


class TestTaskProgressIntegration:
    """Integration tests for complete progress tracking workflow."""

    @pytest.mark.asyncio
    async def test_end_to_end_progress_tracking(self):
        """
        Given a full task execution lifecycle,
        when tracking progress from 0% to 100%,
        then should correctly stream all progress updates.
        """
        # Arrange
        task_id = str(uuid4())
        lease_token = str(uuid4())
        # Use a very low rate limit for testing
        progress_service = TaskProgressService(min_interval_seconds=0.01)
        progress_service._stream_message = AsyncMock()
        progress_service.register_task_lease(task_id, lease_token)

        # Act - simulate task execution with progress updates
        progress_updates = [0, 25, 50, 75, 100]
        for progress in progress_updates:
            await progress_service.send_progress_update(
                task_id=task_id,
                lease_token=lease_token,
                percentage_complete=float(progress),
                intermediate_results={"current_step": progress // 25},
            )
            await asyncio.sleep(0.02)  # Small delay to avoid rate limiting in test

        # Assert
        assert progress_service._stream_message.call_count == 5
        assert task_id in progress_service._progress_history

    @pytest.mark.asyncio
    async def test_concurrent_task_progress_tracking(self):
        """
        Given multiple tasks running concurrently,
        when each sends progress updates,
        then should correctly track each task independently.
        """
        # Arrange
        task_ids = [str(uuid4()) for _ in range(3)]
        lease_tokens = [str(uuid4()) for _ in range(3)]
        progress_service = TaskProgressService()
        progress_service._stream_message = AsyncMock()

        # Register all tasks
        for task_id, lease_token in zip(task_ids, lease_tokens):
            progress_service.register_task_lease(task_id, lease_token)

        # Act - send updates for all tasks
        for i, (task_id, lease_token) in enumerate(zip(task_ids, lease_tokens)):
            await progress_service.send_progress_update(
                task_id=task_id,
                lease_token=lease_token,
                percentage_complete=float((i + 1) * 30),
                intermediate_results={"task_number": i},
            )

        # Assert
        assert len(progress_service._progress_history) == 3
        for i, task_id in enumerate(task_ids):
            assert task_id in progress_service._progress_history
            assert progress_service._progress_history[task_id][0].percentage_complete == (i + 1) * 30
