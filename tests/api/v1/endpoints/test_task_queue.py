"""
Tests for Task Queue Visibility Endpoints

Tests all endpoints for task queue management:
- GET /api/v1/tasks/queue - List tasks with filters
- GET /api/v1/tasks/{task_id} - Get task details
- GET /api/v1/tasks/{task_id}/history - Task execution history
- GET /api/v1/tasks/active-leases - List active leases
- GET /api/v1/tasks/stats - Queue statistics

Refs: Issue #86
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.db.base import get_db
from backend.db.base_class import Base
from backend.models.task_queue import Task, TaskLease, TaskStatus, TaskPriority
from backend.services.task_timeline_service import (
    get_timeline_service,
    TimelineEventType,
)


# Test database setup
TEST_DATABASE_URL = "sqlite:///./test_task_queue.db"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Override database dependency for testing"""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def setup_database():
    """Create fresh database for each test"""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    # Clear timeline service
    timeline = get_timeline_service()
    timeline.clear()


@pytest.fixture
def sample_tasks(setup_database):
    """Create sample tasks for testing"""
    db = TestSessionLocal()
    tasks = []

    # Task 1: Queued with high priority
    task1 = Task(
        id=uuid4(),
        task_type="image_generation",
        payload={"prompt": "sunset landscape"},
        priority=TaskPriority.HIGH,
        status=TaskStatus.QUEUED,
        required_capabilities={"gpu": True},
        created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    tasks.append(task1)

    # Task 2: Leased with normal priority
    task2 = Task(
        id=uuid4(),
        task_type="text_processing",
        payload={"text": "analyze sentiment"},
        priority=TaskPriority.NORMAL,
        status=TaskStatus.LEASED,
        assigned_peer_id="peer-node-1",
        required_capabilities={"cpu_cores": 4},
        created_at=datetime.now(timezone.utc) - timedelta(minutes=8),
    )
    tasks.append(task2)

    # Task 3: Running
    task3 = Task(
        id=uuid4(),
        task_type="video_encoding",
        payload={"video_id": "vid-123"},
        priority=TaskPriority.NORMAL,
        status=TaskStatus.RUNNING,
        assigned_peer_id="peer-node-2",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        created_at=datetime.now(timezone.utc) - timedelta(minutes=15),
    )
    tasks.append(task3)

    # Task 4: Completed
    task4 = Task(
        id=uuid4(),
        task_type="data_analysis",
        payload={"dataset": "sales-2024"},
        priority=TaskPriority.LOW,
        status=TaskStatus.COMPLETED,
        assigned_peer_id="peer-node-1",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        completed_at=datetime.now(timezone.utc) - timedelta(minutes=20),
        duration_seconds=600,
        result={"summary": "analysis complete"},
        created_at=datetime.now(timezone.utc) - timedelta(minutes=35),
    )
    tasks.append(task4)

    # Task 5: Failed
    task5 = Task(
        id=uuid4(),
        task_type="model_training",
        payload={"model": "gpt-mini"},
        priority=TaskPriority.CRITICAL,
        status=TaskStatus.FAILED,
        assigned_peer_id="peer-node-3",
        started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        completed_at=datetime.now(timezone.utc) - timedelta(hours=1, minutes=45),
        duration_seconds=900,
        error_message="Out of memory",
        error_type="ResourceError",
        retry_count=2,
        created_at=datetime.now(timezone.utc) - timedelta(hours=3),
    )
    tasks.append(task5)

    db.add_all(tasks)
    db.commit()

    # Create active leases for leased and running tasks
    lease1 = TaskLease(
        id=uuid4(),
        task_id=task2.id,
        peer_id="peer-node-1",
        lease_token="jwt-token-task2-masked",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        is_expired=0,
        is_revoked=0,
        lease_duration_seconds=600,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )

    lease2 = TaskLease(
        id=uuid4(),
        task_id=task3.id,
        peer_id="peer-node-2",
        lease_token="jwt-token-task3-masked",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=8),
        is_expired=0,
        is_revoked=0,
        lease_duration_seconds=900,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )

    db.add_all([lease1, lease2])
    db.commit()

    # Add timeline events for task history
    timeline = get_timeline_service()
    for task in tasks:
        timeline.record_event(
            TimelineEventType.TASK_CREATED,
            task_id=str(task.id),
            metadata={"task_type": task.task_type},
        )
        if task.status in [TaskStatus.LEASED, TaskStatus.RUNNING, TaskStatus.COMPLETED, TaskStatus.FAILED]:
            timeline.record_event(
                TimelineEventType.TASK_LEASED,
                task_id=str(task.id),
                peer_id=task.assigned_peer_id,
                metadata={"priority": task.priority.value},
            )
        if task.status in [TaskStatus.RUNNING, TaskStatus.COMPLETED, TaskStatus.FAILED]:
            timeline.record_event(
                TimelineEventType.TASK_STARTED,
                task_id=str(task.id),
                peer_id=task.assigned_peer_id,
            )
        if task.status == TaskStatus.COMPLETED:
            timeline.record_event(
                TimelineEventType.TASK_COMPLETED,
                task_id=str(task.id),
                peer_id=task.assigned_peer_id,
                metadata={"duration_seconds": task.duration_seconds},
            )
        if task.status == TaskStatus.FAILED:
            timeline.record_event(
                TimelineEventType.TASK_FAILED,
                task_id=str(task.id),
                peer_id=task.assigned_peer_id,
                metadata={"error": task.error_message},
            )

    db.close()
    return tasks


