"""
Integration tests for DBOS Reconnection and Reconciliation (E6-S5).

This module tests the DBOS reconciliation service including:
- Reconnection detection after partition heals
- Exit from degraded mode
- Buffered result flushing with token validation
- Expired result discarding
- Normal operation resumption

Refs E6-S5 (DBOS Reconnection and Reconciliation)
Story Points: 5
Coverage Target: >= 80%
"""

import pytest
import asyncio
import httpx
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID

from backend.services.dbos_reconciliation_service import (
    DBOSReconciliationService,
    ReconciliationState,
    BufferedResult,
)
from backend.services.lease_validation_service import (
    LeaseValidationService,
    LeaseExpiredError,
    LeaseNotFoundError,
)
from backend.schemas.task_schemas import TaskLease, TaskResult, TaskStatus


@pytest.fixture
def lease_validation_service():
    """Create LeaseValidationService instance for testing"""
    return LeaseValidationService()


@pytest.fixture
def reconciliation_service(lease_validation_service):
    """Create DBOSReconciliationService instance for testing"""
    return DBOSReconciliationService(
        dbos_gateway_url="http://localhost:8080",
        lease_validator=lease_validation_service,
    )


@pytest.fixture
def valid_lease_token():
    """Generate valid lease token for testing"""
    return f"valid_token_{uuid4()}"


@pytest.fixture
def expired_lease_token():
    """Generate expired lease token for testing"""
    return f"expired_token_{uuid4()}"


@pytest.fixture
def valid_task_lease(valid_lease_token):
    """Create valid task lease for testing"""
    task_id = uuid4()
    now = datetime.now(timezone.utc)

    return TaskLease(
        task_id=task_id,
        lease_owner_peer_id="QmValidPeer123",
        lease_token=valid_lease_token,
        granted_at=now - timedelta(minutes=5),
        lease_expires_at=now + timedelta(minutes=5),  # Still valid
        heartbeat_interval=30,
    )


@pytest.fixture
def expired_task_lease(expired_lease_token):
    """Create expired task lease for testing"""
    task_id = uuid4()
    now = datetime.now(timezone.utc)

    return TaskLease(
        task_id=task_id,
        lease_owner_peer_id="QmExpiredPeer456",
        lease_token=expired_lease_token,
        granted_at=now - timedelta(minutes=20),
        lease_expires_at=now - timedelta(minutes=5),  # Expired 5 minutes ago
        heartbeat_interval=30,
    )


@pytest.fixture
def buffered_results(valid_task_lease, expired_task_lease):
    """Create list of buffered results for testing"""
    now = datetime.now(timezone.utc)

    results = []

    # Create 8 valid buffered results - all using the same valid task_lease
    for i in range(8):
        result = BufferedResult(
            task_id=valid_task_lease.task_id,  # Use same task_id from lease
            peer_id=valid_task_lease.lease_owner_peer_id,  # Use same peer_id
            lease_token=valid_task_lease.lease_token,
            status=TaskStatus.COMPLETED,
            output_payload={"result": f"Task {i} completed"},
            execution_metadata={"duration_seconds": 120 + i},
            submitted_at=now - timedelta(minutes=10 - i),
            buffered_at=now - timedelta(minutes=10 - i),
        )
        results.append(result)

    # Create 2 expired buffered results - using expired lease
    for i in range(8, 10):
        result = BufferedResult(
            task_id=expired_task_lease.task_id,  # Use same task_id from expired lease
            peer_id=expired_task_lease.lease_owner_peer_id,  # Use same peer_id
            lease_token=expired_task_lease.lease_token,
            status=TaskStatus.COMPLETED,
            output_payload={"result": f"Task {i} completed"},
            execution_metadata={"duration_seconds": 120 + i},
            submitted_at=now - timedelta(minutes=20),
            buffered_at=now - timedelta(minutes=20),
        )
        results.append(result)

    return results


