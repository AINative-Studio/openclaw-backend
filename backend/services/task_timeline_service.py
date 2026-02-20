"""
Task Timeline Service

In-memory timeline event service for tracking task state transitions,
lease events, failures, and recoveries across the agent swarm.

Uses a bounded deque for event storage, matching the pattern from
node_crash_detection_service (crash_history) and
dbos_partition_detection_service (partition_events).

Epic E8-S3: Task Execution Timeline
Refs: #51
"""

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Singleton instance
_timeline_service_instance: Optional["TaskTimelineService"] = None
_singleton_lock = threading.Lock()


class TimelineEventType(str, Enum):
    """Task timeline event types"""
    TASK_CREATED = "TASK_CREATED"
    TASK_QUEUED = "TASK_QUEUED"
    TASK_LEASED = "TASK_LEASED"
    TASK_STARTED = "TASK_STARTED"
    TASK_PROGRESS = "TASK_PROGRESS"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_EXPIRED = "TASK_EXPIRED"
    TASK_REQUEUED = "TASK_REQUEUED"
    LEASE_ISSUED = "LEASE_ISSUED"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    LEASE_REVOKED = "LEASE_REVOKED"
    NODE_CRASHED = "NODE_CRASHED"


class TimelineEvent(BaseModel):
    """
    Timeline Event Model

    Represents a single event in the task execution timeline.

    Attributes:
        event_type: Category of timeline event
        task_id: Task identifier (None for NODE_CRASHED)
        peer_id: Peer identifier (None for some events)
        timestamp: UTC timestamp of event occurrence
        metadata: Additional context-specific data
    """
    event_type: TimelineEventType
    task_id: Optional[str] = None
    peer_id: Optional[str] = None
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskTimelineService:
    """
    Task Timeline Service

    Records and queries task execution timeline events using an
    in-memory bounded deque. Thread-safe via threading.Lock.

    Usage:
        service = get_timeline_service()
        service.record_event(TimelineEventType.TASK_CREATED, task_id="task-1")
        events, total = service.query_events(task_id="task-1")
    """

    def __init__(self, max_events: int = 10000) -> None:
        self._events: deque = deque(maxlen=max_events)
        self._lock = threading.Lock()

    def record_event(
        self,
        event_type: TimelineEventType,
        task_id: Optional[str] = None,
        peer_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TimelineEvent:
        """
        Record a timeline event.

        Args:
            event_type: Type of event
            task_id: Task identifier (optional)
            peer_id: Peer identifier (optional)
            timestamp: Event timestamp (defaults to UTC now)
            metadata: Additional event data (defaults to empty dict)

        Returns:
            The created TimelineEvent
        """
        event = TimelineEvent(
            event_type=event_type,
            task_id=task_id,
            peer_id=peer_id,
            metadata=metadata or {},
        )
        if timestamp is not None:
            event.timestamp = timestamp

        with self._lock:
            self._events.append(event)

        return event

    def query_events(
        self,
        task_id: Optional[str] = None,
        peer_id: Optional[str] = None,
        event_type: Optional[TimelineEventType] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[TimelineEvent], int]:
        """
        Query timeline events with AND-filter logic.

        Args:
            task_id: Filter by task ID
            peer_id: Filter by peer ID
            event_type: Filter by event type
            since: Events at or after this timestamp
            until: Events at or before this timestamp
            limit: Max events to return (default 100)
            offset: Skip N events (default 0)

        Returns:
            Tuple of (paginated_events, total_count) where total_count
            is the count before limit/offset are applied.
        """
        with self._lock:
            all_events = list(self._events)

        # Filter
        filtered = all_events
        if task_id is not None:
            filtered = [e for e in filtered if e.task_id == task_id]
        if peer_id is not None:
            filtered = [e for e in filtered if e.peer_id == peer_id]
        if event_type is not None:
            filtered = [e for e in filtered if e.event_type == event_type]
        if since is not None:
            filtered = [e for e in filtered if e.timestamp >= since]
        if until is not None:
            filtered = [e for e in filtered if e.timestamp <= until]

        # Sort newest-first
        filtered.sort(key=lambda e: e.timestamp, reverse=True)

        total_count = len(filtered)

        # Paginate
        paginated = filtered[offset:offset + limit]

        return paginated, total_count

    def get_event_count(self) -> int:
        """
        Get current number of events in the timeline.

        Returns:
            Current deque size
        """
        with self._lock:
            return len(self._events)

    def clear(self) -> None:
        """Clear all events from the timeline (for test isolation)."""
        with self._lock:
            self._events.clear()


def get_timeline_service() -> TaskTimelineService:
    """
    Get the singleton TaskTimelineService instance.

    Returns:
        The shared TaskTimelineService instance
    """
    global _timeline_service_instance
    if _timeline_service_instance is None:
        with _singleton_lock:
            if _timeline_service_instance is None:
                _timeline_service_instance = TaskTimelineService()
    return _timeline_service_instance
