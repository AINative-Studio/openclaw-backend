"""
DBOS Partition Detection Service Tests

Tests for DBOS connection loss detection, degraded mode operation,
and partition event logging. Implements BDD-style tests following TDD approach.

Epic E6-S3: DBOS Partition Detection (3 story points)
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from typing import Dict, List, Optional
import asyncio


# Test fixtures
@pytest.fixture
def mock_dbos_healthy_response():
    """Mock healthy DBOS health check response"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "connected",
        "workflows": "operational"
    }


@pytest.fixture
def mock_dbos_unhealthy_response():
    """Mock unhealthy DBOS health check response (connection failure)"""
    return None  # Simulates connection failure/timeout


@pytest.fixture
def mock_task_in_progress():
    """Mock task that is currently in progress"""
    return {
        "task_id": "task_123",
        "status": "in_progress",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "peer_id": "peer_456"
    }


@pytest.fixture
def mock_new_task_request():
    """Mock new task request during partition"""
    return {
        "task_id": "task_new_789",
        "payload": {"operation": "test_operation"},
        "idempotency_key": "key_789"
    }


class TestDBOSPartitionDetection:
    """Test DBOS partition detection via health checks"""

    @pytest.mark.asyncio
    async def test_detect_dbos_partition(self, mock_dbos_unhealthy_response):
        """
        GIVEN DBOS connection is unreachable
        WHEN performing health check
        THEN should detect partition and enter degraded mode
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080",
            health_check_interval=5
        )

        # Mock httpx client to simulate connection failure
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            # Simulate connection timeout/failure
            import httpx
            mock_get.side_effect = httpx.ConnectError("Connection refused")

            # Act
            is_partitioned = await service.check_dbos_health()

            # Assert
            assert is_partitioned is True
            assert service.is_degraded_mode() is True
            assert service.get_partition_count() == 1

        await service.close()

    @pytest.mark.asyncio
    async def test_healthy_dbos_connection(self, mock_dbos_healthy_response):
        """
        GIVEN DBOS connection is healthy
        WHEN performing health check
        THEN should remain in normal mode
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080"
        )

        # Mock httpx client to return healthy response
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_dbos_healthy_response
            mock_get.return_value = mock_response

            # Act
            is_partitioned = await service.check_dbos_health()

            # Assert
            assert is_partitioned is False
            assert service.is_degraded_mode() is False
            assert service.get_partition_count() == 0

        await service.close()

    @pytest.mark.asyncio
    async def test_partition_recovery_detection(self, mock_dbos_healthy_response):
        """
        GIVEN system is in degraded mode due to partition
        WHEN DBOS connection is restored
        THEN should exit degraded mode and log recovery
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080"
        )

        # First, enter degraded mode
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            import httpx
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            await service.check_dbos_health()
            assert service.is_degraded_mode() is True

            # Now restore connection
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_dbos_healthy_response
            mock_get.side_effect = None
            mock_get.return_value = mock_response

            # Act
            is_partitioned = await service.check_dbos_health()

            # Assert
            assert is_partitioned is False
            assert service.is_degraded_mode() is False

            # Check recovery was logged
            events = service.get_partition_events()
            assert len(events) == 2  # One partition, one recovery
            assert events[0]['event_type'] == 'partition_detected'
            assert events[1]['event_type'] == 'partition_recovered'

        await service.close()

    @pytest.mark.asyncio
    async def test_multiple_consecutive_failures(self):
        """
        GIVEN multiple consecutive health check failures
        WHEN checking DBOS health
        THEN should track failure count and remain in degraded mode
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080"
        )

        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            import httpx
            mock_get.side_effect = httpx.ConnectError("Connection refused")

            # Act - Multiple checks
            await service.check_dbos_health()
            await service.check_dbos_health()
            await service.check_dbos_health()

            # Assert
            assert service.is_degraded_mode() is True
            assert service.get_consecutive_failure_count() >= 3

        await service.close()


