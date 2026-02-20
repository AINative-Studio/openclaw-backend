"""
Test Duplicate Prevention Service

BDD-style tests for duplicate work prevention using idempotency keys.
Tests cover duplicate detection, concurrent submissions, and metrics tracking.

Epic E6-S7: Duplicate Work Prevention (3 story points)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from backend.models.task_models import Base, Task, TaskStatus
from backend.services.duplicate_prevention_service import (
    DuplicatePreventionService,
    DuplicateTaskError,
    TaskCreationResult,
)


@pytest.fixture
def db_session():
    """Create in-memory SQLite database session for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def metrics_tracker():
    """Mock metrics tracker"""
    return Mock()


@pytest.fixture
def duplicate_prevention_service(db_session, metrics_tracker):
    """Create DuplicatePreventionService instance"""
    return DuplicatePreventionService(
        db_session=db_session,
        metrics_tracker=metrics_tracker,
    )


class TestDuplicateTaskCreation:
    """
    Test suite for duplicate task creation prevention

    Given: Duplicate idempotency_key
    When: Creating task
    Then: Should return existing task_id
    """

    def test_prevent_duplicate_task_creation(
        self, duplicate_prevention_service, db_session, metrics_tracker
    ):
        """
        Given a task with idempotency_key already exists
        When attempting to create another task with same idempotency_key
        Then should return existing task_id without creating duplicate
        """
        # Given: Create initial task
        idempotency_key = "test-idem-key-001"
        task_id_1 = "task-001"
        payload_1 = {"message": "first submission"}

        result1 = duplicate_prevention_service.create_task_with_deduplication(
            task_id=task_id_1,
            idempotency_key=idempotency_key,
            payload=payload_1,
        )

        assert result1.is_new_task is True
        assert result1.task_id == task_id_1
        assert result1.duplicate_of is None

        # When: Attempt to create duplicate task
        task_id_2 = "task-002"  # Different task_id
        payload_2 = {"message": "duplicate submission"}

        result2 = duplicate_prevention_service.create_task_with_deduplication(
            task_id=task_id_2,
            idempotency_key=idempotency_key,  # Same idempotency_key
            payload=payload_2,
        )

        # Then: Should return existing task_id
        assert result2.is_new_task is False
        assert result2.task_id == task_id_1  # Returns original task_id
        assert result2.duplicate_of == task_id_1

        # Verify only one task exists in database
        tasks = db_session.query(Task).filter_by(idempotency_key=idempotency_key).all()
        assert len(tasks) == 1
        assert tasks[0].task_id == task_id_1

        # Verify duplicate metric was tracked
        metrics_tracker.increment.assert_called_with(
            "duplicate_task_prevented",
            tags={"idempotency_key": idempotency_key},
        )

    def test_create_task_with_unique_idempotency_key(
        self, duplicate_prevention_service, db_session, metrics_tracker
    ):
        """
        Given a unique idempotency_key
        When creating a new task
        Then should create task successfully and return new task_id
        """
        # When: Create task with unique idempotency_key
        task_id = "task-unique-001"
        idempotency_key = "unique-idem-key"
        payload = {"message": "new task"}

        result = duplicate_prevention_service.create_task_with_deduplication(
            task_id=task_id,
            idempotency_key=idempotency_key,
            payload=payload,
        )

        # Then: Should create new task
        assert result.is_new_task is True
        assert result.task_id == task_id
        assert result.duplicate_of is None

        # Verify task exists in database
        task = db_session.query(Task).filter_by(task_id=task_id).first()
        assert task is not None
        assert task.idempotency_key == idempotency_key
        assert task.status == TaskStatus.QUEUED.value

        # Verify new task metric was tracked
        metrics_tracker.increment.assert_called_with(
            "task_created",
            tags={"idempotency_key": idempotency_key},
        )

    def test_multiple_tasks_with_different_idempotency_keys(
        self, duplicate_prevention_service, db_session
    ):
        """
        Given multiple tasks with different idempotency_keys
        When creating tasks
        Then should create all tasks successfully
        """
        # Create 3 tasks with different idempotency keys
        tasks_data = [
            ("task-001", "idem-key-001", {"msg": "task 1"}),
            ("task-002", "idem-key-002", {"msg": "task 2"}),
            ("task-003", "idem-key-003", {"msg": "task 3"}),
        ]

        for task_id, idem_key, payload in tasks_data:
            result = duplicate_prevention_service.create_task_with_deduplication(
                task_id=task_id,
                idempotency_key=idem_key,
                payload=payload,
            )
            assert result.is_new_task is True
            assert result.task_id == task_id

        # Verify all tasks exist
        all_tasks = db_session.query(Task).all()
        assert len(all_tasks) == 3


