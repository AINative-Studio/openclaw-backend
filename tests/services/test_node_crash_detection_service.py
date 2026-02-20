"""
Node Crash Detection Service Tests (E6-S1)

Tests for node crash detection based on heartbeat timeout monitoring.
Implements BDD-style tests following TDD approach.

Features tested:
- Detect crashed nodes when heartbeats stop for 60s
- Mark node status as offline
- Emit node_crashed event
- Trigger lease revocation
- Start recovery workflows

Refs: OpenCLAW P2P Swarm PRD Section 5.2, Backlog E6-S1
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import List, Dict

from backend.models.heartbeat import PeerState, PeerEvent


# Test fixtures
@pytest.fixture
def mock_heartbeat_subscriber():
    """Mock HeartbeatSubscriber with peer cache"""
    subscriber = Mock()
    subscriber.peer_cache = {}
    subscriber.get_peer_state = Mock(return_value=None)
    return subscriber


@pytest.fixture
def mock_peer_cache_with_crashed_node():
    """Peer cache with node that hasn't sent heartbeat for 60s"""
    now = datetime.utcnow()
    return {
        "peer1": PeerState(
            peer_id="peer1",
            last_heartbeat=now - timedelta(seconds=65),  # 65s ago - crashed
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="online"
        ),
        "peer2": PeerState(
            peer_id="peer2",
            last_heartbeat=now - timedelta(seconds=5),  # 5s ago - healthy
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="online"
        )
    }


@pytest.fixture
def mock_peer_cache_with_suspect_node():
    """Peer cache with node in suspect state (15s no heartbeat)"""
    now = datetime.utcnow()
    return {
        "peer1": PeerState(
            peer_id="peer1",
            last_heartbeat=now - timedelta(seconds=15),  # 15s ago - suspect
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="suspect"
        )
    }


@pytest.fixture
def mock_peer_cache_all_healthy():
    """Peer cache with all healthy nodes"""
    now = datetime.utcnow()
    return {
        "peer1": PeerState(
            peer_id="peer1",
            last_heartbeat=now - timedelta(seconds=3),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="online"
        ),
        "peer2": PeerState(
            peer_id="peer2",
            last_heartbeat=now - timedelta(seconds=5),
            capabilities={},
            load_metrics={},
            version="1.0.0",
            status="online"
        )
    }


@pytest.fixture
def mock_lease_revocation_service():
    """Mock lease revocation service"""
    service = AsyncMock()
    service.revoke_leases_for_peer = AsyncMock(return_value=2)  # 2 leases revoked
    return service


@pytest.fixture
def mock_recovery_workflow():
    """Mock recovery workflow trigger"""
    workflow = AsyncMock()
    workflow.start_recovery = AsyncMock(return_value="recovery-workflow-123")
    return workflow