class TestTaskQueueList:
    """Tests for GET /api/v1/tasks/queue"""

    def test_list_all_tasks_default_pagination(self, sample_tasks):
        """Should list all tasks with default pagination"""
        response = client.get("/api/v1/tasks/queue")
        assert response.status_code == 200
        data = response.json()

        assert "tasks" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

        assert data["total"] == 5
        assert data["limit"] == 100
        assert data["offset"] == 0
        assert len(data["tasks"]) == 5

    def test_list_tasks_with_pagination(self, sample_tasks):
        """Should paginate task results"""
        response = client.get("/api/v1/tasks/queue?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 5
        assert len(data["tasks"]) == 2

        # Get next page
        response2 = client.get("/api/v1/tasks/queue?limit=2&offset=2")
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["tasks"]) == 2

    def test_filter_by_status(self, sample_tasks):
        """Should filter tasks by status"""
        response = client.get("/api/v1/tasks/queue?status=queued")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1
        assert all(task["status"] == "queued" for task in data["tasks"])

    def test_filter_by_multiple_statuses(self, sample_tasks):
        """Should filter by multiple statuses"""
        response = client.get("/api/v1/tasks/queue?status=leased&status=running")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 2
        statuses = {task["status"] for task in data["tasks"]}
        assert statuses == {"leased", "running"}

    def test_filter_by_priority(self, sample_tasks):
        """Should filter tasks by priority"""
        response = client.get("/api/v1/tasks/queue?priority=high")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1
        assert data["tasks"][0]["priority"] == "high"

    def test_filter_by_assigned_peer(self, sample_tasks):
        """Should filter tasks by assigned peer"""
        response = client.get("/api/v1/tasks/queue?peer_id=peer-node-1")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 2
        assert all(task["assigned_peer_id"] == "peer-node-1" for task in data["tasks"])

    def test_combined_filters(self, sample_tasks):
        """Should apply multiple filters together"""
        response = client.get(
            "/api/v1/tasks/queue?status=completed&priority=low&peer_id=peer-node-1"
        )
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1
        task = data["tasks"][0]
        assert task["status"] == "completed"
        assert task["priority"] == "low"
        assert task["assigned_peer_id"] == "peer-node-1"

    def test_task_structure(self, sample_tasks):
        """Should return tasks with correct structure"""
        response = client.get("/api/v1/tasks/queue?limit=1")
        assert response.status_code == 200
        data = response.json()

        task = data["tasks"][0]
        required_fields = [
            "id", "task_type", "payload", "priority", "status",
            "retry_count", "max_retries", "created_at"
        ]
        for field in required_fields:
            assert field in task

    def test_empty_results(self):
        """Should return empty list when no tasks match filters"""
        response = client.get("/api/v1/tasks/queue?status=expired")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 0
        assert data["tasks"] == []


class TestTaskDetails:
    """Tests for GET /api/v1/tasks/{task_id}"""

    def test_get_existing_task(self, sample_tasks):
        """Should return task details for existing task"""
        task_id = str(sample_tasks[0].id)
        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()

        assert data["id"] == task_id
        assert data["task_type"] == "image_generation"
        assert data["status"] == "queued"
        assert data["priority"] == "high"

    def test_get_completed_task_with_result(self, sample_tasks):
        """Should include result for completed tasks"""
        task_id = str(sample_tasks[3].id)  # Completed task
        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "completed"
        assert data["result"] is not None
        assert data["result"]["summary"] == "analysis complete"
        assert data["duration_seconds"] == 600

    def test_get_failed_task_with_error(self, sample_tasks):
        """Should include error info for failed tasks"""
        task_id = str(sample_tasks[4].id)  # Failed task
        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "failed"
        assert data["error_message"] == "Out of memory"
        assert data["error_type"] == "ResourceError"
        assert data["retry_count"] == 2

    def test_get_task_with_lease_info(self, sample_tasks):
        """Should include current lease info for leased tasks"""
        task_id = str(sample_tasks[1].id)  # Leased task
        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "leased"
        assert "current_lease" in data
        assert data["current_lease"] is not None
        assert data["current_lease"]["peer_id"] == "peer-node-1"
        # Lease token should be masked
        assert "***" in data["current_lease"]["lease_token_masked"]

    def test_get_nonexistent_task(self):
        """Should return 404 for nonexistent task"""
        fake_id = str(uuid4())
        response = client.get(f"/api/v1/tasks/{fake_id}")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_task_invalid_uuid(self):
        """Should return 422 for invalid UUID format"""
        response = client.get("/api/v1/tasks/not-a-uuid")
        assert response.status_code == 422