class TestConcurrentDuplicates:
    """
    Test suite for concurrent duplicate detection

    Given: Concurrent task submissions with same idempotency_key
    When: Creating tasks simultaneously
    Then: Should only create one task
    """

    def test_detect_concurrent_duplicates(
        self, duplicate_prevention_service, db_session, metrics_tracker
    ):
        """
        Given concurrent submissions with same idempotency_key
        When both attempt to create task simultaneously
        Then only one task should be created due to unique constraint
        """
        idempotency_key = "concurrent-idem-key"
        task_id_1 = "concurrent-task-001"
        task_id_2 = "concurrent-task-002"

        # Create first task
        result1 = duplicate_prevention_service.create_task_with_deduplication(
            task_id=task_id_1,
            idempotency_key=idempotency_key,
            payload={"msg": "first"},
        )
        assert result1.is_new_task is True

        # Simulate concurrent creation attempt
        # This should detect existing task
        result2 = duplicate_prevention_service.create_task_with_deduplication(
            task_id=task_id_2,
            idempotency_key=idempotency_key,
            payload={"msg": "second"},
        )

        # Then: Second attempt should return existing task
        assert result2.is_new_task is False
        assert result2.task_id == task_id_1  # Returns first task_id

        # Verify only one task exists
        tasks = db_session.query(Task).filter_by(idempotency_key=idempotency_key).all()
        assert len(tasks) == 1
        assert tasks[0].task_id == task_id_1

    def test_handle_database_integrity_error(
        self, duplicate_prevention_service, db_session, metrics_tracker
    ):
        """
        Given database IntegrityError on duplicate key
        When creating task with existing idempotency_key
        Then should catch error and return existing task
        """
        idempotency_key = "integrity-test-key"

        # Create first task
        result1 = duplicate_prevention_service.create_task_with_deduplication(
            task_id="task-001",
            idempotency_key=idempotency_key,
            payload={"msg": "first"},
        )
        assert result1.is_new_task is True

        # Mock IntegrityError on second attempt
        # This simulates race condition where duplicate check passes
        # but insert fails due to unique constraint
        with patch.object(
            db_session, "commit", side_effect=IntegrityError("", "", "")
        ) as mock_commit:
            # First call raises IntegrityError, subsequent calls succeed
            mock_commit.side_effect = [
                IntegrityError("UNIQUE constraint failed", "", ""),
                None,  # Successful commit after rollback
            ]

            result2 = duplicate_prevention_service.create_task_with_deduplication(
                task_id="task-002",
                idempotency_key=idempotency_key,
                payload={"msg": "second"},
            )

            # Should handle error and return existing task
            assert result2.is_new_task is False
            assert result2.task_id == "task-001"