@pytest.mark.asyncio
async def test_reconnect_after_partition(reconciliation_service):
    """
    Given DBOS available again
    When detecting reconnection
    Then should exit degraded mode

    BDD Scenario: DBOS Reconnection Detection
    """
    # Given: Service is in degraded mode due to partition
    reconciliation_service.state = ReconciliationState.DEGRADED
    assert reconciliation_service.state == ReconciliationState.DEGRADED

    # Mock DBOS health check to return healthy
    with patch.object(
        reconciliation_service, "_check_dbos_health", return_value=True
    ):
        # When: Detecting DBOS availability
        reconnected = await reconciliation_service.detect_reconnection()

        # Then: Should exit degraded mode
        assert reconnected is True
        assert reconciliation_service.state == ReconciliationState.NORMAL
        assert reconciliation_service.last_reconnection_time is not None


@pytest.mark.asyncio
async def test_submit_buffered_results(
    reconciliation_service,
    lease_validation_service,
    buffered_results,
    valid_task_lease,
):
    """
    Given 10 buffered results
    When flushing buffer
    Then should submit all with valid tokens

    BDD Scenario: Buffered Result Submission
    """
    # Given: Service has 10 buffered results (8 valid, 2 expired)
    reconciliation_service.result_buffer = buffered_results.copy()

    # Register valid lease in validation service
    lease_validation_service.lease_store[valid_task_lease.lease_token] = (
        valid_task_lease
    )

    # Mock DBOS result submission
    submit_mock = AsyncMock(return_value={"success": True})
    with patch.object(
        reconciliation_service, "_submit_result_to_dbos", submit_mock
    ):
        # When: Flushing buffered results
        flush_summary = await reconciliation_service.flush_buffered_results()

        # Then: Should attempt to submit all 10 results
        assert flush_summary["total_buffered"] == 10
        # 8 valid submissions (all same task_id) + 2 expired (should be discarded)
        # Since all 8 valid results share the same task_id, they will all validate successfully
        assert flush_summary["submitted"] == 8
        assert flush_summary["discarded"] == 2  # 2 expired


@pytest.mark.asyncio
async def test_discard_expired_buffered_results(
    reconciliation_service,
    lease_validation_service,
    expired_task_lease,
):
    """
    Given buffered result with expired token
    Then should discard without submission

    BDD Scenario: Expired Result Discarding
    """
    # Given: A buffered result with expired lease token
    task_id = uuid4()
    now = datetime.now(timezone.utc)

    expired_result = BufferedResult(
        task_id=task_id,
        peer_id="QmExpiredPeer",
        lease_token=expired_task_lease.lease_token,
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Task completed"},
        execution_metadata={"duration_seconds": 100},
        submitted_at=now - timedelta(minutes=20),
        buffered_at=now - timedelta(minutes=20),
    )

    reconciliation_service.result_buffer = [expired_result]

    # Register expired lease in validation service
    lease_validation_service.lease_store[expired_task_lease.lease_token] = (
        expired_task_lease
    )

    # Mock DBOS submission (should not be called)
    submit_mock = AsyncMock(return_value={"success": True})
    with patch.object(
        reconciliation_service, "_submit_result_to_dbos", submit_mock
    ):
        # When: Flushing buffered results
        flush_summary = await reconciliation_service.flush_buffered_results()

        # Then: Should discard expired result without submission
        assert flush_summary["total_buffered"] == 1
        assert flush_summary["discarded"] == 1
        assert flush_summary["submitted"] == 0
        # Submission should not be called for expired results
        submit_mock.assert_not_called()


@pytest.mark.asyncio
async def test_enter_degraded_mode(reconciliation_service):
    """
    Given normal operation
    When DBOS partition detected
    Then should enter degraded mode

    BDD Scenario: Degraded Mode Entry
    """
    # Given: Service in normal state
    assert reconciliation_service.state == ReconciliationState.NORMAL

    # When: Entering degraded mode due to partition
    await reconciliation_service.enter_degraded_mode(
        reason="DBOS connection lost"
    )

    # Then: Should be in degraded mode
    assert reconciliation_service.state == ReconciliationState.DEGRADED
    assert reconciliation_service.degraded_reason == "DBOS connection lost"
    assert reconciliation_service.degraded_since is not None