class TestNodeCrashDetection:
    """Test node crash detection logic based on heartbeat timeout"""

    @pytest.mark.asyncio
    async def test_detect_node_crash(self, mock_peer_cache_with_crashed_node):
        """
        GIVEN a node with no heartbeat for 60 seconds
        WHEN checking for crashed nodes
        THEN should mark node as offline and return crashed node list
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        service = NodeCrashDetectionService(crash_threshold_seconds=60)

        # Act
        crashed_nodes = await service.detect_crashed_nodes(mock_peer_cache_with_crashed_node)

        # Assert
        assert len(crashed_nodes) == 1
        assert crashed_nodes[0] == "peer1"

        # Verify node status updated to offline
        assert mock_peer_cache_with_crashed_node["peer1"].status == "offline"
        # Healthy node should remain online
        assert mock_peer_cache_with_crashed_node["peer2"].status == "online"

    @pytest.mark.asyncio
    async def test_detect_no_crashes_when_all_healthy(self, mock_peer_cache_all_healthy):
        """
        GIVEN all nodes with recent heartbeats
        WHEN checking for crashed nodes
        THEN should return empty list
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        service = NodeCrashDetectionService(crash_threshold_seconds=60)

        # Act
        crashed_nodes = await service.detect_crashed_nodes(mock_peer_cache_all_healthy)

        # Assert
        assert len(crashed_nodes) == 0
        assert mock_peer_cache_all_healthy["peer1"].status == "online"
        assert mock_peer_cache_all_healthy["peer2"].status == "online"

    @pytest.mark.asyncio
    async def test_ignore_suspect_nodes(self, mock_peer_cache_with_suspect_node):
        """
        GIVEN a suspect node (15s no heartbeat)
        WHEN checking for crashes (60s threshold)
        THEN should NOT trigger crash recovery yet
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        service = NodeCrashDetectionService(crash_threshold_seconds=60)

        # Act
        crashed_nodes = await service.detect_crashed_nodes(mock_peer_cache_with_suspect_node)

        # Assert
        assert len(crashed_nodes) == 0
        # Status should remain suspect, not escalate to offline
        assert mock_peer_cache_with_suspect_node["peer1"].status == "suspect"

    @pytest.mark.asyncio
    async def test_configurable_crash_threshold(self):
        """
        GIVEN custom crash threshold
        WHEN detecting crashes
        THEN should respect custom threshold
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        service = NodeCrashDetectionService(crash_threshold_seconds=30)  # 30s threshold
        now = datetime.utcnow()
        peer_cache = {
            "peer1": PeerState(
                peer_id="peer1",
                last_heartbeat=now - timedelta(seconds=35),  # 35s - crashed at 30s threshold
                capabilities={},
                load_metrics={},
                version="1.0.0",
                status="online"
            )
        }

        # Act
        crashed_nodes = await service.detect_crashed_nodes(peer_cache)

        # Assert
        assert len(crashed_nodes) == 1
        assert crashed_nodes[0] == "peer1"


