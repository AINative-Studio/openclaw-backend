"""
Result Buffer Service Tests

Tests for local SQLite result buffering during DBOS partition scenarios.
Implements BDD-style tests following TDD approach.

Refs #E6-S4
"""

import pytest
import asyncio
import sqlite3
import tempfile
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from typing import Dict, List, Optional


# Test fixtures
@pytest.fixture
def temp_db_path():
    """Create temporary database file for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_buffer.db"
        yield str(db_path)


@pytest.fixture
def mock_dbos_client():
    """Mock DBOS client for testing flush operations"""
    client = AsyncMock()
    client.send_result = AsyncMock(return_value={"status": "success"})
    client.is_connected = AsyncMock(return_value=True)
    return client


@pytest.fixture
def sample_task_result():
    """Sample task result for testing"""
    return {
        "task_id": "task-123",
        "agent_id": "agent-456",
        "lease_token": "lease-789",
        "result": {"status": "completed", "output": "test output"},
        "metadata": {
            "execution_time": 1.5,
            "memory_used": 1024,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    }


@pytest.fixture
def partition_scenario_results():
    """Multiple results for partition scenario testing"""
    base_time = datetime.now(timezone.utc)
    return [
        {
            "task_id": f"task-{i}",
            "agent_id": "agent-456",
            "lease_token": f"lease-{i}",
            "result": {"status": "completed", "output": f"output-{i}"},
            "metadata": {
                "execution_time": 1.0 + (i * 0.1),
                "timestamp": (base_time + timedelta(seconds=i)).isoformat()
            }
        }
        for i in range(5)
    ]


class TestResultBufferInitialization:
    """Test result buffer service initialization and setup"""

    def test_initialize_buffer_database(self, temp_db_path):
        """
        GIVEN a new result buffer service
        WHEN initializing the service
        THEN should create SQLite database with proper schema
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange & Act
        service = ResultBufferService(db_path=temp_db_path)

        # Assert
        assert os.path.exists(temp_db_path)

        # Verify schema
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()

        # Check table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='buffered_results'
        """)
        assert cursor.fetchone() is not None

        # Check schema columns
        cursor.execute("PRAGMA table_info(buffered_results)")
        columns = {row[1] for row in cursor.fetchall()}

        expected_columns = {
            'id', 'task_id', 'agent_id', 'lease_token',
            'result_data', 'metadata', 'created_at',
            'retry_count', 'last_retry_at'
        }
        assert expected_columns.issubset(columns)

        conn.close()
        service.close()

    def test_initialize_with_custom_capacity(self, temp_db_path):
        """
        GIVEN custom buffer capacity limit
        WHEN initializing service
        THEN should set capacity limit correctly
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange & Act
        service = ResultBufferService(
            db_path=temp_db_path,
            max_buffer_size=1000
        )

        # Assert
        assert service.max_buffer_size == 1000
        service.close()

    def test_initialize_with_default_settings(self, temp_db_path):
        """
        GIVEN no custom settings
        WHEN initializing service
        THEN should use default configuration
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange & Act
        service = ResultBufferService(db_path=temp_db_path)

        # Assert
        assert service.max_buffer_size == 10000  # Default capacity
        assert service.flush_interval == 30  # Default 30 seconds
        assert service.max_retry_attempts == 3
        service.close()


class TestBufferResultDuringPartition:
    """Test buffering results when DBOS is partitioned"""

    @pytest.mark.asyncio
    async def test_buffer_result_during_partition(
        self,
        temp_db_path,
        sample_task_result
    ):
        """
        GIVEN DBOS partition detected
        WHEN task completes
        THEN should store result in local buffer
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path)

        # Act
        buffer_id = await service.buffer_result(
            task_id=sample_task_result["task_id"],
            agent_id=sample_task_result["agent_id"],
            lease_token=sample_task_result["lease_token"],
            result=sample_task_result["result"],
            metadata=sample_task_result["metadata"]
        )

        # Assert
        assert buffer_id is not None
        assert isinstance(buffer_id, int)

        # Verify result is in buffer
        buffered = await service.get_buffered_result(buffer_id)
        assert buffered is not None
        assert buffered["task_id"] == sample_task_result["task_id"]
        assert buffered["agent_id"] == sample_task_result["agent_id"]
        assert buffered["lease_token"] == sample_task_result["lease_token"]
        assert buffered["retry_count"] == 0

        service.close()

    @pytest.mark.asyncio
    async def test_buffer_multiple_results(
        self,
        temp_db_path,
        partition_scenario_results
    ):
        """
        GIVEN multiple task completions during partition
        WHEN buffering results
        THEN should store all results in order
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path)
        buffer_ids = []

        # Act
        for result in partition_scenario_results:
            buffer_id = await service.buffer_result(
                task_id=result["task_id"],
                agent_id=result["agent_id"],
                lease_token=result["lease_token"],
                result=result["result"],
                metadata=result["metadata"]
            )
            buffer_ids.append(buffer_id)

        # Assert
        assert len(buffer_ids) == 5
        assert all(isinstance(bid, int) for bid in buffer_ids)

        # Verify buffer size
        buffer_size = await service.get_buffer_size()
        assert buffer_size == 5

        service.close()

    @pytest.mark.asyncio
    async def test_buffer_includes_metadata(self, temp_db_path, sample_task_result):
        """
        GIVEN task result with metadata
        WHEN buffering result
        THEN should preserve all metadata
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path)

        # Act
        buffer_id = await service.buffer_result(
            task_id=sample_task_result["task_id"],
            agent_id=sample_task_result["agent_id"],
            lease_token=sample_task_result["lease_token"],
            result=sample_task_result["result"],
            metadata=sample_task_result["metadata"]
        )

        # Assert
        buffered = await service.get_buffered_result(buffer_id)
        assert buffered["metadata"] == sample_task_result["metadata"]
        assert "execution_time" in buffered["metadata"]
        assert "timestamp" in buffered["metadata"]

        service.close()

    @pytest.mark.asyncio
    async def test_buffer_tracks_lease_token(self, temp_db_path, sample_task_result):
        """
        GIVEN task result with lease token
        WHEN buffering result
        THEN should store and track lease token
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path)

        # Act
        buffer_id = await service.buffer_result(
            task_id=sample_task_result["task_id"],
            agent_id=sample_task_result["agent_id"],
            lease_token=sample_task_result["lease_token"],
            result=sample_task_result["result"],
            metadata=sample_task_result["metadata"]
        )

        # Assert
        buffered = await service.get_buffered_result(buffer_id)
        assert buffered["lease_token"] == "lease-789"

        service.close()


class TestBufferCapacityLimit:
    """Test buffer capacity management and overflow handling"""

    @pytest.mark.asyncio
    async def test_buffer_capacity_limit(self, temp_db_path, sample_task_result):
        """
        GIVEN buffer at capacity
        WHEN adding result
        THEN should reject with buffer full error
        """
        from backend.services.result_buffer_service import (
            ResultBufferService,
            BufferFullError
        )

        # Arrange
        service = ResultBufferService(
            db_path=temp_db_path,
            max_buffer_size=3  # Small capacity for testing
        )

        # Fill buffer to capacity
        for i in range(3):
            await service.buffer_result(
                task_id=f"task-{i}",
                agent_id="agent-456",
                lease_token=f"lease-{i}",
                result={"status": "completed"},
                metadata={"index": i}
            )

        # Act & Assert
        with pytest.raises(BufferFullError) as exc_info:
            await service.buffer_result(
                task_id=sample_task_result["task_id"],
                agent_id=sample_task_result["agent_id"],
                lease_token=sample_task_result["lease_token"],
                result=sample_task_result["result"],
                metadata=sample_task_result["metadata"]
            )

        assert "Buffer capacity exceeded" in str(exc_info.value)
        assert "max=3" in str(exc_info.value)

        service.close()

    @pytest.mark.asyncio
    async def test_get_buffer_size(self, temp_db_path, partition_scenario_results):
        """
        GIVEN buffered results
        WHEN checking buffer size
        THEN should return accurate count
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path)

        # Act - Add results
        for result in partition_scenario_results[:3]:
            await service.buffer_result(
                task_id=result["task_id"],
                agent_id=result["agent_id"],
                lease_token=result["lease_token"],
                result=result["result"],
                metadata=result["metadata"]
            )

        # Assert
        buffer_size = await service.get_buffer_size()
        assert buffer_size == 3

        service.close()

    @pytest.mark.asyncio
    async def test_buffer_size_after_flush(
        self,
        temp_db_path,
        partition_scenario_results,
        mock_dbos_client
    ):
        """
        GIVEN buffered results
        WHEN flushing buffer successfully
        THEN buffer size should decrease
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path)

        # Add results
        for result in partition_scenario_results[:3]:
            await service.buffer_result(
                task_id=result["task_id"],
                agent_id=result["agent_id"],
                lease_token=result["lease_token"],
                result=result["result"],
                metadata=result["metadata"]
            )

        initial_size = await service.get_buffer_size()
        assert initial_size == 3

        # Act - Flush buffer
        flushed = await service.flush_buffer(mock_dbos_client)

        # Assert
        assert flushed == 3
        final_size = await service.get_buffer_size()
        assert final_size == 0

        service.close()


class TestFlushBufferOnReconnect:
    """Test flushing buffered results when DBOS reconnects"""

    @pytest.mark.asyncio
    async def test_flush_buffer_on_reconnect(
        self,
        temp_db_path,
        partition_scenario_results,
        mock_dbos_client
    ):
        """
        GIVEN buffered results
        WHEN DBOS reconnects
        THEN should flush all buffered results
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path)

        # Buffer results during partition
        for result in partition_scenario_results:
            await service.buffer_result(
                task_id=result["task_id"],
                agent_id=result["agent_id"],
                lease_token=result["lease_token"],
                result=result["result"],
                metadata=result["metadata"]
            )

        # Act - Simulate reconnect and flush
        flushed_count = await service.flush_buffer(mock_dbos_client)

        # Assert
        assert flushed_count == 5

        # Verify all results were sent to DBOS
        assert mock_dbos_client.send_result.call_count == 5

        # Verify buffer is empty
        buffer_size = await service.get_buffer_size()
        assert buffer_size == 0

        service.close()

    @pytest.mark.asyncio
    async def test_flush_buffer_fifo_order(
        self,
        temp_db_path,
        partition_scenario_results,
        mock_dbos_client
    ):
        """
        GIVEN buffered results
        WHEN flushing buffer
        THEN should flush in FIFO order (oldest first)
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path)
        sent_task_ids = []

        # Mock to capture order
        async def mock_send(result_data):
            sent_task_ids.append(result_data["task_id"])
            return {"status": "success"}

        mock_dbos_client.send_result = mock_send

        # Buffer results
        for result in partition_scenario_results:
            await service.buffer_result(
                task_id=result["task_id"],
                agent_id=result["agent_id"],
                lease_token=result["lease_token"],
                result=result["result"],
                metadata=result["metadata"]
            )

        # Act
        await service.flush_buffer(mock_dbos_client)

        # Assert - Results should be sent in FIFO order
        expected_order = [r["task_id"] for r in partition_scenario_results]
        assert sent_task_ids == expected_order

        service.close()

    @pytest.mark.asyncio
    async def test_flush_buffer_partial_failure(
        self,
        temp_db_path,
        partition_scenario_results
    ):
        """
        GIVEN buffered results
        WHEN some flush operations fail
        THEN should continue with remaining results and track failures
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path)

        # Mock client that fails on specific task
        mock_client = AsyncMock()
        call_count = 0

        async def mock_send(result_data):
            nonlocal call_count
            call_count += 1
            # Fail on second result
            if call_count == 2:
                raise Exception("Network error")
            return {"status": "success"}

        mock_client.send_result = mock_send

        # Buffer results
        for result in partition_scenario_results[:4]:
            await service.buffer_result(
                task_id=result["task_id"],
                agent_id=result["agent_id"],
                lease_token=result["lease_token"],
                result=result["result"],
                metadata=result["metadata"]
            )

        # Act
        flushed_count = await service.flush_buffer(mock_client)

        # Assert
        # Should have flushed 3 successfully (1 failed)
        assert flushed_count == 3

        # Failed result should still be in buffer
        buffer_size = await service.get_buffer_size()
        assert buffer_size == 1

        # Failed result should have retry count incremented
        remaining = await service.get_all_buffered_results()
        assert len(remaining) == 1
        assert remaining[0]["retry_count"] == 1

        service.close()

    @pytest.mark.asyncio
    async def test_flush_empty_buffer(self, temp_db_path, mock_dbos_client):
        """
        GIVEN empty buffer
        WHEN attempting to flush
        THEN should handle gracefully without errors
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path)

        # Act
        flushed_count = await service.flush_buffer(mock_dbos_client)

        # Assert
        assert flushed_count == 0
        assert mock_dbos_client.send_result.call_count == 0

        service.close()


class TestPeriodicFlushAttempts:
    """Test periodic flush attempts with reconnection handling"""

    @pytest.mark.asyncio
    async def test_periodic_flush_attempts(
        self,
        temp_db_path,
        partition_scenario_results,
        mock_dbos_client
    ):
        """
        GIVEN buffered results and active service
        WHEN periodic flush runs
        THEN should attempt to flush buffer periodically
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(
            db_path=temp_db_path,
            flush_interval=0.1  # Very short interval for testing
        )

        # Buffer results
        for result in partition_scenario_results[:3]:
            await service.buffer_result(
                task_id=result["task_id"],
                agent_id=result["agent_id"],
                lease_token=result["lease_token"],
                result=result["result"],
                metadata=result["metadata"]
            )

        # Act - Start periodic flush
        await service.start_periodic_flush(mock_dbos_client)

        # Wait for at least one flush cycle
        await asyncio.sleep(0.3)

        # Stop periodic flush
        await service.stop_periodic_flush()

        # Assert
        # Buffer should be empty after flush
        buffer_size = await service.get_buffer_size()
        assert buffer_size == 0

        service.close()

    @pytest.mark.asyncio
    async def test_periodic_flush_with_reconnection(
        self,
        temp_db_path,
        partition_scenario_results
    ):
        """
        GIVEN DBOS initially disconnected
        WHEN connection is restored
        THEN periodic flush should detect and flush buffer
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(
            db_path=temp_db_path,
            flush_interval=0.1
        )

        # Mock client that becomes available after delay
        mock_client = AsyncMock()
        connection_available = False

        async def mock_is_connected():
            return connection_available

        async def mock_send(result_data):
            if not connection_available:
                raise Exception("Not connected")
            return {"status": "success"}

        mock_client.is_connected = mock_is_connected
        mock_client.send_result = mock_send

        # Buffer results
        for result in partition_scenario_results[:3]:
            await service.buffer_result(
                task_id=result["task_id"],
                agent_id=result["agent_id"],
                lease_token=result["lease_token"],
                result=result["result"],
                metadata=result["metadata"]
            )

        # Act - Start periodic flush while disconnected
        await service.start_periodic_flush(mock_client)
        await asyncio.sleep(0.15)

        # Simulate reconnection
        connection_available = True
        await asyncio.sleep(0.25)

        await service.stop_periodic_flush()

        # Assert
        buffer_size = await service.get_buffer_size()
        assert buffer_size == 0

        service.close()

    @pytest.mark.asyncio
    async def test_stop_periodic_flush(self, temp_db_path, mock_dbos_client):
        """
        GIVEN running periodic flush
        WHEN stopping service
        THEN should cleanly stop background task
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(
            db_path=temp_db_path,
            flush_interval=0.1
        )

        # Act
        await service.start_periodic_flush(mock_dbos_client)
        assert service.is_flushing_active()

        await service.stop_periodic_flush()

        # Assert
        assert not service.is_flushing_active()

        service.close()