@pytest.mark.asyncio
async def test_buffer_result_during_degraded_mode(reconciliation_service):
    """
    Given degraded mode active
    When task result ready
    Then should buffer result locally

    BDD Scenario: Result Buffering
    """
    # Given: Service in degraded mode
    reconciliation_service.state = ReconciliationState.DEGRADED

    # When: Buffering a task result
    task_id = uuid4()
    result = TaskResult(
        task_id=task_id,
        peer_id="QmTestPeer",
        lease_token="test_token_123",
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Success"},
        execution_metadata={"duration_seconds": 100},
        submitted_at=datetime.now(timezone.utc),
    )

    buffer_success = await reconciliation_service.buffer_result(result)

    # Then: Should buffer successfully
    assert buffer_success is True
    assert len(reconciliation_service.result_buffer) == 1
    buffered = reconciliation_service.result_buffer[0]
    assert buffered.task_id == task_id
    assert buffered.peer_id == "QmTestPeer"


@pytest.mark.asyncio
async def test_reconciliation_full_cycle(
    reconciliation_service,
    lease_validation_service,
    valid_task_lease,
):
    """
    Given partition -> buffering -> reconnection
    When full reconciliation cycle
    Then should recover to normal operation

    BDD Scenario: Full Reconciliation Cycle
    """
    # Given: Starting in normal mode
    assert reconciliation_service.state == ReconciliationState.NORMAL

    # Step 1: Enter degraded mode (partition detected)
    await reconciliation_service.enter_degraded_mode(reason="Network partition")
    assert reconciliation_service.state == ReconciliationState.DEGRADED

    # Step 2: Buffer results during partition
    # Use the same task_id as the valid_task_lease to avoid mismatch
    task_id = valid_task_lease.task_id
    result = TaskResult(
        task_id=task_id,
        peer_id=valid_task_lease.lease_owner_peer_id,  # Match lease owner
        lease_token=valid_task_lease.lease_token,
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Success"},
        execution_metadata={"duration_seconds": 100},
        submitted_at=datetime.now(timezone.utc),
    )

    await reconciliation_service.buffer_result(result)
    assert len(reconciliation_service.result_buffer) == 1

    # Step 3: Register lease for validation
    lease_validation_service.lease_store[valid_task_lease.lease_token] = (
        valid_task_lease
    )

    # Step 4: Detect reconnection
    with patch.object(
        reconciliation_service, "_check_dbos_health", return_value=True
    ):
        reconnected = await reconciliation_service.detect_reconnection()
        assert reconnected is True

    # Step 5: Flush buffered results
    submit_mock = AsyncMock(return_value={"success": True})
    with patch.object(
        reconciliation_service, "_submit_result_to_dbos", submit_mock
    ):
        flush_summary = await reconciliation_service.flush_buffered_results()

        # Then: Should successfully reconcile
        assert reconciliation_service.state == ReconciliationState.NORMAL
        assert flush_summary["submitted"] == 1
        assert len(reconciliation_service.result_buffer) == 0  # Buffer cleared


@pytest.mark.asyncio
async def test_buffer_capacity_limit(reconciliation_service):
    """
    Given buffer at max capacity
    When attempting to buffer more results
    Then should reject with buffer full error

    BDD Scenario: Buffer Overflow Protection
    """
    # Given: Fill buffer to capacity (default 1000)
    reconciliation_service.state = ReconciliationState.DEGRADED
    reconciliation_service.max_buffer_size = 5  # Set small for testing

    # Fill buffer
    for i in range(5):
        result = TaskResult(
            task_id=uuid4(),
            peer_id=f"QmTestPeer{i:03d}",  # At least 10 chars
            lease_token=f"valid_token_{i:05d}",  # At least 10 chars
            status=TaskStatus.COMPLETED,
            output_payload={"result": f"Task {i}"},
            execution_metadata={},
            submitted_at=datetime.now(timezone.utc),
        )
        await reconciliation_service.buffer_result(result)

    assert len(reconciliation_service.result_buffer) == 5

    # When: Attempting to buffer beyond capacity
    overflow_result = TaskResult(
        task_id=uuid4(),
        peer_id="QmOverflowPeer001",  # At least 10 chars
        lease_token="overflow_token_001",  # At least 10 chars
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Overflow"},
        execution_metadata={},
        submitted_at=datetime.now(timezone.utc),
    )

    buffer_success = await reconciliation_service.buffer_result(overflow_result)

    # Then: Should reject
    assert buffer_success is False
    assert len(reconciliation_service.result_buffer) == 5  # Unchanged


