"""
Tests for TaskFailure protocol implementation.

This module tests the TaskFailure message schema, error categorization,
and failure reporting handler following BDD-style testing methodology.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from backend.p2p.protocols.task_failure import (
    TaskFailure,
    FailureType,
    ErrorCategory,
    TaskFailureHandler,
    categorize_error,
)


class TestTaskFailureSchema:
    """Test TaskFailure message schema validation."""

    def test_task_failure_creation_with_all_fields(self):
        """Given complete failure data, when creating TaskFailure,
        then should validate all required fields."""

        task_id = str(uuid4())
        lease_token = f"lease_{uuid4()}"
        error_type = FailureType.RUNTIME_ERROR
        error_message = "Division by zero in calculation"
        traceback = "Traceback:\n  File 'main.py', line 42\n    result = x / y"
        timestamp = datetime.now(timezone.utc)

        failure = TaskFailure(
            task_id=task_id,
            lease_token=lease_token,
            error_type=error_type,
            error_message=error_message,
            traceback=traceback,
            timestamp=timestamp,
            peer_id="12D3KooWEyopopk...",
            retry_count=1,
        )

        assert failure.task_id == task_id
        assert failure.lease_token == lease_token
        assert failure.error_type == error_type
        assert failure.error_message == error_message
        assert failure.traceback == traceback
        assert failure.timestamp == timestamp
        assert failure.peer_id == "12D3KooWEyopopk..."
        assert failure.retry_count == 1

    def test_task_failure_sanitizes_sensitive_data(self):
        """Given error message with sensitive data, when creating TaskFailure,
        then should sanitize secrets and PII."""

        sensitive_message = "Failed to connect to db with password=secret123"

        failure = TaskFailure(
            task_id=str(uuid4()),
            lease_token=f"lease_{uuid4()}",
            error_type=FailureType.RUNTIME_ERROR,
            error_message=sensitive_message,
            traceback="",
            timestamp=datetime.now(timezone.utc),
            peer_id="12D3KooWTest",
            retry_count=0,
        )

        # Should redact sensitive information
        assert "secret123" not in failure.error_message
        assert "password=" in failure.error_message or "[REDACTED]" in failure.error_message

    def test_task_failure_defaults(self):
        """Given minimal required fields, when creating TaskFailure,
        then should apply sensible defaults."""

        failure = TaskFailure(
            task_id=str(uuid4()),
            lease_token=f"lease_{uuid4()}",
            error_type=FailureType.RUNTIME_ERROR,
            error_message="Test error",
            traceback="",
            timestamp=datetime.now(timezone.utc),
            peer_id="12D3KooWTest",
        )

        assert failure.retry_count == 0
        assert failure.timestamp is not None
        assert isinstance(failure.timestamp, datetime)


class TestErrorCategorization:
    """Test error categorization logic (retriable vs permanent)."""

    def test_categorize_timeout_as_retriable(self):
        """Given timeout error, when categorizing,
        then should classify as RETRIABLE."""

        error = TimeoutError("Operation timed out after 30s")
        category = categorize_error(error)

        assert category == ErrorCategory.RETRIABLE
        assert category.is_retriable() is True

    def test_categorize_connection_error_as_retriable(self):
        """Given connection error, when categorizing,
        then should classify as RETRIABLE."""

        error = ConnectionError("Failed to connect to peer")
        category = categorize_error(error)

        assert category == ErrorCategory.RETRIABLE
        assert category.is_retriable() is True

    def test_categorize_value_error_as_permanent(self):
        """Given value error, when categorizing,
        then should classify as PERMANENT."""

        error = ValueError("Invalid input parameters")
        category = categorize_error(error)

        assert category == ErrorCategory.PERMANENT
        assert category.is_retriable() is False

    def test_categorize_type_error_as_permanent(self):
        """Given type error, when categorizing,
        then should classify as PERMANENT."""

        error = TypeError("Expected string, got int")
        category = categorize_error(error)

        assert category == ErrorCategory.PERMANENT
        assert category.is_retriable() is False

    def test_categorize_runtime_error_as_retriable(self):
        """Given generic runtime error, when categorizing,
        then should classify as RETRIABLE (conservative)."""

        error = RuntimeError("Unexpected runtime error")
        category = categorize_error(error)

        assert category == ErrorCategory.RETRIABLE
        assert category.is_retriable() is True

    def test_categorize_resource_exhausted_as_retriable(self):
        """Given resource exhaustion error, when categorizing,
        then should classify as RETRIABLE."""

        error = MemoryError("Out of memory")
        category = categorize_error(error)

        assert category == ErrorCategory.RETRIABLE
        assert category.is_retriable() is True

    def test_categorize_permission_denied_as_permanent(self):
        """Given permission error, when categorizing,
        then should classify as PERMANENT."""

        error = PermissionError("Access denied to resource")
        category = categorize_error(error)

        assert category == ErrorCategory.PERMANENT
        assert category.is_retriable() is False


class TestTaskFailureHandler:
    """Test TaskFailure reporting handler and DBOS integration."""

    @pytest.mark.asyncio
    async def test_report_task_failure_updates_status(self):
        """Given task error, when reporting failure,
        then should update task status = failed in DBOS."""

        task_id = str(uuid4())
        lease_token = f"lease_{uuid4()}"

        # Mock DBOS client
        mock_dbos = AsyncMock()
        mock_dbos.update_task_status = AsyncMock(return_value=True)
        mock_dbos.store_failure_details = AsyncMock(return_value=True)
        mock_dbos.get_task = AsyncMock(return_value={
            "task_id": task_id,
            "retry_count": 0,
            "max_retries": 3,
        })
        mock_dbos.increment_retry_count = AsyncMock(return_value=1)
        mock_dbos.requeue_task = AsyncMock(return_value=True)

        handler = TaskFailureHandler(dbos_client=mock_dbos)

        failure = TaskFailure(
            task_id=task_id,
            lease_token=lease_token,
            error_type=FailureType.RUNTIME_ERROR,
            error_message="Test failure",
            traceback="",
            timestamp=datetime.now(timezone.utc),
            peer_id="12D3KooWTest",
            retry_count=0,
        )

        result = await handler.report_failure(failure)

        assert result is True
        mock_dbos.update_task_status.assert_called_once()
        call_args = mock_dbos.update_task_status.call_args
        assert call_args[1]["task_id"] == task_id
        assert call_args[1]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_increment_retry_count_for_retriable_failure(self):
        """Given retriable failure, when processing,
        then should increment task.retry_count."""

        task_id = str(uuid4())
        lease_token = f"lease_{uuid4()}"

        mock_dbos = AsyncMock()
        mock_dbos.update_task_status = AsyncMock(return_value=True)
        mock_dbos.increment_retry_count = AsyncMock(return_value=2)
        mock_dbos.get_task = AsyncMock(return_value={
            "task_id": task_id,
            "retry_count": 1,
            "max_retries": 3,
        })

        handler = TaskFailureHandler(dbos_client=mock_dbos)

        failure = TaskFailure(
            task_id=task_id,
            lease_token=lease_token,
            error_type=FailureType.TIMEOUT,
            error_message="Operation timed out",
            traceback="",
            timestamp=datetime.now(timezone.utc),
            peer_id="12D3KooWTest",
            retry_count=1,
        )

        result = await handler.report_failure(failure)

        assert result is True
        mock_dbos.increment_retry_count.assert_called_once_with(task_id)

    @pytest.mark.asyncio
    async def test_requeue_task_if_retries_available(self):
        """Given retriable failure with retries remaining, when reporting,
        then should requeue task for retry."""

        task_id = str(uuid4())
        lease_token = f"lease_{uuid4()}"

        mock_dbos = AsyncMock()
        mock_dbos.update_task_status = AsyncMock(return_value=True)
        mock_dbos.increment_retry_count = AsyncMock(return_value=2)
        mock_dbos.requeue_task = AsyncMock(return_value=True)
        mock_dbos.get_task = AsyncMock(return_value={
            "task_id": task_id,
            "retry_count": 1,
            "max_retries": 3,
        })

        handler = TaskFailureHandler(dbos_client=mock_dbos)

        failure = TaskFailure(
            task_id=task_id,
            lease_token=lease_token,
            error_type=FailureType.CONNECTION_ERROR,
            error_message="Failed to connect",
            traceback="",
            timestamp=datetime.now(timezone.utc),
            peer_id="12D3KooWTest",
            retry_count=1,
        )

        result = await handler.report_failure(failure)

        assert result is True
        mock_dbos.requeue_task.assert_called_once_with(task_id)

    @pytest.mark.asyncio
    async def test_no_requeue_if_max_retries_exceeded(self):
        """Given retriable failure with no retries remaining, when reporting,
        then should NOT requeue task."""

        task_id = str(uuid4())
        lease_token = f"lease_{uuid4()}"

        mock_dbos = AsyncMock()
        mock_dbos.update_task_status = AsyncMock(return_value=True)
        mock_dbos.store_failure_details = AsyncMock(return_value=True)
        mock_dbos.increment_retry_count = AsyncMock(return_value=4)
        mock_dbos.requeue_task = AsyncMock(return_value=True)
        mock_dbos.get_task = AsyncMock(return_value={
            "task_id": task_id,
            "retry_count": 3,
            "max_retries": 3,
        })

        handler = TaskFailureHandler(dbos_client=mock_dbos)

        failure = TaskFailure(
            task_id=task_id,
            lease_token=lease_token,
            error_type=FailureType.TIMEOUT,
            error_message="Operation timed out",
            traceback="",
            timestamp=datetime.now(timezone.utc),
            peer_id="12D3KooWTest",
            retry_count=3,
        )

        result = await handler.report_failure(failure)

        assert result is True
        mock_dbos.requeue_task.assert_not_called()
        # Should not increment retry count when at max
        mock_dbos.increment_retry_count.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_requeue_for_permanent_failure(self):
        """Given permanent failure, when reporting,
        then should NOT requeue task regardless of retry count."""

        task_id = str(uuid4())
        lease_token = f"lease_{uuid4()}"

        mock_dbos = AsyncMock()
        mock_dbos.update_task_status = AsyncMock(return_value=True)
        mock_dbos.store_failure_details = AsyncMock(return_value=True)
        mock_dbos.increment_retry_count = AsyncMock(return_value=1)
        mock_dbos.requeue_task = AsyncMock(return_value=True)
        mock_dbos.get_task = AsyncMock(return_value={
            "task_id": task_id,
            "retry_count": 0,
            "max_retries": 3,
        })

        handler = TaskFailureHandler(dbos_client=mock_dbos)

        failure = TaskFailure(
            task_id=task_id,
            lease_token=lease_token,
            error_type=FailureType.VALIDATION_ERROR,
            error_message="Invalid input parameters",
            traceback="",
            timestamp=datetime.now(timezone.utc),
            peer_id="12D3KooWTest",
            retry_count=0,
        )

        result = await handler.report_failure(failure)

        assert result is True
        mock_dbos.update_task_status.assert_called_once()
        # Should not increment retry count or requeue for permanent failures
        mock_dbos.increment_retry_count.assert_not_called()
        mock_dbos.requeue_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_lease_token_before_processing(self):
        """Given failure report, when validating,
        then should verify lease token is valid."""

        task_id = str(uuid4())
        invalid_lease_token = "invalid_token"

        mock_dbos = AsyncMock()
        mock_dbos.validate_lease_token = AsyncMock(return_value=False)

        handler = TaskFailureHandler(dbos_client=mock_dbos)

        failure = TaskFailure(
            task_id=task_id,
            lease_token=invalid_lease_token,
            error_type=FailureType.RUNTIME_ERROR,
            error_message="Test error",
            traceback="",
            timestamp=datetime.now(timezone.utc),
            peer_id="12D3KooWTest",
            retry_count=0,
        )

        with pytest.raises(ValueError, match="Invalid lease token"):
            await handler.report_failure(failure)

    @pytest.mark.asyncio
    async def test_rate_limit_failure_reports(self):
        """Given multiple failure reports from same peer, when rate limiting,
        then should throttle excessive reports."""

        task_id = str(uuid4())
        lease_token = f"lease_{uuid4()}"
        peer_id = "12D3KooWTest"

        mock_dbos = AsyncMock()
        mock_dbos.update_task_status = AsyncMock(return_value=True)
        mock_dbos.store_failure_details = AsyncMock(return_value=True)
        mock_dbos.validate_lease_token = AsyncMock(return_value=True)
        mock_dbos.get_task = AsyncMock(return_value={
            "task_id": task_id,
            "retry_count": 0,
            "max_retries": 3,
        })
        mock_dbos.increment_retry_count = AsyncMock(return_value=1)
        mock_dbos.requeue_task = AsyncMock(return_value=True)

        handler = TaskFailureHandler(
            dbos_client=mock_dbos,
            rate_limit_per_peer=3,
            rate_limit_window_seconds=60,
        )

        failure = TaskFailure(
            task_id=task_id,
            lease_token=lease_token,
            error_type=FailureType.RUNTIME_ERROR,
            error_message="Test error",
            traceback="",
            timestamp=datetime.now(timezone.utc),
            peer_id=peer_id,
            retry_count=0,
        )

        # First 3 reports should succeed
        for _ in range(3):
            result = await handler.report_failure(failure)
            assert result is True

        # 4th report should be rate limited
        with pytest.raises(Exception, match="Rate limit exceeded"):
            await handler.report_failure(failure)

    @pytest.mark.asyncio
    async def test_store_failure_details_in_dbos(self):
        """Given failure report, when storing,
        then should persist error details to DBOS."""

        task_id = str(uuid4())
        lease_token = f"lease_{uuid4()}"
        error_message = "Detailed error message"
        traceback = "Full traceback information"

        mock_dbos = AsyncMock()
        mock_dbos.update_task_status = AsyncMock(return_value=True)
        mock_dbos.store_failure_details = AsyncMock(return_value=True)
        mock_dbos.get_task = AsyncMock(return_value={
            "task_id": task_id,
            "retry_count": 0,
            "max_retries": 3,
        })
        mock_dbos.increment_retry_count = AsyncMock(return_value=1)
        mock_dbos.requeue_task = AsyncMock(return_value=True)

        handler = TaskFailureHandler(dbos_client=mock_dbos)

        failure = TaskFailure(
            task_id=task_id,
            lease_token=lease_token,
            error_type=FailureType.RUNTIME_ERROR,
            error_message=error_message,
            traceback=traceback,
            timestamp=datetime.now(timezone.utc),
            peer_id="12D3KooWTest",
            retry_count=0,
        )

        result = await handler.report_failure(failure)

        assert result is True
        mock_dbos.store_failure_details.assert_called_once()
        call_args = mock_dbos.store_failure_details.call_args
        assert call_args[1]["task_id"] == task_id
        assert call_args[1]["error_message"] == error_message
        assert call_args[1]["traceback"] == traceback


class TestFailureTypeEnum:
    """Test FailureType enumeration."""

    def test_failure_type_values(self):
        """Given FailureType enum, when checking values,
        then should have all expected error types."""

        assert hasattr(FailureType, "RUNTIME_ERROR")
        assert hasattr(FailureType, "TIMEOUT")
        assert hasattr(FailureType, "CONNECTION_ERROR")
        assert hasattr(FailureType, "VALIDATION_ERROR")
        assert hasattr(FailureType, "RESOURCE_EXHAUSTED")
        assert hasattr(FailureType, "PERMISSION_DENIED")

    def test_failure_type_to_error_category_mapping(self):
        """Given FailureType, when mapping to ErrorCategory,
        then should return correct category."""

        assert FailureType.TIMEOUT.to_error_category() == ErrorCategory.RETRIABLE
        assert FailureType.CONNECTION_ERROR.to_error_category() == ErrorCategory.RETRIABLE
        assert FailureType.VALIDATION_ERROR.to_error_category() == ErrorCategory.PERMANENT
        assert FailureType.PERMISSION_DENIED.to_error_category() == ErrorCategory.PERMANENT


class TestErrorCategoryEnum:
    """Test ErrorCategory enumeration."""

    def test_error_category_values(self):
        """Given ErrorCategory enum, when checking values,
        then should have RETRIABLE and PERMANENT."""

        assert hasattr(ErrorCategory, "RETRIABLE")
        assert hasattr(ErrorCategory, "PERMANENT")

    def test_error_category_is_retriable_method(self):
        """Given ErrorCategory, when checking retriability,
        then should return correct boolean."""

        assert ErrorCategory.RETRIABLE.is_retriable() is True
        assert ErrorCategory.PERMANENT.is_retriable() is False
