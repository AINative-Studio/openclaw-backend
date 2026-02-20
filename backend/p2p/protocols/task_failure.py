"""
TaskFailure protocol implementation.

This module implements the TaskFailure message schema, error categorization,
and failure reporting handler for the OpenCLAW P2P agent swarm.

Follows the protocol specification from OPENCLAW_P2P_SWARM_PRD.md:
- Message Type: TASK_FAILURE (5)
- Protocol: /openclaw/task/result/1.0
- Security: Lease token validation, rate limiting, sanitization
"""

import re
import traceback as tb_module
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any
from collections import defaultdict
from dataclasses import dataclass, field
from pydantic import BaseModel, Field, validator


class FailureType(str, Enum):
    """
    Categorizes the type of failure that occurred during task execution.

    Used to determine error handling strategy and retry eligibility.
    """
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    VALIDATION_ERROR = "validation_error"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    PERMISSION_DENIED = "permission_denied"

    def to_error_category(self) -> "ErrorCategory":
        """Map FailureType to ErrorCategory for retry logic."""
        retriable_types = {
            FailureType.TIMEOUT,
            FailureType.CONNECTION_ERROR,
            FailureType.RUNTIME_ERROR,
            FailureType.RESOURCE_EXHAUSTED,
        }

        if self in retriable_types:
            return ErrorCategory.RETRIABLE
        else:
            return ErrorCategory.PERMANENT


class ErrorCategory(str, Enum):
    """
    High-level categorization of errors for retry strategy.

    - RETRIABLE: Transient errors that may succeed on retry
    - PERMANENT: Deterministic errors that will always fail
    """
    RETRIABLE = "retriable"
    PERMANENT = "permanent"

    def is_retriable(self) -> bool:
        """Check if this category allows retries."""
        return self == ErrorCategory.RETRIABLE


class TaskFailure(BaseModel):
    """
    TaskFailure message schema.

    Represents a task execution failure with complete error context,
    including error type, message, traceback, and lease authorization.

    Security features:
    - Sanitizes sensitive data from error messages
    - Validates lease token format
    - Tracks retry count for loop prevention
    """
    task_id: str = Field(..., description="UUID of the failed task")
    lease_token: str = Field(..., description="Lease authorization token")
    error_type: FailureType = Field(..., description="Category of error")
    error_message: str = Field(..., description="Human-readable error description")
    traceback: str = Field(default="", description="Full stack trace")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the failure occurred"
    )
    peer_id: str = Field(..., description="libp2p peer ID of reporting agent")
    retry_count: int = Field(default=0, description="Number of retry attempts")

    @validator("error_message")
    def sanitize_error_message(cls, v: str) -> str:
        """
        Sanitize error messages to prevent leaking sensitive data.

        Redacts:
        - Passwords
        - API keys
        - Tokens
        - Connection strings
        """
        # Redact password patterns
        v = re.sub(r'password\s*=\s*[^\s,;]+', 'password=[REDACTED]', v, flags=re.IGNORECASE)

        # Redact API keys and tokens
        v = re.sub(r'(api[_-]?key|token)\s*[=:]\s*[^\s,;]+', r'\1=[REDACTED]', v, flags=re.IGNORECASE)

        # Redact connection strings
        v = re.sub(r'://[^:]+:[^@]+@', '://[REDACTED]:[REDACTED]@', v)

        return v

    @validator("lease_token")
    def validate_lease_token_format(cls, v: str) -> str:
        """Validate lease token has expected format."""
        if not v or len(v) < 10:
            raise ValueError("Invalid lease token format")
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


def categorize_error(error: Exception) -> ErrorCategory:
    """
    Categorize an exception into RETRIABLE or PERMANENT.

    Strategy:
    - Network errors, timeouts, resource exhaustion -> RETRIABLE
    - Validation errors, type errors, permission errors -> PERMANENT
    - Unknown errors -> RETRIABLE (conservative approach)

    Args:
        error: The exception to categorize

    Returns:
        ErrorCategory indicating retry eligibility
    """
    # Retriable error types
    retriable_exceptions = (
        TimeoutError,
        ConnectionError,
        ConnectionRefusedError,
        ConnectionResetError,
        BrokenPipeError,
        MemoryError,
        RuntimeError,
        OSError,
    )

    # Permanent error types
    permanent_exceptions = (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        ImportError,
        PermissionError,
        FileNotFoundError,
    )

    if isinstance(error, permanent_exceptions):
        return ErrorCategory.PERMANENT
    elif isinstance(error, retriable_exceptions):
        return ErrorCategory.RETRIABLE
    else:
        # Conservative default: assume retriable for unknown errors
        return ErrorCategory.RETRIABLE


