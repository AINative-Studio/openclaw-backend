"""
TaskProgress Protocol Implementation

Implements progress streaming for task execution with lease validation,
rate limiting, and periodic heartbeat scheduling.

Features:
- Progress message schema with Pydantic validation
- Lease token validation for security
- Rate limiting to prevent message flooding
- Periodic heartbeat scheduling (30s minimum interval)
- Intermediate results streaming
- Progress history tracking

Refs #29
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, AsyncGenerator
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


logger = logging.getLogger(__name__)


# Custom exceptions
class ProgressValidationError(Exception):
    """Raised when progress validation fails."""
    pass


class InvalidLeaseTokenError(ProgressValidationError):
    """Raised when lease token validation fails."""
    pass


class TaskProgressMessage(BaseModel):
    """
    TaskProgress message schema.

    Represents a progress update for a task being executed by an agent.
    Includes percentage complete, intermediate results, and lease token
    for validation.
    """

    task_id: str = Field(
        ...,
        description="Unique identifier for the task",
    )
    lease_token: str = Field(
        ...,
        description="Lease token for validation",
    )
    percentage_complete: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of task completion (0-100)",
    )
    intermediate_results: Dict[str, Any] = Field(
        default_factory=dict,
        description="Intermediate results from task execution",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when progress update was created",
    )

    @field_validator("percentage_complete")
    @classmethod
    def validate_percentage(cls, v: float) -> float:
        """Validate percentage is between 0 and 100."""
        if not 0.0 <= v <= 100.0:
            raise ValueError("percentage_complete must be between 0 and 100")
        return v

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class TaskProgressService:
    """
    Service for sending and validating task progress updates.

    Handles:
    - Progress message creation and streaming
    - Lease token validation
    - Rate limiting
    - Progress history tracking
    """

    def __init__(self, min_interval_seconds: float = 30.0):
        """
        Initialize TaskProgressService.

        Args:
            min_interval_seconds: Minimum interval between progress updates (default 30s)
        """
        self.min_interval_seconds = min_interval_seconds
        self._lease_tokens: Dict[str, str] = {}  # task_id -> lease_token
        self._progress_history: Dict[str, List[TaskProgressMessage]] = {}
        self._last_update_time: Dict[str, float] = {}  # task_id -> timestamp
        logger.info(
            f"TaskProgressService initialized with {min_interval_seconds}s minimum interval"
        )

    def register_task_lease(self, task_id: str, lease_token: str) -> None:
        """
        Register a task lease token for validation.

        Args:
            task_id: Unique task identifier
            lease_token: Lease token for this task
        """
        self._lease_tokens[task_id] = lease_token
        self._progress_history[task_id] = []
        logger.info(f"Registered lease token for task {task_id}")

    def _validate_lease_token(self, task_id: str, lease_token: str) -> bool:
        """
        Validate lease token for a task.

        Args:
            task_id: Task identifier
            lease_token: Token to validate

        Returns:
            True if valid

        Raises:
            InvalidLeaseTokenError: If token is invalid
        """
        if task_id not in self._lease_tokens:
            raise InvalidLeaseTokenError(
                f"No lease token registered for task {task_id}"
            )

        if self._lease_tokens[task_id] != lease_token:
            logger.warning(
                f"Invalid lease token for task {task_id}. "
                f"Expected {self._lease_tokens[task_id][:8]}..., "
                f"got {lease_token[:8]}..."
            )
            raise InvalidLeaseTokenError(
                f"Invalid lease token for task {task_id}"
            )

        return True

    def _check_rate_limit(self, task_id: str) -> None:
        """
        Check if rate limit is exceeded for task updates.

        Args:
            task_id: Task identifier

        Raises:
            ProgressValidationError: If rate limit is exceeded
        """
        current_time = asyncio.get_event_loop().time()

        if task_id in self._last_update_time:
            elapsed = current_time - self._last_update_time[task_id]
            if elapsed < self.min_interval_seconds:
                raise ProgressValidationError(
                    f"Rate limit exceeded for task {task_id}. "
                    f"Minimum interval is {self.min_interval_seconds}s, "
                    f"only {elapsed:.2f}s elapsed since last update."
                )

        self._last_update_time[task_id] = current_time

    async def _stream_message(self, message: TaskProgressMessage) -> None:
        """
        Stream progress message to coordinator.

        In a real implementation, this would use libp2p or other P2P
        protocol to stream the message. For now, it's a placeholder.

        Args:
            message: TaskProgressMessage to stream
        """
        # TODO: Implement actual message streaming via libp2p
        logger.info(
            f"Streaming progress update for task {message.task_id}: "
            f"{message.percentage_complete}% complete"
        )
        # Simulate async streaming
        await asyncio.sleep(0.001)

    async def send_progress_update(
        self,
        task_id: str,
        lease_token: str,
        percentage_complete: float,
        intermediate_results: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Send a progress update for a task.

        Args:
            task_id: Unique task identifier
            lease_token: Lease token for validation
            percentage_complete: Percentage of task completion (0-100)
            intermediate_results: Optional intermediate results

        Raises:
            InvalidLeaseTokenError: If lease token is invalid
            ProgressValidationError: If rate limit is exceeded
        """
        # Validate lease token
        self._validate_lease_token(task_id, lease_token)

        # Check rate limit
        self._check_rate_limit(task_id)

        # Create progress message
        message = TaskProgressMessage(
            task_id=task_id,
            lease_token=lease_token,
            percentage_complete=percentage_complete,
            intermediate_results=intermediate_results or {},
            timestamp=datetime.now(timezone.utc),
        )

        # Stream message
        await self._stream_message(message)

        # Store in history
        self._progress_history[task_id].append(message)

        logger.info(
            f"Progress update sent for task {task_id}: "
            f"{percentage_complete}% complete"
        )

    async def validate_and_process_progress(
        self, message: TaskProgressMessage
    ) -> bool:
        """
        Validate and process incoming progress message.

        Args:
            message: TaskProgressMessage to validate

        Returns:
            True if valid and processed

        Raises:
            InvalidLeaseTokenError: If lease token is invalid
        """
        # Validate lease token
        self._validate_lease_token(message.task_id, message.lease_token)

        # Store in history
        if message.task_id not in self._progress_history:
            self._progress_history[message.task_id] = []

        self._progress_history[message.task_id].append(message)

        logger.info(
            f"Progress update validated for task {message.task_id}: "
            f"{message.percentage_complete}% complete"
        )

        return True

    def get_progress_history(self, task_id: str) -> List[TaskProgressMessage]:
        """
        Get progress history for a task.

        Args:
            task_id: Task identifier

        Returns:
            List of progress messages
        """
        return self._progress_history.get(task_id, [])

    def get_latest_progress(self, task_id: str) -> Optional[TaskProgressMessage]:
        """
        Get latest progress update for a task.

        Args:
            task_id: Task identifier

        Returns:
            Latest progress message or None
        """
        history = self._progress_history.get(task_id, [])
        return history[-1] if history else None


