"""
Node Crash Detection Service (E6-S1)

Detects crashed nodes based on heartbeat timeout monitoring.
Marks nodes as offline, emits crash events, and triggers recovery workflows.

Features:
- Detect crashed nodes when heartbeats stop for 60s (configurable)
- Mark node status as offline
- Emit node_crashed events
- Trigger lease revocation for crashed nodes
- Start recovery workflows
- Track crash statistics and history

Refs: OpenCLAW P2P Swarm PRD Section 5.2, Backlog E6-S1
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from collections import deque

from backend.models.heartbeat import PeerState, PeerEvent


logger = logging.getLogger(__name__)


class NodeCrashDetectionService:
    """
    Node Crash Detection Service

    Monitors peer heartbeats and detects crashed nodes based on timeout thresholds.
    Triggers recovery actions including lease revocation and workflow initiation.

    Features:
    - Configurable crash detection threshold (default: 60s)
    - Event emission for crash notifications
    - Lease revocation integration
    - Recovery workflow triggering
    - Crash statistics and history tracking
    """

    def __init__(
        self,
        crash_threshold_seconds: int = 60,
        heartbeat_subscriber: Optional[Any] = None,
        lease_revocation_service: Optional[Any] = None,
        recovery_workflow: Optional[Any] = None,
        max_history_size: int = 100
    ):
        """
        Initialize node crash detection service.

        Args:
            crash_threshold_seconds: Seconds without heartbeat before marking as crashed
            heartbeat_subscriber: HeartbeatSubscriber instance for monitoring
            lease_revocation_service: Service to revoke leases for crashed nodes
            recovery_workflow: Workflow to start recovery for crashed nodes
            max_history_size: Maximum crash history records to retain
        """
        self.crash_threshold_seconds = crash_threshold_seconds
        self.heartbeat_subscriber = heartbeat_subscriber
        self.lease_revocation_service = lease_revocation_service
        self.recovery_workflow = recovery_workflow
        self.max_history_size = max_history_size

        self._event_handlers: List[Callable[[PeerEvent], None]] = []
        self._crash_count = 0
        self._crash_history: deque = deque(maxlen=max_history_size)
        self._lock = asyncio.Lock()

    async def detect_crashed_nodes(self, peer_cache: Dict[str, PeerState]) -> List[str]:
        """
        Detect crashed nodes based on heartbeat timeout.

        A node is considered crashed if:
        - No heartbeat received for >= crash_threshold_seconds
        - Current status is not already "offline"

        Args:
            peer_cache: Dictionary of peer_id -> PeerState

        Returns:
            List of peer_ids for crashed nodes
        """
        async with self._lock:
            crashed_nodes = []
            now = datetime.utcnow()

            for peer_id, peer_state in peer_cache.items():
                # Skip if already marked offline
                if peer_state.status == "offline":
                    continue

                # Calculate elapsed time since last heartbeat
                elapsed = (now - peer_state.last_heartbeat).total_seconds()

                # Check if node has crashed (exceeded threshold)
                if elapsed >= self.crash_threshold_seconds:
                    # Mark node as offline
                    peer_state.status = "offline"
                    crashed_nodes.append(peer_id)

                    logger.warning(
                        f"Node crash detected: {peer_id} "
                        f"(no heartbeat for {elapsed:.1f}s, threshold={self.crash_threshold_seconds}s)"
                    )

            return crashed_nodes

    async def process_crashes(
        self,
        crashed_nodes: List[str],
        peer_cache: Dict[str, PeerState]
    ) -> Dict[str, Any]:
        """
        Process crashed nodes: emit events, revoke leases, start recovery.

        Args:
            crashed_nodes: List of peer_ids for crashed nodes
            peer_cache: Dictionary of peer_id -> PeerState

        Returns:
            Dictionary with processing results
        """
        results = {
            "crashed_count": len(crashed_nodes),
            "events_emitted": 0,
            "leases_revoked": 0,
            "recovery_workflows_started": 0
        }

        for peer_id in crashed_nodes:
            peer_state = peer_cache.get(peer_id)
            if not peer_state:
                continue

            # Calculate elapsed time
            elapsed = (datetime.utcnow() - peer_state.last_heartbeat).total_seconds()

            # Emit crash event
            await self._emit_crash_event(peer_id, peer_state, elapsed)
            results["events_emitted"] += 1

            # Track crash in history
            self._record_crash(peer_id, elapsed)

            # Revoke leases if service configured
            if self.lease_revocation_service:
                try:
                    revoked_count = await self.lease_revocation_service.revoke_leases_for_peer(peer_id)
                    results["leases_revoked"] += revoked_count
                    logger.info(f"Revoked {revoked_count} leases for crashed node: {peer_id}")
                except Exception as e:
                    logger.error(f"Failed to revoke leases for {peer_id}: {e}", exc_info=True)

            # Start recovery workflow if configured
            if self.recovery_workflow:
                try:
                    workflow_id = await self.recovery_workflow.start_recovery(peer_id)
                    results["recovery_workflows_started"] += 1
                    logger.info(f"Started recovery workflow {workflow_id} for crashed node: {peer_id}")
                except Exception as e:
                    logger.error(f"Failed to start recovery workflow for {peer_id}: {e}", exc_info=True)

        return results

    async def _emit_crash_event(
        self,
        peer_id: str,
        peer_state: PeerState,
        elapsed_seconds: float
    ) -> None:
        """
        Emit node_crashed event.

        Args:
            peer_id: Crashed peer identifier
            peer_state: Current peer state
            elapsed_seconds: Seconds since last heartbeat
        """
        event = PeerEvent(
            event_type="node_crashed",
            peer_id=peer_id,
            timestamp=datetime.utcnow(),
            previous_status=peer_state.status if peer_state.status != "offline" else "online",
            current_status="offline",
            metadata={
                "elapsed_seconds": elapsed_seconds,
                "crash_threshold": self.crash_threshold_seconds,
                "last_heartbeat": peer_state.last_heartbeat.isoformat()
            }
        )

        # Emit to all registered handlers
        for handler in self._event_handlers:
            try:
                # Support both sync and async handlers
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Error in crash event handler: {e}", exc_info=True)

    def _record_crash(self, peer_id: str, elapsed_seconds: float) -> None:
        """
        Record crash in history for statistics.

        Args:
            peer_id: Crashed peer identifier
            elapsed_seconds: Seconds since last heartbeat
        """
        self._crash_count += 1
        self._crash_history.append({
            "peer_id": peer_id,
            "timestamp": datetime.utcnow(),
            "elapsed_seconds": elapsed_seconds
        })

    def on_crash_event(self, handler: Callable[[PeerEvent], None]) -> None:
        """
        Register event handler for crash events.

        Args:
            handler: Callable that receives PeerEvent
        """
        self._event_handlers.append(handler)

    async def start_crash_monitor(
        self,
        interval_seconds: int = 10
    ) -> None:
        """
        Start continuous crash monitoring loop.

        Periodically checks for crashed nodes and processes them.

        Args:
            interval_seconds: How often to check for crashes
        """
        if not self.heartbeat_subscriber:
            raise ValueError("heartbeat_subscriber required for monitoring loop")

        logger.info(
            f"Starting crash monitor (interval={interval_seconds}s, "
            f"threshold={self.crash_threshold_seconds}s)"
        )

        while True:
            try:
                await asyncio.sleep(interval_seconds)

                # Get current peer cache
                peer_cache = self.heartbeat_subscriber.peer_cache

                # Detect crashed nodes
                crashed_nodes = await self.detect_crashed_nodes(peer_cache)

                # Process crashes if any detected
                if crashed_nodes:
                    results = await self.process_crashes(crashed_nodes, peer_cache)
                    logger.info(
                        f"Processed {len(crashed_nodes)} crashed nodes: "
                        f"{results['events_emitted']} events emitted, "
                        f"{results['leases_revoked']} leases revoked, "
                        f"{results['recovery_workflows_started']} recovery workflows started"
                    )

            except asyncio.CancelledError:
                logger.info("Crash monitor stopped")
                break
            except Exception as e:
                logger.error(f"Error in crash monitor: {e}", exc_info=True)
                # Continue monitoring even after errors

    def get_crash_statistics(self) -> Dict[str, Any]:
        """
        Get crash detection statistics.

        Returns:
            Dictionary with crash statistics
        """
        return {
            "total_crashes_detected": self._crash_count,
            "crash_detection_threshold_seconds": self.crash_threshold_seconds,
            "recent_crashes": len(self._crash_history),
            "max_history_size": self.max_history_size
        }

    def get_crash_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get recent crash history.

        Args:
            limit: Maximum number of records to return (None = all)

        Returns:
            List of crash records
        """
        history = list(self._crash_history)
        if limit:
            history = history[-limit:]
        return history