class TestDegradedModeOperation:
    """Test degraded mode state management during partition"""

    @pytest.mark.asyncio
    async def test_continue_work_during_partition(self, mock_task_in_progress):
        """
        GIVEN system is in degraded mode
        WHEN existing task is running
        THEN should allow task to continue and complete
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080"
        )

        # Register task as in-progress before partition
        service.register_task_start(mock_task_in_progress['task_id'])

        # Enter degraded mode
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            import httpx
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            await service.check_dbos_health()
            assert service.is_degraded_mode() is True

            # Act - Try to complete existing task
            can_complete = service.can_complete_task(mock_task_in_progress['task_id'])

            # Assert
            assert can_complete is True

        await service.close()

    @pytest.mark.asyncio
    async def test_reject_new_work_during_partition(self, mock_new_task_request):
        """
        GIVEN system is in degraded mode
        WHEN new task arrives
        THEN should reject with partition error
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService, PartitionError

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080"
        )

        # Enter degraded mode
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            import httpx
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            await service.check_dbos_health()
            assert service.is_degraded_mode() is True

            # Act & Assert - Try to accept new task
            with pytest.raises(PartitionError) as exc_info:
                service.accept_new_task(mock_new_task_request)

            assert "degraded mode" in str(exc_info.value).lower()
            assert "partition" in str(exc_info.value).lower()

        await service.close()

    @pytest.mark.asyncio
    async def test_buffer_task_results_during_partition(self, mock_task_in_progress):
        """
        GIVEN system is in degraded mode
        WHEN task completes with results
        THEN should buffer results locally
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080"
        )

        # Enter degraded mode
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            import httpx
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            await service.check_dbos_health()
            assert service.is_degraded_mode() is True

            # Act - Buffer task result
            task_result = {
                "task_id": mock_task_in_progress['task_id'],
                "status": "completed",
                "result": {"data": "test_result"}
            }
            service.buffer_task_result(task_result)

            # Assert
            buffered_results = service.get_buffered_results()
            assert len(buffered_results) == 1
            assert buffered_results[0]['task_id'] == mock_task_in_progress['task_id']
            assert buffered_results[0]['status'] == 'completed'

        await service.close()

    @pytest.mark.asyncio
    async def test_flush_buffered_results_on_recovery(self, mock_dbos_healthy_response):
        """
        GIVEN buffered results exist from partition
        WHEN partition is recovered
        THEN should flush buffered results to DBOS
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080"
        )

        # Enter degraded mode and buffer results
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            import httpx
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            await service.check_dbos_health()

            # Buffer some results
            service.buffer_task_result({
                "task_id": "task_1",
                "status": "completed",
                "result": {"data": "result_1"}
            })
            service.buffer_task_result({
                "task_id": "task_2",
                "status": "completed",
                "result": {"data": "result_2"}
            })

            assert len(service.get_buffered_results()) == 2

            # Mock post requests for flushing
            with patch.object(service.client, 'post', new_callable=AsyncMock) as mock_post:
                mock_post_response = Mock()
                mock_post_response.status_code = 200
                mock_post_response.json.return_value = {"success": True}
                mock_post.return_value = mock_post_response

                # Restore connection
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = mock_dbos_healthy_response
                mock_get.side_effect = None
                mock_get.return_value = mock_response

                # Act - Recovery should flush results
                await service.check_dbos_health()

                # Assert
                assert service.is_degraded_mode() is False
                assert len(service.get_buffered_results()) == 0
                # Verify post was called for each buffered result
                assert mock_post.call_count == 2

        await service.close()

    @pytest.mark.asyncio
    async def test_track_in_progress_tasks(self, mock_task_in_progress):
        """
        GIVEN tasks are in progress before partition
        WHEN partition occurs
        THEN should track which tasks can continue
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080"
        )

        # Register task as in progress
        service.register_task_start(mock_task_in_progress['task_id'])

        # Enter degraded mode
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            import httpx
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            await service.check_dbos_health()

            # Act
            in_progress_tasks = service.get_in_progress_tasks()

            # Assert
            assert len(in_progress_tasks) == 1
            assert mock_task_in_progress['task_id'] in in_progress_tasks

        await service.close()


class TestPartitionEventLogging:
    """Test partition event logging and monitoring"""

    @pytest.mark.asyncio
    async def test_log_partition_detected_event(self):
        """
        GIVEN DBOS partition is detected
        WHEN partition occurs
        THEN should log partition event with timestamp and details
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080"
        )

        # Act - Trigger partition
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            import httpx
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            await service.check_dbos_health()

            # Assert
            events = service.get_partition_events()
            assert len(events) >= 1

            partition_event = events[0]
            assert partition_event['event_type'] == 'partition_detected'
            assert 'timestamp' in partition_event
            assert 'error_message' in partition_event
            assert 'consecutive_failures' in partition_event

        await service.close()

    @pytest.mark.asyncio
    async def test_log_partition_recovered_event(self, mock_dbos_healthy_response):
        """
        GIVEN partition is recovered
        WHEN DBOS connection is restored
        THEN should log recovery event with duration
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080"
        )

        # Enter and recover from partition
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            import httpx
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            await service.check_dbos_health()

            # Wait a bit for duration tracking
            await asyncio.sleep(0.1)

            # Restore connection
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_dbos_healthy_response
            mock_get.side_effect = None
            mock_get.return_value = mock_response

            await service.check_dbos_health()

            # Assert
            events = service.get_partition_events()
            assert len(events) == 2

            recovery_event = events[1]
            assert recovery_event['event_type'] == 'partition_recovered'
            assert 'timestamp' in recovery_event
            assert 'partition_duration_seconds' in recovery_event
            assert recovery_event['partition_duration_seconds'] > 0

        await service.close()

    @pytest.mark.asyncio
    async def test_get_partition_statistics(self):
        """
        GIVEN partition events have occurred
        WHEN requesting partition statistics
        THEN should return count, total duration, and MTBF
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080"
        )

        # Simulate multiple partition cycles
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            import httpx
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "healthy"}

            # First partition
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            await service.check_dbos_health()

            # Recovery
            mock_get.side_effect = None
            mock_get.return_value = mock_response
            await service.check_dbos_health()

            # Act
            stats = service.get_partition_statistics()

            # Assert
            assert 'total_partitions' in stats
            assert 'total_recoveries' in stats
            assert 'current_state' in stats
            assert stats['total_partitions'] == 1
            assert stats['total_recoveries'] == 1
            assert stats['current_state'] == 'normal'

        await service.close()

    @pytest.mark.asyncio
    async def test_partition_event_retention(self):
        """
        GIVEN partition event history
        WHEN events exceed retention limit
        THEN should keep only most recent events
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080",
            max_event_history=5
        )

        # Simulate many partition cycles
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            import httpx
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "healthy"}

            # Create 10 partition/recovery cycles
            for _ in range(10):
                # Partition
                mock_get.side_effect = httpx.ConnectError("Connection refused")
                await service.check_dbos_health()

                # Recovery
                mock_get.side_effect = None
                mock_get.return_value = mock_response
                await service.check_dbos_health()

            # Assert
            events = service.get_partition_events()
            assert len(events) <= 5  # Should respect max_event_history

        await service.close()


class TestHealthCheckScheduling:
    """Test background health check scheduling"""

    @pytest.mark.asyncio
    async def test_start_background_health_checks(self):
        """
        GIVEN service is initialized
        WHEN starting background health checks
        THEN should periodically check DBOS health
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080",
            health_check_interval=0.1  # Very short for testing
        )

        check_count = 0

        async def mock_health_check():
            nonlocal check_count
            check_count += 1
            return False

        # Act
        with patch.object(service, 'check_dbos_health', new=mock_health_check):
            await service.start_background_checks()

            # Wait for a few checks
            await asyncio.sleep(0.35)

            await service.stop_background_checks()

        # Assert
        assert check_count >= 2  # Should have run multiple times

        await service.close()

    @pytest.mark.asyncio
    async def test_stop_background_health_checks(self):
        """
        GIVEN background health checks are running
        WHEN stopping checks
        THEN should gracefully stop background task
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080",
            health_check_interval=1
        )

        # Act
        await service.start_background_checks()
        assert service.is_background_checks_running() is True

        await service.stop_background_checks()

        # Assert
        assert service.is_background_checks_running() is False

        await service.close()


class TestEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_health_check_timeout(self):
        """
        GIVEN DBOS health check times out
        WHEN checking health
        THEN should treat as partition
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080",
            health_check_timeout=1
        )

        # Mock timeout
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            import httpx
            mock_get.side_effect = httpx.TimeoutException("Request timeout")

            # Act
            is_partitioned = await service.check_dbos_health()

            # Assert
            assert is_partitioned is True
            assert service.is_degraded_mode() is True

        await service.close()

    @pytest.mark.asyncio
    async def test_invalid_health_response(self):
        """
        GIVEN DBOS returns invalid health response
        WHEN checking health
        THEN should treat as partition
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080"
        )

        # Mock invalid response
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.json.side_effect = ValueError("Invalid JSON")
            mock_get.return_value = mock_response

            # Act
            is_partitioned = await service.check_dbos_health()

            # Assert
            assert is_partitioned is True
            assert service.is_degraded_mode() is True

        await service.close()

    @pytest.mark.asyncio
    async def test_buffer_overflow_protection(self):
        """
        GIVEN buffer has max capacity
        WHEN buffering more results
        THEN should handle overflow gracefully
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080",
            max_buffer_size=10
        )

        # Enter degraded mode
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            import httpx
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            await service.check_dbos_health()

            # Act - Try to buffer beyond limit
            for i in range(15):
                service.buffer_task_result({
                    "task_id": f"task_{i}",
                    "status": "completed",
                    "result": {"data": f"result_{i}"}
                })

            # Assert
            buffered_results = service.get_buffered_results()
            assert len(buffered_results) <= 10  # Should respect max_buffer_size

        await service.close()

    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self):
        """
        GIVEN multiple concurrent health checks
        WHEN checking health simultaneously
        THEN should handle concurrency safely
        """
        from backend.services.dbos_partition_detection_service import DBOSPartitionDetectionService

        # Arrange
        service = DBOSPartitionDetectionService(
            openclaw_gateway_url="http://localhost:8080"
        )

        # Act - Run multiple concurrent checks
        with patch.object(service.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "healthy"}
            mock_get.return_value = mock_response

            results = await asyncio.gather(
                service.check_dbos_health(),
                service.check_dbos_health(),
                service.check_dbos_health()
            )

            # Assert - All should complete without errors
            assert len(results) == 3
            assert all(r is False for r in results)  # All healthy

        await service.close()