class TestTaskHistory:
    """Tests for GET /api/v1/tasks/{task_id}/history"""

    def test_get_history_for_completed_task(self, sample_tasks):
        """Should return timeline events for completed task"""
        task_id = str(sample_tasks[3].id)  # Completed task
        response = client.get(f"/api/v1/tasks/{task_id}/history")
        assert response.status_code == 200
        data = response.json()

        assert "events" in data
        assert "total" in data
        assert data["total"] >= 3  # Created, Leased, Started, Completed

        event_types = {event["event_type"] for event in data["events"]}
        assert "TASK_CREATED" in event_types
        assert "TASK_COMPLETED" in event_types

    def test_get_history_for_failed_task(self, sample_tasks):
        """Should include failure event in history"""
        task_id = str(sample_tasks[4].id)  # Failed task
        response = client.get(f"/api/v1/tasks/{task_id}/history")
        assert response.status_code == 200
        data = response.json()

        event_types = {event["event_type"] for event in data["events"]}
        assert "TASK_FAILED" in event_types

        # Find failed event
        failed_events = [e for e in data["events"] if e["event_type"] == "TASK_FAILED"]
        assert len(failed_events) == 1
        assert failed_events[0]["metadata"]["error"] == "Out of memory"

    def test_get_history_pagination(self, sample_tasks):
        """Should paginate history events"""
        task_id = str(sample_tasks[3].id)
        response = client.get(f"/api/v1/tasks/{task_id}/history?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()

        assert len(data["events"]) <= 2
        assert "limit" in data
        assert "offset" in data

    def test_get_history_for_queued_task(self, sample_tasks):
        """Should return limited history for queued task"""
        task_id = str(sample_tasks[0].id)  # Queued task
        response = client.get(f"/api/v1/tasks/{task_id}/history")
        assert response.status_code == 200
        data = response.json()

        # Should only have TASK_CREATED event
        assert data["total"] == 1
        assert data["events"][0]["event_type"] == "TASK_CREATED"

    def test_get_history_nonexistent_task(self):
        """Should return 404 for nonexistent task"""
        fake_id = str(uuid4())
        response = client.get(f"/api/v1/tasks/{fake_id}/history")
        assert response.status_code == 404

    def test_history_event_structure(self, sample_tasks):
        """Should return events with correct structure"""
        task_id = str(sample_tasks[3].id)
        response = client.get(f"/api/v1/tasks/{task_id}/history")
        assert response.status_code == 200
        data = response.json()

        event = data["events"][0]
        required_fields = ["event_type", "task_id", "timestamp", "metadata"]
        for field in required_fields:
            assert field in event


class TestActiveLeases:
    """Tests for GET /api/v1/tasks/active-leases"""

    def test_list_active_leases(self, sample_tasks):
        """Should list all active leases"""
        response = client.get("/api/v1/tasks/active-leases")
        assert response.status_code == 200
        data = response.json()

        assert "leases" in data
        assert "total" in data
        assert data["total"] == 2  # Two active leases
        assert len(data["leases"]) == 2

    def test_active_leases_structure(self, sample_tasks):
        """Should return leases with correct structure"""
        response = client.get("/api/v1/tasks/active-leases")
        assert response.status_code == 200
        data = response.json()

        lease = data["leases"][0]
        required_fields = [
            "id", "task_id", "peer_id", "lease_token_masked",
            "expires_at", "is_expired", "is_revoked",
            "lease_duration_seconds", "created_at"
        ]
        for field in required_fields:
            assert field in lease

    def test_active_leases_include_task_info(self, sample_tasks):
        """Should include associated task information"""
        response = client.get("/api/v1/tasks/active-leases")
        assert response.status_code == 200
        data = response.json()

        lease = data["leases"][0]
        assert "task" in lease
        assert lease["task"]["task_type"] in ["text_processing", "video_encoding"]
        assert lease["task"]["status"] in ["leased", "running"]

    def test_active_leases_token_masking(self, sample_tasks):
        """Should mask lease tokens for security"""
        response = client.get("/api/v1/tasks/active-leases")
        assert response.status_code == 200
        data = response.json()

        for lease in data["leases"]:
            token_masked = lease["lease_token_masked"]
            assert "***" in token_masked
            # Should not contain the full token
            assert len(token_masked) < 50

    def test_active_leases_pagination(self, sample_tasks):
        """Should support pagination"""
        response = client.get("/api/v1/tasks/active-leases?limit=1&offset=0")
        assert response.status_code == 200
        data = response.json()

        assert len(data["leases"]) == 1
        assert data["total"] == 2
        assert data["limit"] == 1
        assert data["offset"] == 0

    def test_filter_by_peer(self, sample_tasks):
        """Should filter leases by peer_id"""
        response = client.get("/api/v1/tasks/active-leases?peer_id=peer-node-1")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1
        assert data["leases"][0]["peer_id"] == "peer-node-1"

    def test_no_active_leases(self):
        """Should return empty list when no active leases"""
        response = client.get("/api/v1/tasks/active-leases")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 0
        assert data["leases"] == []


class TestQueueStats:
    """Tests for GET /api/v1/tasks/stats"""

    def test_get_basic_stats(self, sample_tasks):
        """Should return queue statistics"""
        response = client.get("/api/v1/tasks/stats")
        assert response.status_code == 200
        data = response.json()

        assert "summary" in data
        summary = data["summary"]

        # Check status counts
        assert summary["queued_count"] == 1
        assert summary["leased_count"] == 1
        assert summary["running_count"] == 1
        assert summary["completed_count"] == 1
        assert summary["failed_count"] == 1
        assert summary["total_count"] == 5

    def test_stats_include_active_leases(self, sample_tasks):
        """Should include active lease count"""
        response = client.get("/api/v1/tasks/stats")
        assert response.status_code == 200
        data = response.json()

        assert data["summary"]["active_leases_count"] == 2

    def test_stats_include_average_execution_time(self, sample_tasks):
        """Should calculate average execution time for completed tasks"""
        response = client.get("/api/v1/tasks/stats")
        assert response.status_code == 200
        data = response.json()

        # One completed task with 600s duration
        assert "avg_execution_time_seconds" in data["summary"]
        assert data["summary"]["avg_execution_time_seconds"] == 600.0

    def test_stats_include_time_series(self, sample_tasks):
        """Should include time-series data for charts"""
        response = client.get("/api/v1/tasks/stats")
        assert response.status_code == 200
        data = response.json()

        assert "time_series" in data
        time_series = data["time_series"]

        # Should have hourly buckets
        assert "hourly" in time_series
        assert len(time_series["hourly"]) > 0

        # Each bucket should have timestamp and counts
        bucket = time_series["hourly"][0]
        assert "timestamp" in bucket
        assert "created" in bucket
        assert "completed" in bucket
        assert "failed" in bucket

    def test_stats_time_series_custom_interval(self, sample_tasks):
        """Should support custom time series interval"""
        response = client.get("/api/v1/tasks/stats?interval=daily")
        assert response.status_code == 200
        data = response.json()

        assert "time_series" in data
        assert "daily" in data["time_series"]

    def test_stats_by_priority(self, sample_tasks):
        """Should include breakdown by priority"""
        response = client.get("/api/v1/tasks/stats")
        assert response.status_code == 200
        data = response.json()

        assert "by_priority" in data
        by_priority = data["by_priority"]

        assert by_priority["high"] == 1
        assert by_priority["normal"] == 2
        assert by_priority["low"] == 1
        assert by_priority["critical"] == 1

    def test_stats_by_type(self, sample_tasks):
        """Should include breakdown by task type"""
        response = client.get("/api/v1/tasks/stats")
        assert response.status_code == 200
        data = response.json()

        assert "by_type" in data
        by_type = data["by_type"]

        # Should have counts for each task type
        assert by_type["image_generation"] == 1
        assert by_type["text_processing"] == 1
        assert by_type["video_encoding"] == 1

    def test_stats_empty_queue(self):
        """Should return zero stats for empty queue"""
        response = client.get("/api/v1/tasks/stats")
        assert response.status_code == 200
        data = response.json()

        summary = data["summary"]
        assert summary["total_count"] == 0
        assert summary["queued_count"] == 0
        assert summary["active_leases_count"] == 0
        assert summary["avg_execution_time_seconds"] is None

    def test_stats_time_range_filter(self, sample_tasks):
        """Should support time range filtering"""
        # Get stats for last hour only
        from urllib.parse import quote
        now = datetime.now(timezone.utc)
        since = (now - timedelta(hours=1)).isoformat()

        response = client.get(f"/api/v1/tasks/stats?since={quote(since)}")
        assert response.status_code == 200
        data = response.json()

        # Should have fewer tasks than total
        assert data["summary"]["total_count"] <= 5