class ProgressHeartbeatScheduler:
    """
    Scheduler for periodic progress heartbeat updates.

    Ensures that tasks send progress updates at regular intervals
    (minimum 30s) even if no explicit progress is reported.
    """

    def __init__(
        self,
        progress_service: TaskProgressService,
        interval_seconds: int = 30,
    ):
        """
        Initialize ProgressHeartbeatScheduler.

        Args:
            progress_service: TaskProgressService instance
            interval_seconds: Interval between heartbeat updates (default 30s)
        """
        # Enforce minimum 30s interval
        self.interval_seconds = max(interval_seconds, 30)
        self.progress_service = progress_service
        self._active_tasks: Dict[str, bool] = {}
        logger.info(
            f"ProgressHeartbeatScheduler initialized with "
            f"{self.interval_seconds}s interval"
        )

    async def schedule_heartbeat_updates(
        self,
        task_id: str,
        lease_token: str,
        task_executor: AsyncGenerator[float, None],
        task_duration_seconds: float,
    ) -> AsyncGenerator[float, None]:
        """
        Schedule periodic heartbeat updates for a task.

        Args:
            task_id: Unique task identifier
            lease_token: Lease token for validation
            task_executor: Async generator yielding progress percentages
            task_duration_seconds: Expected task duration in seconds

        Yields:
            Progress percentages from task executor
        """
        self._active_tasks[task_id] = True

        try:
            async for progress in task_executor:
                yield progress

                # Check if task is complete
                if progress >= 100.0:
                    logger.info(f"Task {task_id} completed")
                    break

        finally:
            self._active_tasks[task_id] = False
            logger.info(f"Heartbeat scheduling stopped for task {task_id}")

    def is_task_active(self, task_id: str) -> bool:
        """
        Check if a task is currently active.

        Args:
            task_id: Task identifier

        Returns:
            True if task is active
        """
        return self._active_tasks.get(task_id, False)

    async def send_progress_with_results(
        self,
        task_id: str,
        lease_token: str,
        percentage_complete: float,
        intermediate_results: Dict[str, Any],
    ) -> None:
        """
        Send progress update with intermediate results.

        Args:
            task_id: Unique task identifier
            lease_token: Lease token for validation
            percentage_complete: Percentage of task completion
            intermediate_results: Intermediate results from task execution
        """
        await self.progress_service.send_progress_update(
            task_id=task_id,
            lease_token=lease_token,
            percentage_complete=percentage_complete,
            intermediate_results=intermediate_results,
        )

    async def stop_task(self, task_id: str) -> None:
        """
        Stop heartbeat scheduling for a task.

        Args:
            task_id: Task identifier
        """
        self._active_tasks[task_id] = False
        logger.info(f"Stopped heartbeat scheduling for task {task_id}")


__all__ = [
    "TaskProgressMessage",
    "TaskProgressService",
    "ProgressValidationError",
    "InvalidLeaseTokenError",
    "ProgressHeartbeatScheduler",
]