class TestDuplicateAttemptLogging:
    """
    Test suite for duplicate attempt logging

    Given: Duplicate submission detected
    When: Detecting duplicate
    Then: Should log attempt with metadata
    """

    def test_log_duplicate_attempts(
        self, duplicate_prevention_service, db_session, metrics_tracker
    ):
        """
        Given a duplicate task submission
        When duplicate is detected
        Then should log attempt with metadata including:
        - Original task_id
        - Attempted task_id
        - Idempotency_key
        - Timestamp
        - Payload comparison
        """
        idempotency_key = "log-test-key"

        # Create original task
        original_task_id = "original-task"
        original_payload = {"message": "original", "priority": "high"}

        duplicate_prevention_service.create_task_with_deduplication(
            task_id=original_task_id,
            idempotency_key=idempotency_key,
            payload=original_payload,
        )

        # Attempt duplicate with different payload
        duplicate_task_id = "duplicate-task"
        duplicate_payload = {"message": "duplicate", "priority": "low"}

        with patch("backend.services.duplicate_prevention_service.logger") as mock_logger:
            result = duplicate_prevention_service.create_task_with_deduplication(
                task_id=duplicate_task_id,
                idempotency_key=idempotency_key,
                payload=duplicate_payload,
            )

            # Verify duplicate was logged with metadata
            mock_logger.warning.assert_called_once()
            log_call_args = mock_logger.warning.call_args[0][0]

            # Check log message contains key information
            assert "Duplicate task submission detected" in log_call_args
            assert idempotency_key in str(mock_logger.warning.call_args)
            assert original_task_id in str(mock_logger.warning.call_args)

    def test_log_includes_duplicate_metadata(
        self, duplicate_prevention_service, db_session
    ):
        """
        Given a duplicate task attempt
        When logging duplicate
        Then should include comprehensive metadata
        """
        idempotency_key = "metadata-test-key"

        # Create original task
        duplicate_prevention_service.create_task_with_deduplication(
            task_id="original",
            idempotency_key=idempotency_key,
            payload={"data": "original"},
        )

        # Capture log output
        with patch("backend.services.duplicate_prevention_service.logger") as mock_logger:
            result = duplicate_prevention_service.create_task_with_deduplication(
                task_id="duplicate-attempt",
                idempotency_key=idempotency_key,
                payload={"data": "duplicate"},
            )

            # Verify logging was called
            assert mock_logger.warning.called

            # Verify extra context was logged
            assert mock_logger.info.called  # Should log duplicate detection


class TestIdempotencyKeyEnforcement:
    """
    Test suite for idempotency key enforcement

    Given: Database with unique constraint on idempotency_key
    When: Attempting to create duplicate
    Then: Should enforce uniqueness
    """

    def test_idempotency_key_unique_constraint(self, db_session):
        """
        Given database schema with unique constraint on idempotency_key
        When attempting to insert duplicate idempotency_key directly
        Then should raise IntegrityError
        """
        idempotency_key = "constraint-test-key"

        # Create first task
        task1 = Task(
            task_id="task-001",
            idempotency_key=idempotency_key,
            status=TaskStatus.QUEUED.value,
            payload={"msg": "first"},
        )
        db_session.add(task1)
        db_session.commit()

        # Attempt to create second task with same idempotency_key
        task2 = Task(
            task_id="task-002",
            idempotency_key=idempotency_key,  # Duplicate key
            status=TaskStatus.QUEUED.value,
            payload={"msg": "second"},
        )
        db_session.add(task2)

        # Should raise IntegrityError due to unique constraint
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_null_idempotency_key_not_allowed(self, db_session):
        """
        Given idempotency_key is required (nullable=False)
        When attempting to create task without idempotency_key
        Then should raise IntegrityError
        """
        task = Task(
            task_id="task-no-idem",
            idempotency_key=None,  # Not allowed
            status=TaskStatus.QUEUED.value,
            payload={"msg": "test"},
        )
        db_session.add(task)

        # Should raise IntegrityError for NOT NULL constraint
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestMetricsTracking:
    """
    Test suite for metrics tracking

    Given: Metrics tracker configured
    When: Creating tasks or detecting duplicates
    Then: Should track appropriate metrics
    """

    def test_track_duplicate_prevention_metric(
        self, duplicate_prevention_service, metrics_tracker
    ):
        """
        Given a duplicate task is prevented
        When duplicate detection occurs
        Then should increment duplicate_task_prevented metric
        """
        idempotency_key = "metrics-test-key"

        # Create original task
        duplicate_prevention_service.create_task_with_deduplication(
            task_id="original",
            idempotency_key=idempotency_key,
            payload={"msg": "first"},
        )

        # Reset mock to clear previous calls
        metrics_tracker.reset_mock()

        # Attempt duplicate
        duplicate_prevention_service.create_task_with_deduplication(
            task_id="duplicate",
            idempotency_key=idempotency_key,
            payload={"msg": "second"},
        )

        # Verify metric was tracked
        metrics_tracker.increment.assert_called_with(
            "duplicate_task_prevented",
            tags={"idempotency_key": idempotency_key},
        )

    def test_track_task_creation_metric(
        self, duplicate_prevention_service, metrics_tracker
    ):
        """
        Given a new task is created
        When task creation succeeds
        Then should increment task_created metric
        """
        # Create new task
        duplicate_prevention_service.create_task_with_deduplication(
            task_id="new-task",
            idempotency_key="new-key",
            payload={"msg": "new"},
        )

        # Verify metric was tracked
        metrics_tracker.increment.assert_called_with(
            "task_created",
            tags={"idempotency_key": "new-key"},
        )

    def test_track_multiple_duplicate_attempts(
        self, duplicate_prevention_service, metrics_tracker
    ):
        """
        Given multiple duplicate submissions for same idempotency_key
        When each duplicate is detected
        Then should increment metric for each attempt
        """
        idempotency_key = "multi-dup-key"

        # Create original
        duplicate_prevention_service.create_task_with_deduplication(
            task_id="original",
            idempotency_key=idempotency_key,
            payload={"msg": "first"},
        )

        # Reset to count only duplicates
        metrics_tracker.reset_mock()

        # Attempt 3 duplicates
        for i in range(3):
            duplicate_prevention_service.create_task_with_deduplication(
                task_id=f"dup-{i}",
                idempotency_key=idempotency_key,
                payload={"msg": f"duplicate {i}"},
            )

        # Should have tracked 3 duplicate attempts
        assert metrics_tracker.increment.call_count == 3