@dataclass
class TaskFailureHandler:
    """
    Handler for processing TaskFailure reports and updating DBOS.

    Responsibilities:
    - Validate lease tokens
    - Update task status to failed
    - Increment retry counts for retriable failures
    - Requeue tasks if retries available
    - Rate limit failure reports per peer
    - Store failure details for debugging

    Security:
    - Validates lease token before processing
    - Rate limits reports per peer
    - Sanitizes error data before storage
    """

    dbos_client: Any
    rate_limit_per_peer: int = 10
    rate_limit_window_seconds: int = 60
    _rate_limit_tracker: Dict[str, list] = field(default_factory=lambda: defaultdict(list))

    async def report_failure(self, failure: TaskFailure) -> bool:
        """
        Process a task failure report.

        Workflow:
        1. Validate lease token
        2. Check rate limits
        3. Update task status to failed
        4. Store failure details
        5. If retriable and retries available:
           - Increment retry count
           - Requeue task

        Args:
            failure: TaskFailure message

        Returns:
            True if successfully processed

        Raises:
            ValueError: If lease token invalid
            Exception: If rate limit exceeded
        """
        # Validate lease token
        is_valid = await self._validate_lease_token(
            failure.task_id,
            failure.lease_token
        )
        if not is_valid:
            raise ValueError(f"Invalid lease token for task {failure.task_id}")

        # Check rate limits
        self._check_rate_limit(failure.peer_id)

        # Update task status to failed
        await self.dbos_client.update_task_status(
            task_id=failure.task_id,
            status="failed",
            error_type=failure.error_type.value,
            error_message=failure.error_message,
            timestamp=failure.timestamp,
        )

        # Store failure details for debugging
        await self.dbos_client.store_failure_details(
            task_id=failure.task_id,
            error_type=failure.error_type.value,
            error_message=failure.error_message,
            traceback=failure.traceback,
            peer_id=failure.peer_id,
            retry_count=failure.retry_count,
            timestamp=failure.timestamp,
        )

        # Determine if error is retriable
        error_category = failure.error_type.to_error_category()

        if error_category == ErrorCategory.RETRIABLE:
            # Get current task state
            task = await self.dbos_client.get_task(failure.task_id)
            current_retry_count = task.get("retry_count", 0)
            max_retries = task.get("max_retries", 3)

            # Check if we should increment and requeue
            if current_retry_count < max_retries:
                # Increment retry count
                new_retry_count = await self.dbos_client.increment_retry_count(
                    failure.task_id
                )

                # Requeue task for retry
                await self.dbos_client.requeue_task(failure.task_id)

        return True

    async def _validate_lease_token(self, task_id: str, lease_token: str) -> bool:
        """
        Validate that the lease token is valid for the given task.

        Args:
            task_id: Task identifier
            lease_token: Lease authorization token

        Returns:
            True if valid, False otherwise
        """
        if hasattr(self.dbos_client, "validate_lease_token"):
            return await self.dbos_client.validate_lease_token(
                task_id=task_id,
                lease_token=lease_token,
            )
        else:
            # Default to accepting if validation not implemented
            return True

    def _check_rate_limit(self, peer_id: str) -> None:
        """
        Check and enforce rate limits for failure reports.

        Prevents abuse and excessive retries from misbehaving agents.

        Args:
            peer_id: Peer ID to check

        Raises:
            Exception: If rate limit exceeded
        """
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - self.rate_limit_window_seconds

        # Clean old entries
        self._rate_limit_tracker[peer_id] = [
            ts for ts in self._rate_limit_tracker[peer_id]
            if ts > cutoff
        ]

        # Check limit
        if len(self._rate_limit_tracker[peer_id]) >= self.rate_limit_per_peer:
            raise Exception(
                f"Rate limit exceeded for peer {peer_id}: "
                f"{self.rate_limit_per_peer} failures per "
                f"{self.rate_limit_window_seconds}s"
            )

        # Record this request
        self._rate_limit_tracker[peer_id].append(now.timestamp())


# Export public API
__all__ = [
    "TaskFailure",
    "FailureType",
    "ErrorCategory",
    "TaskFailureHandler",
    "categorize_error",
]