@pytest.mark.asyncio
async def test_validate_lease_before_submission(
    reconciliation_service,
    lease_validation_service,
    valid_task_lease,
):
    """
    Given buffered result with valid token
    When validating before submission
    Then should pass validation

    BDD Scenario: Lease Validation Before Flush
    """
    # Given: Buffered result with valid lease
    task_id = valid_task_lease.task_id
    result = BufferedResult(
        task_id=task_id,
        peer_id=valid_task_lease.lease_owner_peer_id,
        lease_token=valid_task_lease.lease_token,
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Success"},
        execution_metadata={"duration_seconds": 100},
        submitted_at=datetime.now(timezone.utc),
        buffered_at=datetime.now(timezone.utc),
    )

    # Register lease
    lease_validation_service.lease_store[valid_task_lease.lease_token] = (
        valid_task_lease
    )

    # When: Validating lease
    is_valid = await reconciliation_service._validate_buffered_result(result)

    # Then: Should be valid
    assert is_valid is True


@pytest.mark.asyncio
async def test_periodic_reconnection_attempts(reconciliation_service):
    """
    Given degraded mode
    When periodic health checks run
    Then should attempt reconnection

    BDD Scenario: Periodic Reconnection
    """
    # Given: Service in degraded mode
    reconciliation_service.state = ReconciliationState.DEGRADED
    reconciliation_service.reconnection_check_interval = 1  # 1 second for test

    # Mock health check to succeed after 2 attempts
    health_checks = [False, True]
    health_mock = AsyncMock(side_effect=health_checks)

    with patch.object(reconciliation_service, "_check_dbos_health", health_mock):
        # When: Running periodic reconnection checks
        # First attempt fails
        result1 = await reconciliation_service.detect_reconnection()
        assert result1 is False
        assert reconciliation_service.state == ReconciliationState.DEGRADED

        # Second attempt succeeds
        result2 = await reconciliation_service.detect_reconnection()
        assert result2 is True
        assert reconciliation_service.state == ReconciliationState.NORMAL


@pytest.mark.asyncio
async def test_close_cleanup(reconciliation_service):
    """
    Given initialized service
    When closing
    Then should cleanup HTTP client

    BDD Scenario: Service Cleanup
    """
    # When: Closing service
    await reconciliation_service.close()

    # Then: Client should be closed
    assert reconciliation_service.client.is_closed


@pytest.mark.asyncio
async def test_buffered_result_conversion(reconciliation_service):
    """
    Given TaskResult
    When buffering
    Then should convert to BufferedResult with timestamp

    BDD Scenario: Result Buffering with Conversion
    """
    # Given: TaskResult
    task_id = uuid4()
    result = TaskResult(
        task_id=task_id,
        peer_id="QmTestPeer123",
        lease_token="test_token_123456",
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Success"},
        execution_metadata={"duration_seconds": 100},
        submitted_at=datetime.now(timezone.utc),
    )

    # When: Buffering result
    reconciliation_service.state = ReconciliationState.DEGRADED
    success = await reconciliation_service.buffer_result(result)

    # Then: Should convert and buffer
    assert success is True
    assert len(reconciliation_service.result_buffer) == 1
    buffered = reconciliation_service.result_buffer[0]
    assert isinstance(buffered, BufferedResult)
    assert buffered.buffered_at is not None
    assert buffered.task_id == task_id


