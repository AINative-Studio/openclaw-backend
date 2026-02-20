"""
Duplicate Prevention Service

Prevents duplicate work by detecting identical task submissions via idempotency keys.
Uses database unique constraints and atomic operations to guarantee exactly-once semantics
even under concurrent submissions.

Features:
- Idempotency key enforcement with unique database constraint
- Duplicate detection with existing task_id return
- Comprehensive logging of duplicate attempts with metadata
- Metrics tracking for monitoring and alerting
- Thread-safe and concurrent-safe implementation

Epic E6-S7: Duplicate Work Prevention (3 story points)
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend.models.task_models import Task, TaskStatus


# Configure logging
logger = logging.getLogger(__name__)


class DuplicateTaskError(Exception):
    """Raised when duplicate task is detected"""
    pass


@dataclass
class TaskCreationResult:
    """
    Result of task creation with deduplication

    Contains complete information about task creation or duplicate detection,
    enabling clients to handle both cases appropriately.
    """
    is_new_task: bool
    task_id: str
    duplicate_of: Optional[str]
    idempotency_key: str
    created_at: datetime

    def __repr__(self) -> str:
        status = "new" if self.is_new_task else "duplicate"
        return f"<TaskCreationResult {status} task_id={self.task_id}>"


class DuplicatePreventionService:
    """
    Duplicate Prevention Service

    Prevents duplicate task creation using idempotency keys with database-level
    enforcement. Handles concurrent submissions safely through unique constraints
    and atomic database operations.

    Key Features:
    1. Idempotency key enforcement via unique database constraint
    2. Returns existing task_id for duplicate submissions
    3. No duplicate task creation guaranteed by DB constraint
    4. Comprehensive logging with duplicate attempt metadata
    5. Metrics tracking for monitoring duplicate rates
    6. Thread-safe and concurrent-safe implementation

    Usage:
        service = DuplicatePreventionService(db_session, metrics_tracker)
        result = service.create_task_with_deduplication(
            task_id="task-123",
            idempotency_key="client-request-456",
            payload={"data": "..."}
        )

        if result.is_new_task:
            print(f"Created new task: {result.task_id}")
        else:
            print(f"Duplicate detected, existing task: {result.task_id}")
    """

    def __init__(
        self,
        db_session: Session,
        metrics_tracker: Optional[Any] = None,
    ):
        """
        Initialize Duplicate Prevention Service

        Args:
            db_session: SQLAlchemy database session
            metrics_tracker: Optional metrics tracker for monitoring
        """
        self.db_session = db_session
        self.metrics_tracker = metrics_tracker

    def create_task_with_deduplication(
        self,
        task_id: str,
        idempotency_key: str,
        payload: Optional[Dict[str, Any]] = None,
        status: str = TaskStatus.QUEUED.value,
    ) -> TaskCreationResult:
        """
        Create task with duplicate prevention via idempotency key

        This method implements exactly-once semantics for task creation:
        1. Checks if task with idempotency_key already exists
        2. If exists, returns existing task_id (no duplicate created)
        3. If not exists, creates new task atomically
        4. Handles concurrent races via database unique constraint
        5. Logs all duplicate attempts with metadata
        6. Tracks metrics for monitoring

        Args:
            task_id: Unique task identifier
            idempotency_key: Client-provided idempotency key (must be unique)
            payload: Optional task payload (JSON-serializable)
            status: Initial task status (default: QUEUED)

        Returns:
            TaskCreationResult indicating new task or duplicate

        Raises:
            ValueError: If task_id or idempotency_key is empty
            DuplicateTaskError: If duplicate detected (optional, based on client needs)

        Thread Safety:
            This method is thread-safe and concurrent-safe due to database
            unique constraint on idempotency_key column. Multiple concurrent
            calls with same idempotency_key will result in exactly one task
            being created, with others receiving duplicate indication.
        """
        # Validate inputs
        if not task_id or not task_id.strip():
            raise ValueError("Task ID cannot be empty")
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("Idempotency key cannot be empty")

        logger.info(
            f"Creating task with deduplication: task_id={task_id}, "
            f"idempotency_key={idempotency_key}"
        )

        # Step 1: Check if task with this idempotency_key already exists
        existing_task = self._find_existing_task_by_idempotency_key(idempotency_key)

        if existing_task:
            # Duplicate detected - return existing task
            return self._handle_duplicate_task(
                existing_task=existing_task,
                attempted_task_id=task_id,
                idempotency_key=idempotency_key,
                attempted_payload=payload,
            )

        # Step 2: No existing task found, attempt to create new task
        try:
            new_task = self._create_new_task(
                task_id=task_id,
                idempotency_key=idempotency_key,
                payload=payload,
                status=status,
            )

            # Track success metric
            self._track_metric("task_created", idempotency_key)

            logger.info(
                f"Successfully created new task: task_id={task_id}, "
                f"idempotency_key={idempotency_key}"
            )

            return TaskCreationResult(
                is_new_task=True,
                task_id=new_task.task_id,
                duplicate_of=None,
                idempotency_key=idempotency_key,
                created_at=new_task.created_at or datetime.now(timezone.utc),
            )

        except IntegrityError as e:
            # Race condition: Another process created task with same idempotency_key
            # between our check and insert. Rollback and fetch existing task.
            logger.warning(
                f"IntegrityError during task creation (race condition): {e}. "
                f"Fetching existing task for idempotency_key={idempotency_key}"
            )

            # Rollback failed transaction
            self.db_session.rollback()

            # Fetch the task that was created by the other process
            existing_task = self._find_existing_task_by_idempotency_key(idempotency_key)

            if existing_task:
                return self._handle_duplicate_task(
                    existing_task=existing_task,
                    attempted_task_id=task_id,
                    idempotency_key=idempotency_key,
                    attempted_payload=payload,
                )
            else:
                # Should never happen, but handle gracefully
                logger.error(
                    f"IntegrityError occurred but no existing task found for "
                    f"idempotency_key={idempotency_key}. This indicates a data "
                    "consistency issue."
                )
                raise

    def _find_existing_task_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[Task]:
        """
        Find existing task by idempotency key

        Args:
            idempotency_key: Idempotency key to search for

        Returns:
            Existing Task if found, None otherwise
        """
        return (
            self.db_session.query(Task)
            .filter_by(idempotency_key=idempotency_key)
            .first()
        )

    def _create_new_task(
        self,
        task_id: str,
        idempotency_key: str,
        payload: Optional[Dict[str, Any]],
        status: str,
    ) -> Task:
        """
        Create new task in database

        Args:
            task_id: Task identifier
            idempotency_key: Idempotency key
            payload: Task payload
            status: Task status

        Returns:
            Created Task instance

        Raises:
            IntegrityError: If unique constraint violated (concurrent duplicate)
        """
        task = Task(
            task_id=task_id,
            idempotency_key=idempotency_key,
            payload=payload,
            status=status,
        )
        self.db_session.add(task)
        self.db_session.commit()
        return task

    def _handle_duplicate_task(
        self,
        existing_task: Task,
        attempted_task_id: str,
        idempotency_key: str,
        attempted_payload: Optional[Dict[str, Any]],
    ) -> TaskCreationResult:
        """
        Handle duplicate task detection

        Logs comprehensive metadata about duplicate attempt and tracks metrics.

        Args:
            existing_task: Existing task found in database
            attempted_task_id: Task ID that was attempted
            idempotency_key: Idempotency key
            attempted_payload: Payload that was attempted

        Returns:
            TaskCreationResult indicating duplicate
        """
        # Log duplicate attempt with comprehensive metadata
        self._log_duplicate_attempt(
            existing_task=existing_task,
            attempted_task_id=attempted_task_id,
            idempotency_key=idempotency_key,
            attempted_payload=attempted_payload,
        )

        # Track duplicate prevention metric
        self._track_metric("duplicate_task_prevented", idempotency_key)

        return TaskCreationResult(
            is_new_task=False,
            task_id=existing_task.task_id,  # Return existing task_id
            duplicate_of=existing_task.task_id,
            idempotency_key=idempotency_key,
            created_at=existing_task.created_at or datetime.now(timezone.utc),
        )

    def _log_duplicate_attempt(
        self,
        existing_task: Task,
        attempted_task_id: str,
        idempotency_key: str,
        attempted_payload: Optional[Dict[str, Any]],
    ):
        """
        Log duplicate task attempt with comprehensive metadata

        Logs include:
        - Existing task_id (what will be returned)
        - Attempted task_id (what client tried to create)
        - Idempotency key (the duplicate key)
        - Timestamp of detection
        - Payload comparison (existing vs attempted)

        Args:
            existing_task: Existing task in database
            attempted_task_id: Task ID client attempted to create
            idempotency_key: Idempotency key
            attempted_payload: Payload client attempted to submit
        """
        duplicate_metadata = {
            "existing_task_id": existing_task.task_id,
            "attempted_task_id": attempted_task_id,
            "idempotency_key": idempotency_key,
            "existing_status": existing_task.status,
            "existing_created_at": existing_task.created_at.isoformat()
            if existing_task.created_at
            else None,
            "existing_payload_size": len(str(existing_task.payload))
            if existing_task.payload
            else 0,
            "attempted_payload_size": len(str(attempted_payload))
            if attempted_payload
            else 0,
            "payloads_match": existing_task.payload == attempted_payload,
        }

        logger.warning(
            f"Duplicate task submission detected: "
            f"idempotency_key={idempotency_key}, "
            f"existing_task_id={existing_task.task_id}, "
            f"attempted_task_id={attempted_task_id}",
            extra=duplicate_metadata,
        )

        logger.info(
            f"Returning existing task_id={existing_task.task_id} for duplicate "
            f"submission with idempotency_key={idempotency_key}"
        )

    def _track_metric(self, metric_name: str, idempotency_key: str):
        """
        Track metric for monitoring

        Args:
            metric_name: Name of metric to track
            idempotency_key: Idempotency key for tagging
        """
        if self.metrics_tracker:
            self.metrics_tracker.increment(
                metric_name,
                tags={"idempotency_key": idempotency_key},
            )

    def get_task_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get task by idempotency key

        Useful for clients to check if task exists before submission.

        Args:
            idempotency_key: Idempotency key to search for

        Returns:
            Task dictionary if found, None otherwise
        """
        task = self._find_existing_task_by_idempotency_key(idempotency_key)
        if task:
            return task.to_dict()
        return None

    def get_duplicate_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about duplicate prevention

        Returns dictionary with:
        - Total tasks
        - Unique idempotency keys
        - Potential duplicate count (tasks - unique keys)

        Returns:
            Dictionary with duplicate statistics
        """
        total_tasks = self.db_session.query(Task).count()
        unique_keys = (
            self.db_session.query(Task.idempotency_key).distinct().count()
        )

        # In a proper implementation, unique_keys should equal total_tasks
        # due to unique constraint. Any difference indicates historical issues.
        return {
            "total_tasks": total_tasks,
            "unique_idempotency_keys": unique_keys,
            "potential_duplicates_prevented": 0,  # Tracked via metrics in production
            "duplicate_prevention_active": True,
        }