class TestFIFOBufferManagement:
    """Test FIFO (First-In-First-Out) buffer management"""

    @pytest.mark.asyncio
    async def test_fifo_ordering_on_retrieval(
        self,
        temp_db_path,
        partition_scenario_results
    ):
        """
        GIVEN multiple buffered results
        WHEN retrieving buffered results
        THEN should return in FIFO order
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path)

        # Buffer results with known order
        for result in partition_scenario_results:
            await service.buffer_result(
                task_id=result["task_id"],
                agent_id=result["agent_id"],
                lease_token=result["lease_token"],
                result=result["result"],
                metadata=result["metadata"]
            )

        # Act
        buffered = await service.get_all_buffered_results()

        # Assert
        task_ids = [r["task_id"] for r in buffered]
        expected_ids = [r["task_id"] for r in partition_scenario_results]
        assert task_ids == expected_ids

        service.close()

    @pytest.mark.asyncio
    async def test_fifo_oldest_result_first(self, temp_db_path):
        """
        GIVEN results buffered at different times
        WHEN processing buffer
        THEN oldest result should be processed first
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path)

        # Buffer results with delays
        await service.buffer_result(
            task_id="oldest",
            agent_id="agent-1",
            lease_token="lease-1",
            result={"status": "completed"},
            metadata={"timestamp": datetime.now(timezone.utc).isoformat()}
        )

        await asyncio.sleep(0.01)

        await service.buffer_result(
            task_id="middle",
            agent_id="agent-2",
            lease_token="lease-2",
            result={"status": "completed"},
            metadata={"timestamp": datetime.now(timezone.utc).isoformat()}
        )

        await asyncio.sleep(0.01)

        await service.buffer_result(
            task_id="newest",
            agent_id="agent-3",
            lease_token="lease-3",
            result={"status": "completed"},
            metadata={"timestamp": datetime.now(timezone.utc).isoformat()}
        )

        # Act
        buffered = await service.get_all_buffered_results()

        # Assert
        assert buffered[0]["task_id"] == "oldest"
        assert buffered[1]["task_id"] == "middle"
        assert buffered[2]["task_id"] == "newest"

        service.close()