@pytest.mark.asyncio
async def test_reject_buffer_when_full(reconciliation_service):
    """
    Given buffer at capacity
    When attempting to buffer
    Then should reject and return False

    BDD Scenario: Buffer Overflow
    """
    # Given: Small buffer size
    reconciliation_service.max_buffer_size = 2
    reconciliation_service.state = ReconciliationState.DEGRADED

    # Fill buffer
    for i in range(2):
        result = TaskResult(
            task_id=uuid4(),
            peer_id=f"QmBufferPeer{i:03d}",
            lease_token=f"buffer_token_{i:05d}",
            status=TaskStatus.COMPLETED,
            output_payload={"result": f"Task {i}"},
            execution_metadata={},
            submitted_at=datetime.now(timezone.utc),
        )
        await reconciliation_service.buffer_result(result)

    # When: Attempting to exceed capacity
    overflow = TaskResult(
        task_id=uuid4(),
        peer_id="QmOverflow12345",
        lease_token="overflow_token123",
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Overflow"},
        execution_metadata={},
        submitted_at=datetime.now(timezone.utc),
    )

    success = await reconciliation_service.buffer_result(overflow)

    # Then: Should reject
    assert success is False
    assert len(reconciliation_service.result_buffer) == 2


@pytest.mark.asyncio
async def test_get_global_reconciliation_service():
    """
    Given no existing service
    When getting global instance
    Then should create new service

    BDD Scenario: Global Service Access
    """
    # When: Getting global service
    from backend.services.dbos_reconciliation_service import get_reconciliation_service

    service1 = get_reconciliation_service()
    service2 = get_reconciliation_service()

    # Then: Should return same instance
    assert service1 is service2

    # Cleanup
    await service1.close()


@pytest.mark.asyncio
async def test_already_in_degraded_mode(reconciliation_service):
    """
    Given already in degraded mode
    When entering degraded mode again
    Then should log warning and not change state

    BDD Scenario: Idempotent Degraded Mode Entry
    """
    # Given: Already in degraded mode
    await reconciliation_service.enter_degraded_mode(reason="First reason")
    first_degraded_since = reconciliation_service.degraded_since

    # When: Entering again
    await reconciliation_service.enter_degraded_mode(reason="Second reason")

    # Then: Should keep original state
    assert reconciliation_service.state == ReconciliationState.DEGRADED
    assert reconciliation_service.degraded_since == first_degraded_since
    assert reconciliation_service.degraded_reason == "First reason"


@pytest.mark.asyncio
async def test_detect_reconnection_when_already_normal(reconciliation_service):
    """
    Given normal state
    When detecting reconnection
    Then should return True without health check

    BDD Scenario: Redundant Reconnection Check
    """
    # Given: Already in normal mode
    assert reconciliation_service.state == ReconciliationState.NORMAL

    # When: Detecting reconnection
    result = await reconciliation_service.detect_reconnection()

    # Then: Should return True immediately
    assert result is True


@pytest.mark.asyncio
async def test_flush_buffer_clears_after_processing(
    reconciliation_service,
    lease_validation_service,
    valid_task_lease,
):
    """
    Given buffered results
    When flushing
    Then should clear buffer after processing

    BDD Scenario: Buffer Clearing
    """
    # Given: Buffered results
    reconciliation_service.state = ReconciliationState.NORMAL
    result = BufferedResult(
        task_id=valid_task_lease.task_id,
        peer_id=valid_task_lease.lease_owner_peer_id,
        lease_token=valid_task_lease.lease_token,
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Success"},
        execution_metadata={"duration_seconds": 100},
        submitted_at=datetime.now(timezone.utc),
        buffered_at=datetime.now(timezone.utc),
    )

    reconciliation_service.result_buffer = [result]

    # Register lease
    lease_validation_service.lease_store[valid_task_lease.lease_token] = (
        valid_task_lease
    )

    # Mock submission
    submit_mock = AsyncMock(return_value={"success": True})
    with patch.object(
        reconciliation_service, "_submit_result_to_dbos", submit_mock
    ):
        # When: Flushing
        await reconciliation_service.flush_buffered_results()

        # Then: Buffer should be cleared
        assert len(reconciliation_service.result_buffer) == 0