class TestTaskCreationResult:
    """
    Test suite for TaskCreationResult data structure

    Verify that TaskCreationResult provides complete information
    about task creation or duplicate detection
    """

    def test_task_creation_result_new_task(self, duplicate_prevention_service):
        """
        Given a new task is created
        When examining result
        Then should indicate new task with correct attributes
        """
        result = duplicate_prevention_service.create_task_with_deduplication(
            task_id="new-task",
            idempotency_key="unique-key",
            payload={"msg": "test"},
        )

        assert result.is_new_task is True
        assert result.task_id == "new-task"
        assert result.duplicate_of is None
        assert result.idempotency_key == "unique-key"
        assert isinstance(result.created_at, datetime)

    def test_task_creation_result_duplicate(self, duplicate_prevention_service):
        """
        Given a duplicate task is detected
        When examining result
        Then should indicate duplicate with original task_id
        """
        idempotency_key = "dup-result-key"

        # Create original
        duplicate_prevention_service.create_task_with_deduplication(
            task_id="original",
            idempotency_key=idempotency_key,
            payload={"msg": "first"},
        )

        # Attempt duplicate
        result = duplicate_prevention_service.create_task_with_deduplication(
            task_id="duplicate",
            idempotency_key=idempotency_key,
            payload={"msg": "second"},
        )

        assert result.is_new_task is False
        assert result.task_id == "original"  # Returns original task_id
        assert result.duplicate_of == "original"
        assert result.idempotency_key == idempotency_key
        assert isinstance(result.created_at, datetime)


class TestEdgeCases:
    """
    Test suite for edge cases and error conditions
    """

    def test_empty_idempotency_key(self, duplicate_prevention_service, db_session):
        """
        Given an empty idempotency_key
        When creating task
        Then should raise ValueError
        """
        with pytest.raises(ValueError, match="Idempotency key cannot be empty"):
            duplicate_prevention_service.create_task_with_deduplication(
                task_id="task-001",
                idempotency_key="",
                payload={"msg": "test"},
            )

    def test_empty_task_id(self, duplicate_prevention_service, db_session):
        """
        Given an empty task_id
        When creating task
        Then should raise ValueError
        """
        with pytest.raises(ValueError, match="Task ID cannot be empty"):
            duplicate_prevention_service.create_task_with_deduplication(
                task_id="",
                idempotency_key="valid-key",
                payload={"msg": "test"},
            )

    def test_none_payload_allowed(self, duplicate_prevention_service, db_session):
        """
        Given payload is None
        When creating task
        Then should create task successfully with null payload
        """
        result = duplicate_prevention_service.create_task_with_deduplication(
            task_id="task-null-payload",
            idempotency_key="null-payload-key",
            payload=None,
        )

        assert result.is_new_task is True
        task = db_session.query(Task).filter_by(task_id="task-null-payload").first()
        assert task.payload is None

    def test_large_payload(self, duplicate_prevention_service, db_session):
        """
        Given a large JSON payload
        When creating task
        Then should handle large payload correctly
        """
        large_payload = {
            "data": ["item"] * 1000,  # Large array
            "metadata": {f"key_{i}": f"value_{i}" for i in range(100)},
        }

        result = duplicate_prevention_service.create_task_with_deduplication(
            task_id="large-payload-task",
            idempotency_key="large-payload-key",
            payload=large_payload,
        )

        assert result.is_new_task is True
        task = db_session.query(Task).filter_by(task_id="large-payload-task").first()
        assert len(task.payload["data"]) == 1000
        assert len(task.payload["metadata"]) == 100