class TestRetryMechanism:
    """Test retry mechanism for failed flush attempts"""

    @pytest.mark.asyncio
    async def test_retry_count_increment(self, temp_db_path, sample_task_result):
        """
        GIVEN failed flush attempt
        WHEN retrying
        THEN should increment retry count
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path)

        # Buffer result
        buffer_id = await service.buffer_result(
            task_id=sample_task_result["task_id"],
            agent_id=sample_task_result["agent_id"],
            lease_token=sample_task_result["lease_token"],
            result=sample_task_result["result"],
            metadata=sample_task_result["metadata"]
        )

        # Mock failing client
        mock_client = AsyncMock()
        mock_client.send_result = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        # Act - Attempt flush (will fail)
        await service.flush_buffer(mock_client)

        # Assert
        buffered = await service.get_buffered_result(buffer_id)
        assert buffered["retry_count"] == 1
        assert buffered["last_retry_at"] is not None

        service.close()

    @pytest.mark.asyncio
    async def test_max_retry_attempts_exceeded(self, temp_db_path, sample_task_result):
        """
        GIVEN result with max retry attempts exceeded
        WHEN flushing
        THEN should skip result and mark as failed
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(
            db_path=temp_db_path,
            max_retry_attempts=3
        )

        # Buffer result
        buffer_id = await service.buffer_result(
            task_id=sample_task_result["task_id"],
            agent_id=sample_task_result["agent_id"],
            lease_token=sample_task_result["lease_token"],
            result=sample_task_result["result"],
            metadata=sample_task_result["metadata"]
        )

        # Mock failing client
        mock_client = AsyncMock()
        mock_client.send_result = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        # Act - Attempt flush multiple times
        for _ in range(4):
            await service.flush_buffer(mock_client)

        # Assert
        buffered = await service.get_buffered_result(buffer_id)
        # After 3 retries, should be marked as failed or removed
        assert buffered is None or buffered["retry_count"] >= 3

        # Check failed results
        failed = await service.get_failed_results()
        assert len(failed) == 1
        assert failed[0]["task_id"] == sample_task_result["task_id"]

        service.close()