@pytest.mark.asyncio
async def test_submission_failure_tracking(
    reconciliation_service,
    lease_validation_service,
    valid_task_lease,
):
    """
    Given buffered result
    When submission fails
    Then should track failed count

    BDD Scenario: Submission Failure Handling
    """
    # Given: Buffered result
    reconciliation_service.state = ReconciliationState.NORMAL
    result = BufferedResult(
        task_id=valid_task_lease.task_id,
        peer_id=valid_task_lease.lease_owner_peer_id,
        lease_token=valid_task_lease.lease_token,
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Success"},
        execution_metadata={"duration_seconds": 100},
        submitted_at=datetime.now(timezone.utc),
        buffered_at=datetime.now(timezone.utc),
    )

    reconciliation_service.result_buffer = [result]

    # Register lease
    lease_validation_service.lease_store[valid_task_lease.lease_token] = (
        valid_task_lease
    )

    # Mock submission failure
    submit_mock = AsyncMock(return_value={"success": False, "error": "Network error"})
    with patch.object(
        reconciliation_service, "_submit_result_to_dbos", submit_mock
    ):
        # When: Flushing
        flush_summary = await reconciliation_service.flush_buffered_results()

        # Then: Should track failure
        assert flush_summary["failed"] == 1
        assert flush_summary["submitted"] == 0


@pytest.mark.asyncio
async def test_submission_exception_handling(
    reconciliation_service,
    lease_validation_service,
    valid_task_lease,
):
    """
    Given buffered result
    When submission raises exception
    Then should track as failed

    BDD Scenario: Submission Exception Handling
    """
    # Given: Buffered result
    reconciliation_service.state = ReconciliationState.NORMAL
    result = BufferedResult(
        task_id=valid_task_lease.task_id,
        peer_id=valid_task_lease.lease_owner_peer_id,
        lease_token=valid_task_lease.lease_token,
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Success"},
        execution_metadata={"duration_seconds": 100},
        submitted_at=datetime.now(timezone.utc),
        buffered_at=datetime.now(timezone.utc),
    )

    reconciliation_service.result_buffer = [result]

    # Register lease
    lease_validation_service.lease_store[valid_task_lease.lease_token] = (
        valid_task_lease
    )

    # Mock submission exception
    submit_mock = AsyncMock(side_effect=Exception("Unexpected error"))
    with patch.object(
        reconciliation_service, "_submit_result_to_dbos", submit_mock
    ):
        # When: Flushing
        flush_summary = await reconciliation_service.flush_buffered_results()

        # Then: Should track failure
        assert flush_summary["failed"] == 1


@pytest.mark.asyncio
async def test_ownership_mismatch_validation(
    reconciliation_service,
    lease_validation_service,
):
    """
    Given buffered result with wrong peer_id
    When validating
    Then should reject as invalid

    BDD Scenario: Ownership Validation
    """
    # Given: Lease with ownership mismatch
    task_id = uuid4()
    lease_token = "ownership_token_123456"

    lease = TaskLease(
        task_id=task_id,
        lease_owner_peer_id="QmRightPeer123",
        lease_token=lease_token,
        granted_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        heartbeat_interval=30,
    )

    # Result from wrong peer
    result = BufferedResult(
        task_id=task_id,
        peer_id="QmWrongPeer1234",  # Different peer
        lease_token=lease_token,
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Success"},
        execution_metadata={},
        submitted_at=datetime.now(timezone.utc),
        buffered_at=datetime.now(timezone.utc),
    )

    # Register lease
    lease_validation_service.lease_store[lease_token] = lease

    # When: Validating
    is_valid = await reconciliation_service._validate_buffered_result(result)

    # Then: Should be invalid
    assert is_valid is False


@pytest.mark.asyncio
async def test_validation_exception_handling(reconciliation_service):
    """
    Given validation exception
    When validating buffered result
    Then should return False

    BDD Scenario: Validation Exception Handling
    """
    # Given: Result that will cause validation exception
    result = BufferedResult(
        task_id=uuid4(),
        peer_id="QmTestPeer12345",
        lease_token="test_token_123456",
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Success"},
        execution_metadata={},
        submitted_at=datetime.now(timezone.utc),
        buffered_at=datetime.now(timezone.utc),
    )

    # Mock validator to raise generic exception
    with patch.object(
        reconciliation_service.lease_validator,
        "validate_lease_token",
        side_effect=Exception("Unexpected validation error"),
    ):
        # When: Validating
        is_valid = await reconciliation_service._validate_buffered_result(result)

        # Then: Should return False
        assert is_valid is False


