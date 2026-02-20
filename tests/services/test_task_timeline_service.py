"""
Unit Tests for Task Timeline Service

Tests event recording, bounded storage, querying, clearing,
thread safety, and singleton factory behavior.

Epic E8-S3: Task Execution Timeline
Refs: #51
"""

import threading
import time
import pytest
from datetime import datetime, timezone, timedelta

from backend.services.task_timeline_service import (
    TaskTimelineService,
    TimelineEvent,
    TimelineEventType,
    get_timeline_service,
)


class TestEventRecording:
    """Test timeline event recording"""

    @pytest.fixture
    def service(self):
        """Create fresh TaskTimelineService instance"""
        return TaskTimelineService()

    def test_record_basic_event(self, service):
        """
        GIVEN a TaskTimelineService instance
        WHEN recording a TASK_CREATED event
        THEN the event should be stored in the timeline
        """
        # When
        service.record_event(
            event_type=TimelineEventType.TASK_CREATED,
            task_id="task-001",
            peer_id="peer-abc",
        )

        # Then
        events, total = service.query_events()
        assert total == 1
        assert events[0].event_type == TimelineEventType.TASK_CREATED
        assert events[0].task_id == "task-001"
        assert events[0].peer_id == "peer-abc"

    def test_record_event_default_timestamp(self, service):
        """
        GIVEN a TaskTimelineService instance
        WHEN recording an event without timestamp
        THEN the event should have a UTC timestamp near now
        """
        # When
        before = datetime.now(timezone.utc)
        event = service.record_event(
            event_type=TimelineEventType.TASK_QUEUED,
            task_id="task-002",
        )
        after = datetime.now(timezone.utc)

        # Then
        assert event.timestamp >= before
        assert event.timestamp <= after
        assert event.timestamp.tzinfo is not None

    def test_record_event_custom_timestamp(self, service):
        """
        GIVEN a TaskTimelineService instance
        WHEN recording an event with a custom timestamp
        THEN the event should use the provided timestamp
        """
        # Given
        custom_ts = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        # When
        event = service.record_event(
            event_type=TimelineEventType.TASK_LEASED,
            task_id="task-003",
            timestamp=custom_ts,
        )

        # Then
        assert event.timestamp == custom_ts

    def test_record_event_with_metadata(self, service):
        """
        GIVEN a TaskTimelineService instance
        WHEN recording an event with metadata
        THEN the event should include the metadata
        """
        # Given
        metadata = {"reason": "timeout", "duration_seconds": 120}

        # When
        event = service.record_event(
            event_type=TimelineEventType.TASK_EXPIRED,
            task_id="task-004",
            metadata=metadata,
        )

        # Then
        assert event.metadata == metadata
        assert event.metadata["reason"] == "timeout"
        assert event.metadata["duration_seconds"] == 120

    def test_record_event_optional_task_id(self, service):
        """
        GIVEN a TaskTimelineService instance
        WHEN recording a NODE_CRASHED event without task_id
        THEN the event should have task_id=None
        """
        # When
        event = service.record_event(
            event_type=TimelineEventType.NODE_CRASHED,
            peer_id="peer-xyz",
        )

        # Then
        assert event.task_id is None
        assert event.peer_id == "peer-xyz"

    def test_record_event_optional_peer_id(self, service):
        """
        GIVEN a TaskTimelineService instance
        WHEN recording a TASK_CREATED event without peer_id
        THEN the event should have peer_id=None
        """
        # When
        event = service.record_event(
            event_type=TimelineEventType.TASK_CREATED,
            task_id="task-005",
        )

        # Then
        assert event.peer_id is None
        assert event.task_id == "task-005"

    def test_record_event_returns_event(self, service):
        """
        GIVEN a TaskTimelineService instance
        WHEN recording an event
        THEN record_event should return the created TimelineEvent
        """
        # When
        event = service.record_event(
            event_type=TimelineEventType.TASK_COMPLETED,
            task_id="task-006",
            peer_id="peer-abc",
        )

        # Then
        assert isinstance(event, TimelineEvent)
        assert event.event_type == TimelineEventType.TASK_COMPLETED
        assert event.task_id == "task-006"
        assert event.peer_id == "peer-abc"
        assert event.metadata == {}


