"""
Integration tests for TaskResult protocol.

This module tests the TaskResult submission protocol including
result submission, token validation, and task status updates.

Refs #30
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4


@pytest.mark.asyncio
async def test_submit_task_result_success():
    """
    Given completed task
    When submitting result
    Then should update task status = completed
    """
    from backend.p2p.protocols.task_result import (
        TaskResultProtocol,
        TaskResultMessage,
        TaskResultResponse,
        TaskStatus
    )

    # Given: A completed task with valid lease
    task_id = str(uuid4())
    peer_id = "12D3KooWEyopopk..."
    lease_token = "valid_lease_token_123"

    result_message = TaskResultMessage(
        task_id=task_id,
        peer_id=peer_id,
        lease_token=lease_token,
        status=TaskStatus.COMPLETED,
        output={
            "result": "Task completed successfully",
            "data": {"key": "value"}
        },
        execution_metadata={
            "duration_seconds": 125.5,
            "cpu_percent": 45.2,
            "memory_mb": 512,
            "gpu_utilization": 80.5
        },
        timestamp=datetime.now(timezone.utc),
        signature="base64_signature_here"
    )

    # When: Submitting result
    protocol = TaskResultProtocol()
    response = await protocol.submit_result(result_message)

    # Then: Should update task status to completed
    assert response.accepted is True
    assert response.task_id == task_id
    assert response.status == TaskStatus.COMPLETED
    assert response.error is None


@pytest.mark.asyncio
async def test_reject_result_invalid_token():
    """
    Given expired lease token
    When submitting result
    Then should reject with token error
    """
    from backend.p2p.protocols.task_result import (
        TaskResultProtocol,
        TaskResultMessage,
        TaskResultResponse,
        TaskStatus,
        TokenValidationError
    )

    # Given: A task result with expired lease token
    task_id = str(uuid4())
    peer_id = "12D3KooWEyopopk..."
    expired_token = "expired_lease_token"

    result_message = TaskResultMessage(
        task_id=task_id,
        peer_id=peer_id,
        lease_token=expired_token,
        status=TaskStatus.COMPLETED,
        output={"result": "Task completed"},
        execution_metadata={"duration_seconds": 100.0},
        timestamp=datetime.now(timezone.utc),
        signature="signature"
    )

    # When: Submitting result with expired token
    protocol = TaskResultProtocol()

    # Mock expired token validation
    with patch.object(protocol, 'validate_lease_token', side_effect=TokenValidationError("Token expired")):
        response = await protocol.submit_result(result_message)

    # Then: Should reject with token error
    assert response.accepted is False
    assert "token" in response.error.lower() or "expired" in response.error.lower()


@pytest.mark.asyncio
async def test_reject_result_wrong_peer():
    """
    Given result from non-owner peer
    When submitting result
    Then should reject with authorization error
    """
    from backend.p2p.protocols.task_result import (
        TaskResultProtocol,
        TaskResultMessage,
        TaskResultResponse,
        TaskStatus,
        AuthorizationError
    )

    # Given: A task result from wrong peer
    task_id = str(uuid4())
    wrong_peer_id = "12D3KooWWrongPeer"
    lease_token = "valid_token_for_different_peer"

    result_message = TaskResultMessage(
        task_id=task_id,
        peer_id=wrong_peer_id,
        lease_token=lease_token,
        status=TaskStatus.COMPLETED,
        output={"result": "Task completed"},
        execution_metadata={"duration_seconds": 100.0},
        timestamp=datetime.now(timezone.utc),
        signature="signature"
    )

    # When: Submitting result from wrong peer
    protocol = TaskResultProtocol()

    # Mock authorization check
    with patch.object(protocol, 'validate_lease_ownership', side_effect=AuthorizationError("Peer not authorized")):
        response = await protocol.submit_result(result_message)

    # Then: Should reject with authorization error
    assert response.accepted is False
    assert "authorization" in response.error.lower() or "authorized" in response.error.lower()


@pytest.mark.asyncio
async def test_submit_task_result_with_failure_status():
    """
    Given failed task
    When submitting failure result
    Then should update task status = failed
    """
    from backend.p2p.protocols.task_result import (
        TaskResultProtocol,
        TaskResultMessage,
        TaskResultResponse,
        TaskStatus
    )

    # Given: A failed task with valid lease
    task_id = str(uuid4())
    peer_id = "12D3KooWEyopopk..."
    lease_token = "valid_lease_token_456"

    result_message = TaskResultMessage(
        task_id=task_id,
        peer_id=peer_id,
        lease_token=lease_token,
        status=TaskStatus.FAILED,
        output={"error": "Task execution failed"},
        execution_metadata={
            "duration_seconds": 50.0,
            "cpu_percent": 30.0,
            "memory_mb": 256
        },
        error_message="RuntimeError: Out of memory",
        timestamp=datetime.now(timezone.utc),
        signature="signature"
    )

    # When: Submitting failure result
    protocol = TaskResultProtocol()
    response = await protocol.submit_result(result_message)

    # Then: Should update task status to failed
    assert response.accepted is True
    assert response.task_id == task_id
    assert response.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_validate_signature_on_submission():
    """
    Given task result with invalid signature
    When submitting result
    Then should reject with signature error
    """
    from backend.p2p.protocols.task_result import (
        TaskResultProtocol,
        TaskResultMessage,
        TaskResultResponse,
        TaskStatus,
        SignatureValidationError
    )

    # Given: A task result with invalid signature
    task_id = str(uuid4())
    peer_id = "12D3KooWEyopopk..."
    lease_token = "valid_lease_token"

    result_message = TaskResultMessage(
        task_id=task_id,
        peer_id=peer_id,
        lease_token=lease_token,
        status=TaskStatus.COMPLETED,
        output={"result": "Task completed"},
        execution_metadata={"duration_seconds": 100.0},
        timestamp=datetime.now(timezone.utc),
        signature="invalid_signature"
    )

    # When: Submitting result with invalid signature
    protocol = TaskResultProtocol()

    # Mock signature validation failure
    with patch.object(protocol, 'verify_signature', side_effect=SignatureValidationError("Invalid signature")):
        response = await protocol.submit_result(result_message)

    # Then: Should reject with signature error
    assert response.accepted is False
    assert "signature" in response.error.lower()


@pytest.mark.asyncio
async def test_prevent_duplicate_result_submission():
    """
    Given task result already submitted
    When submitting duplicate result
    Then should reject with duplicate error
    """
    from backend.p2p.protocols.task_result import (
        TaskResultProtocol,
        TaskResultMessage,
        TaskResultResponse,
        TaskStatus
    )

    # Given: A task result that was already submitted
    task_id = str(uuid4())
    peer_id = "12D3KooWEyopopk..."
    lease_token = "valid_lease_token"

    result_message = TaskResultMessage(
        task_id=task_id,
        peer_id=peer_id,
        lease_token=lease_token,
        status=TaskStatus.COMPLETED,
        output={"result": "Task completed"},
        execution_metadata={"duration_seconds": 100.0},
        timestamp=datetime.now(timezone.utc),
        signature="signature"
    )

    # When: Submitting result twice
    protocol = TaskResultProtocol()
    first_response = await protocol.submit_result(result_message)
    second_response = await protocol.submit_result(result_message)

    # Then: First submission succeeds, second rejected as duplicate
    assert first_response.accepted is True
    assert second_response.accepted is False
    assert "duplicate" in second_response.error.lower() or "already" in second_response.error.lower()


@pytest.mark.asyncio
async def test_update_dbos_task_status():
    """
    Given valid task result
    When submitting result
    Then should update DBOS task entity
    """
    from backend.p2p.protocols.task_result import (
        TaskResultProtocol,
        TaskResultMessage,
        TaskStatus
    )

    # Given: A valid task result
    task_id = str(uuid4())
    peer_id = "12D3KooWEyopopk..."
    lease_token = "valid_lease_token"

    result_message = TaskResultMessage(
        task_id=task_id,
        peer_id=peer_id,
        lease_token=lease_token,
        status=TaskStatus.COMPLETED,
        output={"result": "Task completed"},
        execution_metadata={"duration_seconds": 100.0},
        timestamp=datetime.now(timezone.utc),
        signature="signature"
    )

    # When: Submitting result
    protocol = TaskResultProtocol()

    with patch.object(protocol, 'update_task_in_dbos') as mock_update:
        response = await protocol.submit_result(result_message)

    # Then: Should call DBOS update
    assert mock_update.called
    mock_update.assert_called_once()

    # Verify update parameters
    call_args = mock_update.call_args
    assert call_args[0][0] == task_id  # task_id
    assert call_args[0][1] == TaskStatus.COMPLETED  # status


@pytest.mark.asyncio
async def test_validate_execution_metadata():
    """
    Given task result with execution metadata
    When validating metadata
    Then should accept valid metadata format
    """
    from backend.p2p.protocols.task_result import (
        TaskResultProtocol,
        TaskResultMessage,
        TaskStatus
    )

    # Given: A task result with comprehensive metadata
    task_id = str(uuid4())
    peer_id = "12D3KooWEyopopk..."
    lease_token = "valid_lease_token"

    result_message = TaskResultMessage(
        task_id=task_id,
        peer_id=peer_id,
        lease_token=lease_token,
        status=TaskStatus.COMPLETED,
        output={"result": "Task completed"},
        execution_metadata={
            "duration_seconds": 125.5,
            "cpu_percent": 45.2,
            "memory_mb": 512,
            "gpu_utilization": 80.5,
            "network_bytes_sent": 1024,
            "network_bytes_received": 2048,
            "started_at": "2026-02-19T12:00:00Z",
            "completed_at": "2026-02-19T12:02:05Z"
        },
        timestamp=datetime.now(timezone.utc),
        signature="signature"
    )

    # When: Validating metadata
    protocol = TaskResultProtocol()
    is_valid = protocol.validate_execution_metadata(result_message.execution_metadata)

    # Then: Should accept valid metadata
    assert is_valid is True


@pytest.mark.asyncio
async def test_late_result_rejection_after_lease_expiry():
    """
    Given task lease expired
    When submitting late result
    Then should reject with lease expired error
    """
    from backend.p2p.protocols.task_result import (
        TaskResultProtocol,
        TaskResultMessage,
        TaskResultResponse,
        TaskStatus,
        LeaseExpiredError
    )

    # Given: A task result submitted after lease expiration
    task_id = str(uuid4())
    peer_id = "12D3KooWEyopopk..."
    expired_token = "expired_lease_token"

    # Result with timestamp after lease expiration
    result_message = TaskResultMessage(
        task_id=task_id,
        peer_id=peer_id,
        lease_token=expired_token,
        status=TaskStatus.COMPLETED,
        output={"result": "Late result"},
        execution_metadata={"duration_seconds": 1000.0},
        timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
        signature="signature"
    )

    # When: Submitting late result
    protocol = TaskResultProtocol()

    # Mock lease expiration check
    with patch.object(protocol, 'check_lease_validity', side_effect=LeaseExpiredError("Lease expired")):
        response = await protocol.submit_result(result_message)

    # Then: Should reject as lease expired
    assert response.accepted is False
    assert "lease" in response.error.lower() and "expired" in response.error.lower()


@pytest.mark.asyncio
async def test_result_idempotency_key():
    """
    Given task result with idempotency key
    When submitting result
    Then should use idempotency key for deduplication
    """
    from backend.p2p.protocols.task_result import (
        TaskResultProtocol,
        TaskResultMessage,
        TaskStatus
    )

    # Given: A task result with idempotency key
    task_id = str(uuid4())
    idempotency_key = f"{task_id}_result_submission"
    peer_id = "12D3KooWEyopopk..."
    lease_token = "valid_lease_token"

    result_message = TaskResultMessage(
        task_id=task_id,
        peer_id=peer_id,
        lease_token=lease_token,
        status=TaskStatus.COMPLETED,
        output={"result": "Task completed"},
        execution_metadata={"duration_seconds": 100.0},
        timestamp=datetime.now(timezone.utc),
        signature="signature",
        idempotency_key=idempotency_key
    )

    # When: Checking idempotency
    protocol = TaskResultProtocol()

    # First submission
    first_check = await protocol.check_idempotency(idempotency_key)
    assert first_check is False  # Not duplicate

    await protocol.record_idempotency(idempotency_key)

    # Second submission
    second_check = await protocol.check_idempotency(idempotency_key)

    # Then: Should detect duplicate
    assert second_check is True  # Is duplicate


# Fixtures for test setup
@pytest.fixture
async def mock_dbos_client():
    """
    Provides a mock DBOS client for testing.
    """
    mock_client = AsyncMock()
    yield mock_client


@pytest.fixture
async def task_result_protocol():
    """
    Provides a configured TaskResultProtocol for testing.
    """
    from backend.p2p.protocols.task_result import TaskResultProtocol

    protocol = TaskResultProtocol()
    yield protocol

    # Cleanup
    await protocol.close()


@pytest.fixture
def valid_task_result_message():
    """
    Provides a valid TaskResultMessage for testing.
    """
    from backend.p2p.protocols.task_result import TaskResultMessage, TaskStatus

    return TaskResultMessage(
        task_id=str(uuid4()),
        peer_id="12D3KooWEyopopk...",
        lease_token="valid_lease_token",
        status=TaskStatus.COMPLETED,
        output={"result": "Task completed successfully"},
        execution_metadata={
            "duration_seconds": 125.5,
            "cpu_percent": 45.2,
            "memory_mb": 512
        },
        timestamp=datetime.now(timezone.utc),
        signature="base64_signature"
    )