@pytest.mark.asyncio
async def test_http_submission_success():
    """
    Given buffered result
    When HTTP submission succeeds
    Then should return success response

    BDD Scenario: HTTP Submission Success Path
    """
    # Given: Service and buffered result
    service = DBOSReconciliationService(
        dbos_gateway_url="http://test-gateway:8080",
        lease_validator=LeaseValidationService(),
    )

    result = BufferedResult(
        task_id=uuid4(),
        peer_id="QmTestPeer12345",
        lease_token="test_token_123456",
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Success"},
        execution_metadata={"duration_seconds": 100},
        submitted_at=datetime.now(timezone.utc),
        buffered_at=datetime.now(timezone.utc),
    )

    # Mock successful HTTP response
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True, "task_id": str(result.task_id)}

    with patch.object(service.client, "post", return_value=mock_response):
        # When: Submitting result
        submission = await service._submit_result_to_dbos(result)

        # Then: Should succeed
        assert submission["success"] is True
        assert submission["task_id"] == str(result.task_id)

    await service.close()


@pytest.mark.asyncio
async def test_http_submission_http_error():
    """
    Given buffered result
    When HTTP request fails
    Then should return error response

    BDD Scenario: HTTP Submission Error Path
    """
    # Given: Service and buffered result
    service = DBOSReconciliationService(
        dbos_gateway_url="http://test-gateway:8080",
        lease_validator=LeaseValidationService(),
    )

    result = BufferedResult(
        task_id=uuid4(),
        peer_id="QmTestPeer12345",
        lease_token="test_token_123456",
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Success"},
        execution_metadata={"duration_seconds": 100},
        submitted_at=datetime.now(timezone.utc),
        buffered_at=datetime.now(timezone.utc),
    )

    # Mock HTTP error
    with patch.object(
        service.client,
        "post",
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        # When: Submitting result
        submission = await service._submit_result_to_dbos(result)

        # Then: Should return error
        assert submission["success"] is False
        assert "HTTP error" in submission["error"]

    await service.close()


@pytest.mark.asyncio
async def test_http_submission_unexpected_error():
    """
    Given buffered result
    When unexpected exception occurs
    Then should return error response

    BDD Scenario: HTTP Submission Unexpected Error
    """
    # Given: Service and buffered result
    service = DBOSReconciliationService(
        dbos_gateway_url="http://test-gateway:8080",
        lease_validator=LeaseValidationService(),
    )

    result = BufferedResult(
        task_id=uuid4(),
        peer_id="QmTestPeer12345",
        lease_token="test_token_123456",
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Success"},
        execution_metadata={"duration_seconds": 100},
        submitted_at=datetime.now(timezone.utc),
        buffered_at=datetime.now(timezone.utc),
    )

    # Mock unexpected exception
    with patch.object(
        service.client,
        "post",
        side_effect=RuntimeError("Unexpected error"),
    ):
        # When: Submitting result
        submission = await service._submit_result_to_dbos(result)

        # Then: Should return error
        assert submission["success"] is False
        assert "Unexpected error" in submission["error"]

    await service.close()


@pytest.mark.asyncio
async def test_http_submission_non_200_status():
    """
    Given buffered result
    When HTTP returns non-200 status
    Then should return failure

    BDD Scenario: HTTP Non-Success Status
    """
    # Given: Service and buffered result
    service = DBOSReconciliationService(
        dbos_gateway_url="http://test-gateway:8080",
        lease_validator=LeaseValidationService(),
    )

    result = BufferedResult(
        task_id=uuid4(),
        peer_id="QmTestPeer12345",
        lease_token="test_token_123456",
        status=TaskStatus.COMPLETED,
        output_payload={"result": "Success"},
        execution_metadata={"duration_seconds": 100},
        submitted_at=datetime.now(timezone.utc),
        buffered_at=datetime.now(timezone.utc),
    )

    # Mock 500 error response
    mock_response = AsyncMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch.object(service.client, "post", return_value=mock_response):
        # When: Submitting result
        submission = await service._submit_result_to_dbos(result)

        # Then: Should return failure
        assert submission["success"] is False
        assert "HTTP 500" in submission["error"]

    await service.close()


@pytest.mark.asyncio
async def test_health_check_timeout():
    """
    Given DBOS endpoint
    When health check times out
    Then should return False

    BDD Scenario: Health Check Timeout
    """
    # Given: Service
    service = DBOSReconciliationService(
        dbos_gateway_url="http://test-gateway:8080",
        lease_validator=LeaseValidationService(),
    )

    # Mock timeout
    with patch.object(
        service.client,
        "get",
        side_effect=httpx.TimeoutException("Request timeout"),
    ):
        # When: Checking health
        is_healthy = await service._check_dbos_health()

        # Then: Should return False
        assert is_healthy is False

    await service.close()


@pytest.mark.asyncio
async def test_health_check_connection_error():
    """
    Given DBOS endpoint
    When connection fails
    Then should return False

    BDD Scenario: Health Check Connection Error
    """
    # Given: Service
    service = DBOSReconciliationService(
        dbos_gateway_url="http://test-gateway:8080",
        lease_validator=LeaseValidationService(),
    )

    # Mock connection error
    with patch.object(
        service.client,
        "get",
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        # When: Checking health
        is_healthy = await service._check_dbos_health()

        # Then: Should return False
        assert is_healthy is False

    await service.close()


@pytest.mark.asyncio
async def test_health_check_non_200_status():
    """
    Given DBOS endpoint
    When health endpoint returns non-200
    Then should return False

    BDD Scenario: Health Check Unhealthy Status
    """
    # Given: Service
    service = DBOSReconciliationService(
        dbos_gateway_url="http://test-gateway:8080",
        lease_validator=LeaseValidationService(),
    )

    # Mock 503 response
    mock_response = AsyncMock()
    mock_response.status_code = 503

    with patch.object(service.client, "get", return_value=mock_response):
        # When: Checking health
        is_healthy = await service._check_dbos_health()

        # Then: Should return False
        assert is_healthy is False

    await service.close()


@pytest.mark.asyncio
async def test_health_check_unexpected_exception():
    """
    Given DBOS endpoint
    When unexpected exception occurs
    Then should return False

    BDD Scenario: Health Check Unexpected Error
    """
    # Given: Service
    service = DBOSReconciliationService(
        dbos_gateway_url="http://test-gateway:8080",
        lease_validator=LeaseValidationService(),
    )

    # Mock unexpected exception
    with patch.object(
        service.client,
        "get",
        side_effect=RuntimeError("Unexpected error"),
    ):
        # When: Checking health
        is_healthy = await service._check_dbos_health()

        # Then: Should return False
        assert is_healthy is False

    await service.close()


@pytest.mark.asyncio
async def test_metrics_collection(reconciliation_service):
    """
    Given reconciliation operations
    When collecting metrics
    Then should track key performance indicators

    BDD Scenario: Metrics Collection
    """
    # Given: Service with operations
    # Enter degraded mode first to set degraded_since
    await reconciliation_service.enter_degraded_mode(reason="Test metrics")

    # Buffer some results
    for i in range(3):
        result = TaskResult(
            task_id=uuid4(),
            peer_id=f"QmMetricsPeer{i:03d}",  # At least 10 chars
            lease_token=f"metrics_token_{i:05d}",  # At least 10 chars
            status=TaskStatus.COMPLETED,
            output_payload={"result": f"Task {i}"},
            execution_metadata={},
            submitted_at=datetime.now(timezone.utc),
        )
        await reconciliation_service.buffer_result(result)

    # When: Getting metrics
    metrics = await reconciliation_service.get_metrics()

    # Then: Should include key metrics
    assert "state" in metrics
    assert "buffered_results_count" in metrics
    assert "degraded_duration_seconds" in metrics
    assert metrics["state"] == ReconciliationState.DEGRADED.value
    assert metrics["buffered_results_count"] == 3