class TestCrashEventEmission:
    """Test node_crashed event emission"""

    @pytest.mark.asyncio
    async def test_emit_crash_event(self, mock_peer_cache_with_crashed_node):
        """
        GIVEN crashed node detected
        WHEN processing crash
        THEN should emit node_crashed event with metadata
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        service = NodeCrashDetectionService(crash_threshold_seconds=60)
        emitted_events = []

        def event_handler(event: PeerEvent):
            emitted_events.append(event)

        service.on_crash_event(event_handler)

        # Act
        crashed_nodes = await service.detect_crashed_nodes(mock_peer_cache_with_crashed_node)
        await service.process_crashes(crashed_nodes, mock_peer_cache_with_crashed_node)

        # Assert
        assert len(emitted_events) == 1
        event = emitted_events[0]
        assert event.event_type == "node_crashed"
        assert event.peer_id == "peer1"
        assert event.previous_status == "online"
        assert event.current_status == "offline"
        assert "elapsed_seconds" in event.metadata
        assert event.metadata["elapsed_seconds"] >= 60

    @pytest.mark.asyncio
    async def test_emit_multiple_crash_events(self):
        """
        GIVEN multiple crashed nodes
        WHEN processing crashes
        THEN should emit separate event for each crashed node
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        service = NodeCrashDetectionService(crash_threshold_seconds=60)
        now = datetime.utcnow()
        peer_cache = {
            "peer1": PeerState(
                peer_id="peer1",
                last_heartbeat=now - timedelta(seconds=65),
                capabilities={},
                load_metrics={},
                version="1.0.0",
                status="online"
            ),
            "peer2": PeerState(
                peer_id="peer2",
                last_heartbeat=now - timedelta(seconds=70),
                capabilities={},
                load_metrics={},
                version="1.0.0",
                status="online"
            )
        }

        emitted_events = []
        service.on_crash_event(lambda e: emitted_events.append(e))

        # Act
        crashed_nodes = await service.detect_crashed_nodes(peer_cache)
        await service.process_crashes(crashed_nodes, peer_cache)

        # Assert
        assert len(emitted_events) == 2
        peer_ids = {e.peer_id for e in emitted_events}
        assert peer_ids == {"peer1", "peer2"}

    @pytest.mark.asyncio
    async def test_event_handler_exception_handling(self, mock_peer_cache_with_crashed_node):
        """
        GIVEN event handler that raises exception
        WHEN emitting crash event
        THEN should handle exception gracefully and continue
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        service = NodeCrashDetectionService(crash_threshold_seconds=60)

        def failing_handler(event: PeerEvent):
            raise ValueError("Handler failed")

        successful_events = []
        def success_handler(event: PeerEvent):
            successful_events.append(event)

        service.on_crash_event(failing_handler)
        service.on_crash_event(success_handler)

        # Act
        crashed_nodes = await service.detect_crashed_nodes(mock_peer_cache_with_crashed_node)
        await service.process_crashes(crashed_nodes, mock_peer_cache_with_crashed_node)

        # Assert - second handler should still receive event
        assert len(successful_events) == 1


class TestLeaseRevocation:
    """Test lease revocation when node crashes"""

    @pytest.mark.asyncio
    async def test_trigger_lease_revocation(self, mock_peer_cache_with_crashed_node, mock_lease_revocation_service):
        """
        GIVEN crashed node with active leases
        WHEN processing crash
        THEN should trigger lease revocation for that peer
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        service = NodeCrashDetectionService(
            crash_threshold_seconds=60,
            lease_revocation_service=mock_lease_revocation_service
        )

        # Act
        crashed_nodes = await service.detect_crashed_nodes(mock_peer_cache_with_crashed_node)
        await service.process_crashes(crashed_nodes, mock_peer_cache_with_crashed_node)

        # Assert
        mock_lease_revocation_service.revoke_leases_for_peer.assert_called_once_with("peer1")

    @pytest.mark.asyncio
    async def test_revoke_leases_for_multiple_crashed_nodes(self, mock_lease_revocation_service):
        """
        GIVEN multiple crashed nodes
        WHEN processing crashes
        THEN should revoke leases for all crashed nodes
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        service = NodeCrashDetectionService(
            crash_threshold_seconds=60,
            lease_revocation_service=mock_lease_revocation_service
        )

        now = datetime.utcnow()
        peer_cache = {
            "peer1": PeerState(
                peer_id="peer1",
                last_heartbeat=now - timedelta(seconds=65),
                capabilities={},
                load_metrics={},
                version="1.0.0",
                status="online"
            ),
            "peer2": PeerState(
                peer_id="peer2",
                last_heartbeat=now - timedelta(seconds=70),
                capabilities={},
                load_metrics={},
                version="1.0.0",
                status="online"
            )
        }

        # Act
        crashed_nodes = await service.detect_crashed_nodes(peer_cache)
        await service.process_crashes(crashed_nodes, peer_cache)

        # Assert
        assert mock_lease_revocation_service.revoke_leases_for_peer.call_count == 2
        called_peers = {
            call[0][0] for call in mock_lease_revocation_service.revoke_leases_for_peer.call_args_list
        }
        assert called_peers == {"peer1", "peer2"}

    @pytest.mark.asyncio
    async def test_no_lease_revocation_when_service_not_configured(self, mock_peer_cache_with_crashed_node):
        """
        GIVEN no lease revocation service configured
        WHEN processing crashes
        THEN should handle gracefully without errors
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        service = NodeCrashDetectionService(crash_threshold_seconds=60)  # No lease service

        # Act & Assert - should not raise exception
        crashed_nodes = await service.detect_crashed_nodes(mock_peer_cache_with_crashed_node)
        await service.process_crashes(crashed_nodes, mock_peer_cache_with_crashed_node)


class TestRecoveryWorkflows:
    """Test recovery workflow triggering"""

    @pytest.mark.asyncio
    async def test_start_recovery_workflow(self, mock_peer_cache_with_crashed_node, mock_recovery_workflow):
        """
        GIVEN crashed node
        WHEN processing crash
        THEN should start recovery workflow
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        service = NodeCrashDetectionService(
            crash_threshold_seconds=60,
            recovery_workflow=mock_recovery_workflow
        )

        # Act
        crashed_nodes = await service.detect_crashed_nodes(mock_peer_cache_with_crashed_node)
        result = await service.process_crashes(crashed_nodes, mock_peer_cache_with_crashed_node)

        # Assert
        mock_recovery_workflow.start_recovery.assert_called_once()
        call_args = mock_recovery_workflow.start_recovery.call_args[0][0]
        assert call_args == "peer1"

    @pytest.mark.asyncio
    async def test_recovery_workflow_receives_metadata(self, mock_peer_cache_with_crashed_node, mock_recovery_workflow):
        """
        GIVEN crashed node
        WHEN starting recovery workflow
        THEN should pass node metadata to workflow
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        service = NodeCrashDetectionService(
            crash_threshold_seconds=60,
            recovery_workflow=mock_recovery_workflow
        )

        # Act
        crashed_nodes = await service.detect_crashed_nodes(mock_peer_cache_with_crashed_node)
        await service.process_crashes(crashed_nodes, mock_peer_cache_with_crashed_node)

        # Assert
        mock_recovery_workflow.start_recovery.assert_called_once()