class TestBoundedStorage:
    """Test bounded deque storage limits"""

    def test_respects_max_events(self):
        """
        GIVEN a TaskTimelineService with max_events=5
        WHEN recording 7 events
        THEN only the 5 newest should be retained
        """
        # Given
        service = TaskTimelineService(max_events=5)

        # When
        for i in range(7):
            service.record_event(
                event_type=TimelineEventType.TASK_CREATED,
                task_id=f"task-{i}",
            )

        # Then
        assert service.get_event_count() == 5
        events, total = service.query_events()
        assert total == 5
        # Oldest two (task-0, task-1) should be evicted
        task_ids = [e.task_id for e in events]
        assert "task-0" not in task_ids
        assert "task-1" not in task_ids
        assert "task-6" in task_ids

    def test_oldest_events_evicted(self):
        """
        GIVEN a TaskTimelineService with max_events=3
        WHEN recording 5 events with known timestamps
        THEN the oldest 2 should be evicted
        """
        # Given
        service = TaskTimelineService(max_events=3)
        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

        # When
        for i in range(5):
            service.record_event(
                event_type=TimelineEventType.TASK_QUEUED,
                task_id=f"task-{i}",
                timestamp=base_time + timedelta(minutes=i),
            )

        # Then
        events, total = service.query_events()
        assert total == 3
        task_ids = [e.task_id for e in events]
        # Newest first: task-4, task-3, task-2
        assert task_ids == ["task-4", "task-3", "task-2"]

    def test_default_max_events(self):
        """
        GIVEN a TaskTimelineService with default settings
        WHEN checking the default max_events
        THEN it should be 10000
        """
        # When
        service = TaskTimelineService()

        # Then - internal check
        assert service._events.maxlen == 10000


class TestQueryEvents:
    """Test event querying with filters"""

    @pytest.fixture
    def service(self):
        """Create service with pre-populated events"""
        service = TaskTimelineService()
        base_time = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)

        service.record_event(
            event_type=TimelineEventType.TASK_CREATED,
            task_id="task-A",
            peer_id="peer-1",
            timestamp=base_time,
        )
        service.record_event(
            event_type=TimelineEventType.TASK_LEASED,
            task_id="task-A",
            peer_id="peer-1",
            timestamp=base_time + timedelta(seconds=10),
        )
        service.record_event(
            event_type=TimelineEventType.LEASE_ISSUED,
            task_id="task-A",
            peer_id="peer-1",
            timestamp=base_time + timedelta(seconds=11),
        )
        service.record_event(
            event_type=TimelineEventType.TASK_CREATED,
            task_id="task-B",
            peer_id="peer-2",
            timestamp=base_time + timedelta(seconds=20),
        )
        service.record_event(
            event_type=TimelineEventType.TASK_FAILED,
            task_id="task-A",
            peer_id="peer-1",
            timestamp=base_time + timedelta(seconds=30),
            metadata={"error": "OOM"},
        )
        service.record_event(
            event_type=TimelineEventType.TASK_REQUEUED,
            task_id="task-A",
            peer_id=None,
            timestamp=base_time + timedelta(seconds=40),
        )
        service.record_event(
            event_type=TimelineEventType.NODE_CRASHED,
            task_id=None,
            peer_id="peer-1",
            timestamp=base_time + timedelta(seconds=50),
        )
        return service

    def test_query_all_events(self, service):
        """
        GIVEN a service with 7 events
        WHEN querying with no filters
        THEN should return all 7 events
        """
        events, total = service.query_events()
        assert total == 7
        assert len(events) == 7

    def test_query_by_task_id(self, service):
        """
        GIVEN a service with events for task-A and task-B
        WHEN querying by task_id="task-A"
        THEN should return only task-A events
        """
        events, total = service.query_events(task_id="task-A")
        assert total == 5
        for event in events:
            assert event.task_id == "task-A"

    def test_query_by_peer_id(self, service):
        """
        GIVEN a service with events from peer-1 and peer-2
        WHEN querying by peer_id="peer-2"
        THEN should return only peer-2 events
        """
        events, total = service.query_events(peer_id="peer-2")
        assert total == 1
        assert events[0].peer_id == "peer-2"
        assert events[0].task_id == "task-B"

    def test_query_by_event_type(self, service):
        """
        GIVEN a service with mixed event types
        WHEN querying by event_type=TASK_CREATED
        THEN should return only TASK_CREATED events
        """
        events, total = service.query_events(
            event_type=TimelineEventType.TASK_CREATED
        )
        assert total == 2
        for event in events:
            assert event.event_type == TimelineEventType.TASK_CREATED

    def test_query_by_since(self, service):
        """
        GIVEN a service with events spanning 50 seconds
        WHEN querying with since=(base_time + 25s)
        THEN should return only events at or after that time
        """
        since = datetime(2026, 2, 20, 10, 0, 25, tzinfo=timezone.utc)
        events, total = service.query_events(since=since)
        assert total == 3
        for event in events:
            assert event.timestamp >= since

    def test_query_by_until(self, service):
        """
        GIVEN a service with events spanning 50 seconds
        WHEN querying with until=(base_time + 15s)
        THEN should return only events at or before that time
        """
        until = datetime(2026, 2, 20, 10, 0, 15, tzinfo=timezone.utc)
        events, total = service.query_events(until=until)
        assert total == 3
        for event in events:
            assert event.timestamp <= until

    def test_query_by_time_range(self, service):
        """
        GIVEN a service with events spanning 50 seconds
        WHEN querying with since and until defining a range
        THEN should return only events within that range
        """
        since = datetime(2026, 2, 20, 10, 0, 10, tzinfo=timezone.utc)
        until = datetime(2026, 2, 20, 10, 0, 30, tzinfo=timezone.utc)
        events, total = service.query_events(since=since, until=until)
        assert total == 4
        for event in events:
            assert event.timestamp >= since
            assert event.timestamp <= until

    def test_query_combined_filters(self, service):
        """
        GIVEN a service with mixed events
        WHEN querying by task_id AND event_type
        THEN should return events matching BOTH criteria
        """
        events, total = service.query_events(
            task_id="task-A",
            event_type=TimelineEventType.TASK_FAILED,
        )
        assert total == 1
        assert events[0].task_id == "task-A"
        assert events[0].event_type == TimelineEventType.TASK_FAILED

    def test_query_no_matches(self, service):
        """
        GIVEN a service with events
        WHEN querying with filters that match nothing
        THEN should return empty list with total=0
        """
        events, total = service.query_events(task_id="task-nonexistent")
        assert total == 0
        assert events == []

    def test_query_newest_first_sort(self, service):
        """
        GIVEN a service with events at different timestamps
        WHEN querying all events
        THEN events should be sorted newest-first (descending)
        """
        events, total = service.query_events()
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_query_with_limit(self, service):
        """
        GIVEN a service with 7 events
        WHEN querying with limit=3
        THEN should return 3 events but total_count should be 7
        """
        events, total = service.query_events(limit=3)
        assert len(events) == 3
        assert total == 7

    def test_query_with_offset(self, service):
        """
        GIVEN a service with 7 events
        WHEN querying with offset=5
        THEN should return the last 2 events
        """
        events, total = service.query_events(offset=5)
        assert len(events) == 2
        assert total == 7

    def test_query_offset_beyond_total(self, service):
        """
        GIVEN a service with 7 events
        WHEN querying with offset=100
        THEN should return empty list but total_count=7
        """
        events, total = service.query_events(offset=100)
        assert len(events) == 0
        assert total == 7