class TestBufferPersistence:
    """Test buffer persistence across service restarts"""

    @pytest.mark.asyncio
    async def test_buffer_persists_across_restarts(
        self,
        temp_db_path,
        partition_scenario_results
    ):
        """
        GIVEN buffered results in SQLite
        WHEN service restarts
        THEN should retain all buffered results
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange - First service instance
        service1 = ResultBufferService(db_path=temp_db_path)

        for result in partition_scenario_results[:3]:
            await service1.buffer_result(
                task_id=result["task_id"],
                agent_id=result["agent_id"],
                lease_token=result["lease_token"],
                result=result["result"],
                metadata=result["metadata"]
            )

        service1.close()

        # Act - Create new service instance
        service2 = ResultBufferService(db_path=temp_db_path)

        # Assert
        buffer_size = await service2.get_buffer_size()
        assert buffer_size == 3

        buffered = await service2.get_all_buffered_results()
        assert len(buffered) == 3

        service2.close()


class TestBufferMetrics:
    """Test buffer metrics and monitoring"""

    @pytest.mark.asyncio
    async def test_get_buffer_metrics(
        self,
        temp_db_path,
        partition_scenario_results
    ):
        """
        GIVEN buffered results
        WHEN requesting metrics
        THEN should return buffer statistics
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path, max_buffer_size=100)

        for result in partition_scenario_results[:3]:
            await service.buffer_result(
                task_id=result["task_id"],
                agent_id=result["agent_id"],
                lease_token=result["lease_token"],
                result=result["result"],
                metadata=result["metadata"]
            )

        # Act
        metrics = await service.get_buffer_metrics()

        # Assert
        assert metrics["current_size"] == 3
        assert metrics["max_capacity"] == 100
        assert metrics["utilization_percent"] == 3.0
        assert "oldest_result_age_seconds" in metrics
        assert "newest_result_age_seconds" in metrics

        service.close()

    @pytest.mark.asyncio
    async def test_buffer_utilization_calculation(self, temp_db_path):
        """
        GIVEN buffer with results
        WHEN calculating utilization
        THEN should return correct percentage
        """
        from backend.services.result_buffer_service import ResultBufferService

        # Arrange
        service = ResultBufferService(db_path=temp_db_path, max_buffer_size=10)

        # Add 5 results (50% utilization)
        for i in range(5):
            await service.buffer_result(
                task_id=f"task-{i}",
                agent_id="agent-1",
                lease_token=f"lease-{i}",
                result={"status": "completed"},
                metadata={"index": i}
            )

        # Act
        metrics = await service.get_buffer_metrics()

        # Assert
        assert metrics["utilization_percent"] == 50.0

        service.close()