class TestMonitoringLoop:
    """Test continuous crash monitoring loop"""

    @pytest.mark.asyncio
    async def test_start_crash_monitor(self):
        """
        GIVEN crash detection service with heartbeat subscriber
        WHEN starting monitor
        THEN should periodically check for crashes
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        subscriber = Mock()
        now = datetime.utcnow()
        subscriber.peer_cache = {
            "peer1": PeerState(
                peer_id="peer1",
                last_heartbeat=now - timedelta(seconds=65),
                capabilities={},
                load_metrics={},
                version="1.0.0",
                status="online"
            )
        }

        service = NodeCrashDetectionService(
            crash_threshold_seconds=60,
            heartbeat_subscriber=subscriber
        )

        crash_events = []
        service.on_crash_event(lambda e: crash_events.append(e))

        # Act - run monitor for one iteration
        task = asyncio.create_task(service.start_crash_monitor(interval_seconds=0.1))
        await asyncio.sleep(0.2)  # Let it run once
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Assert
        assert len(crash_events) >= 1

    @pytest.mark.asyncio
    async def test_monitor_handles_exceptions(self):
        """
        GIVEN monitoring loop encounters error
        WHEN processing crashes
        THEN should log error and continue monitoring
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        subscriber = Mock()
        subscriber.peer_cache = {}

        service = NodeCrashDetectionService(
            crash_threshold_seconds=60,
            heartbeat_subscriber=subscriber
        )

        # Mock detect_crashed_nodes to fail on first call, succeed on second
        call_count = 0
        original_detect = service.detect_crashed_nodes

        async def failing_detect(peer_cache):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Simulated error")
            return await original_detect(peer_cache)

        service.detect_crashed_nodes = failing_detect

        # Act - run monitor briefly
        task = asyncio.create_task(service.start_crash_monitor(interval_seconds=0.05))
        await asyncio.sleep(0.15)  # Allow multiple iterations
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Assert - should have attempted multiple times
        assert call_count >= 2


class TestCrashMetrics:
    """Test crash detection metrics and statistics"""

    @pytest.mark.asyncio
    async def test_get_crash_statistics(self, mock_peer_cache_with_crashed_node):
        """
        GIVEN crash detection service
        WHEN getting statistics
        THEN should return crash count and metrics
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        service = NodeCrashDetectionService(crash_threshold_seconds=60)

        # Act
        crashed_nodes = await service.detect_crashed_nodes(mock_peer_cache_with_crashed_node)
        await service.process_crashes(crashed_nodes, mock_peer_cache_with_crashed_node)

        stats = service.get_crash_statistics()

        # Assert
        assert stats is not None
        assert stats["total_crashes_detected"] >= 1
        assert "crash_detection_threshold_seconds" in stats
        assert stats["crash_detection_threshold_seconds"] == 60

    @pytest.mark.asyncio
    async def test_track_crash_history(self, mock_peer_cache_with_crashed_node):
        """
        GIVEN multiple crash detections
        WHEN tracking history
        THEN should maintain recent crash records
        """
        from backend.services.node_crash_detection_service import NodeCrashDetectionService

        # Arrange
        service = NodeCrashDetectionService(crash_threshold_seconds=60, max_history_size=10)

        # Act - detect crashes multiple times
        for _ in range(3):
            crashed_nodes = await service.detect_crashed_nodes(mock_peer_cache_with_crashed_node)
            await service.process_crashes(crashed_nodes, mock_peer_cache_with_crashed_node)
            # Reset status for next iteration
            mock_peer_cache_with_crashed_node["peer1"].status = "online"

        history = service.get_crash_history()

        # Assert
        assert len(history) >= 3
        for record in history:
            assert "peer_id" in record
            assert "timestamp" in record
            assert "elapsed_seconds" in record