class TestGetEventCount:
    """Test event count retrieval"""

    def test_empty_service(self):
        """
        GIVEN a new TaskTimelineService
        WHEN getting the event count
        THEN should return 0
        """
        service = TaskTimelineService()
        assert service.get_event_count() == 0

    def test_after_recording(self):
        """
        GIVEN a TaskTimelineService with 3 events recorded
        WHEN getting the event count
        THEN should return 3
        """
        service = TaskTimelineService()
        for i in range(3):
            service.record_event(
                event_type=TimelineEventType.TASK_STARTED,
                task_id=f"task-{i}",
            )
        assert service.get_event_count() == 3


class TestClear:
    """Test clearing all events"""

    def test_clear_removes_all(self):
        """
        GIVEN a TaskTimelineService with recorded events
        WHEN calling clear()
        THEN all events should be removed
        """
        service = TaskTimelineService()
        for i in range(5):
            service.record_event(
                event_type=TimelineEventType.TASK_CREATED,
                task_id=f"task-{i}",
            )
        assert service.get_event_count() == 5

        service.clear()

        assert service.get_event_count() == 0
        events, total = service.query_events()
        assert total == 0
        assert events == []


class TestThreadSafety:
    """Test thread-safe concurrent access"""

    def test_concurrent_recording(self):
        """
        GIVEN a TaskTimelineService
        WHEN 10 threads each record 100 events concurrently
        THEN all 1000 events should be recorded without errors
        """
        service = TaskTimelineService()
        errors = []

        def record_events(thread_id):
            try:
                for i in range(100):
                    service.record_event(
                        event_type=TimelineEventType.TASK_CREATED,
                        task_id=f"task-t{thread_id}-{i}",
                        peer_id=f"peer-t{thread_id}",
                    )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=record_events, args=(t,))
            for t in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert service.get_event_count() == 1000


class TestSingletonFactory:
    """Test get_timeline_service() singleton behavior"""

    def test_returns_same_instance(self):
        """
        GIVEN get_timeline_service called multiple times
        WHEN comparing returned instances
        THEN should return the same instance
        """
        # Reset singleton for test isolation
        import backend.services.task_timeline_service as mod
        mod._timeline_service_instance = None

        service1 = get_timeline_service()
        service2 = get_timeline_service()

        assert service1 is service2

        # Cleanup
        mod._timeline_service_instance = None

    def test_returns_correct_type(self):
        """
        GIVEN get_timeline_service called
        WHEN checking return type
        THEN should return TaskTimelineService instance
        """
        import backend.services.task_timeline_service as mod
        mod._timeline_service_instance = None

        service = get_timeline_service()

        assert isinstance(service, TaskTimelineService)

        # Cleanup
        mod._timeline_service_instance = None