class TestQueryMethods:
    """
    Test suite for query and statistics methods
    """

    def test_get_task_by_idempotency_key_found(
        self, duplicate_prevention_service, db_session
    ):
        """
        Given a task exists with idempotency_key
        When querying by idempotency_key
        Then should return task dictionary
        """
        # Create task
        duplicate_prevention_service.create_task_with_deduplication(
            task_id="query-task",
            idempotency_key="query-key",
            payload={"msg": "test"},
        )

        # Query by idempotency_key
        result = duplicate_prevention_service.get_task_by_idempotency_key("query-key")

        assert result is not None
        assert result["task_id"] == "query-task"
        assert result["idempotency_key"] == "query-key"
        assert result["status"] == TaskStatus.QUEUED.value

    def test_get_task_by_idempotency_key_not_found(
        self, duplicate_prevention_service
    ):
        """
        Given no task exists with idempotency_key
        When querying by idempotency_key
        Then should return None
        """
        result = duplicate_prevention_service.get_task_by_idempotency_key(
            "nonexistent-key"
        )
        assert result is None

    def test_get_duplicate_statistics(self, duplicate_prevention_service):
        """
        Given multiple tasks created
        When requesting statistics
        Then should return accurate statistics
        """
        # Create 3 tasks
        for i in range(3):
            duplicate_prevention_service.create_task_with_deduplication(
                task_id=f"stats-task-{i}",
                idempotency_key=f"stats-key-{i}",
                payload={"msg": f"test {i}"},
            )

        # Get statistics
        stats = duplicate_prevention_service.get_duplicate_statistics()

        assert stats["total_tasks"] == 3
        assert stats["unique_idempotency_keys"] == 3
        assert stats["duplicate_prevention_active"] is True

    def test_task_creation_result_repr(self):
        """
        Given TaskCreationResult
        When converting to string representation
        Then should provide readable format
        """
        result_new = TaskCreationResult(
            is_new_task=True,
            task_id="task-001",
            duplicate_of=None,
            idempotency_key="key-001",
            created_at=datetime.now(timezone.utc),
        )

        repr_str = repr(result_new)
        assert "new" in repr_str
        assert "task-001" in repr_str

        result_dup = TaskCreationResult(
            is_new_task=False,
            task_id="task-001",
            duplicate_of="task-001",
            idempotency_key="key-001",
            created_at=datetime.now(timezone.utc),
        )

        repr_str_dup = repr(result_dup)
        assert "duplicate" in repr_str_dup
        assert "task-001" in repr_str_dup


class TestCustomStatus:
    """
    Test suite for custom task status on creation
    """

    def test_create_task_with_custom_status(
        self, duplicate_prevention_service, db_session
    ):
        """
        Given a custom status is provided
        When creating task
        Then should create task with custom status
        """
        result = duplicate_prevention_service.create_task_with_deduplication(
            task_id="custom-status-task",
            idempotency_key="custom-status-key",
            payload={"msg": "test"},
            status=TaskStatus.RUNNING.value,
        )

        assert result.is_new_task is True
        task = db_session.query(Task).filter_by(task_id="custom-status-task").first()
        assert task.status == TaskStatus.RUNNING.value
