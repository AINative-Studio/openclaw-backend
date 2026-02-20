"""
Integration tests for late result rejection

Tests lease token validation, expiration checking, and peer notification
when task results are submitted with expired leases.

Refs #33
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from backend.services.lease_validation_service import (
    LeaseValidationService,
    LeaseValidationError,
    LeaseExpiredError,
    LeaseNotFoundError,
    LeaseOwnershipError,
)
from backend.schemas.task_schemas import TaskLease, TaskResult, TaskStatus


@pytest.fixture
def validation_service():
    """Create lease validation service instance"""
    return LeaseValidationService()


@pytest.fixture
def valid_lease():
    """Create a valid task lease"""
    return TaskLease(
        task_id=uuid4(),
        lease_owner_peer_id="12D3KooWEyopopk...",
        lease_token="valid_token_12345",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        granted_at=datetime.now(timezone.utc),
        heartbeat_interval=30,
    )


@pytest.fixture
def expired_lease():
    """Create an expired task lease"""
    return TaskLease(
        task_id=uuid4(),
        lease_owner_peer_id="12D3KooWEyopopk...",
        lease_token="expired_token_12345",
        lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        granted_at=datetime.now(timezone.utc) - timedelta(minutes=15),
        heartbeat_interval=30,
    )


@pytest.fixture
def valid_result(valid_lease):
    """Create a valid task result"""
    return TaskResult(
        task_id=valid_lease.task_id,
        peer_id=valid_lease.lease_owner_peer_id,
        lease_token=valid_lease.lease_token,
        status=TaskStatus.COMPLETED,
        output_payload={"result": "success"},
        execution_metadata={
            "duration_seconds": 120,
            "cpu_percent": 45.2,
            "memory_mb": 512,
        },
        submitted_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def expired_result(expired_lease):
    """Create a task result with expired lease"""
    return TaskResult(
        task_id=expired_lease.task_id,
        peer_id=expired_lease.lease_owner_peer_id,
        lease_token=expired_lease.lease_token,
        status=TaskStatus.COMPLETED,
        output_payload={"result": "success"},
        execution_metadata={
            "duration_seconds": 120,
            "cpu_percent": 45.2,
            "memory_mb": 512,
        },
        submitted_at=datetime.now(timezone.utc),
    )


class TestLeaseValidation:
    """Test lease token validation"""

    @pytest.mark.asyncio
    async def test_validate_valid_lease_token(
        self, validation_service, valid_lease
    ):
        """
        Given a valid lease token
        When validating the token
        Then should return True without errors
        """
        # Add lease to store
        validation_service.lease_store[valid_lease.lease_token] = valid_lease

        result = await validation_service.validate_lease_token(
            valid_lease.lease_token,
            valid_lease.task_id,
            valid_lease.lease_owner_peer_id,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_expired_lease_token(
        self, validation_service, expired_lease
    ):
        """
        Given an expired lease token
        When validating the token
        Then should raise LeaseExpiredError
        """
        # Add expired lease to store
        validation_service.lease_store[expired_lease.lease_token] = expired_lease

        with pytest.raises(LeaseExpiredError) as exc_info:
            await validation_service.validate_lease_token(
                expired_lease.lease_token,
                expired_lease.task_id,
                expired_lease.lease_owner_peer_id,
            )
        assert "expired" in str(exc_info.value).lower()
        assert expired_lease.lease_token in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_nonexistent_lease_token(self, validation_service):
        """
        Given a non-existent lease token
        When validating the token
        Then should raise LeaseNotFoundError
        """
        with pytest.raises(LeaseNotFoundError) as exc_info:
            await validation_service.validate_lease_token(
                "nonexistent_token_999",
                uuid4(),
                "12D3KooWEyopopk...",
            )
        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_validate_wrong_peer_id(self, validation_service, valid_lease):
        """
        Given a lease token with wrong peer_id
        When validating the token
        Then should raise LeaseOwnershipError
        """
        # Add lease to store
        validation_service.lease_store[valid_lease.lease_token] = valid_lease

        with pytest.raises(LeaseOwnershipError) as exc_info:
            await validation_service.validate_lease_token(
                valid_lease.lease_token,
                valid_lease.task_id,
                "12D3KooWDifferentPeer...",  # Different peer
            )
        assert "own" in str(exc_info.value).lower()


class TestLateResultRejection:
    """Test late result rejection workflow"""

    @pytest.mark.asyncio
    async def test_reject_result_expired_lease(
        self, validation_service, expired_result, expired_lease
    ):
        """
        Given a result with expired lease token
        When submitting the result
        Then should reject and return error details
        """
        # Add expired lease to validation service store
        validation_service.lease_store[expired_lease.lease_token] = expired_lease

        rejection = await validation_service.reject_late_result(expired_result)

        assert rejection is not None
        assert rejection["rejected"] is True
        assert rejection["reason"] == "lease_expired"
        assert "expires_at" in rejection
        assert rejection["task_id"] == str(expired_result.task_id)
        assert rejection["peer_id"] == expired_result.peer_id

    @pytest.mark.asyncio
    async def test_accept_result_valid_lease(
        self, validation_service, valid_result, valid_lease
    ):
        """
        Given a result with valid lease token
        When submitting the result
        Then should accept and update task status
        """
        # Add valid lease to validation service store
        validation_service.lease_store[valid_lease.lease_token] = valid_lease

        is_valid = await validation_service.validate_lease_token(
            valid_result.lease_token,
            valid_result.task_id,
            valid_result.peer_id,
        )

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_notify_peer_of_rejection(
        self, validation_service, expired_result, expired_lease
    ):
        """
        Given a rejected result
        When processing rejection
        Then should send notification to submitting peer
        """
        # Add expired lease to validation service store
        validation_service.lease_store[expired_lease.lease_token] = expired_lease

        rejection = await validation_service.reject_late_result(expired_result)
        notification = await validation_service.notify_peer_of_rejection(
            expired_result.peer_id, rejection
        )

        assert notification is not None
        assert notification.peer_id == expired_result.peer_id
        assert notification.notification_type == "result_rejected"
        assert notification.rejection_reason == "lease_expired"
        assert notification.timestamp is not None


class TestLeaseExpirationChecking:
    """Test lease expiration timestamp validation"""

    @pytest.mark.asyncio
    async def test_check_expires_at_timestamp(
        self, validation_service, valid_lease, expired_lease
    ):
        """
        Given leases with different expiration times
        When checking expiration
        Then should correctly identify expired vs valid leases
        """
        # Valid lease should not be expired
        is_valid_expired = await validation_service.is_lease_expired(valid_lease)
        assert is_valid_expired is False

        # Expired lease should be expired
        is_expired_expired = await validation_service.is_lease_expired(expired_lease)
        assert is_expired_expired is True

    @pytest.mark.asyncio
    async def test_verify_lease_token_validity(
        self, validation_service, valid_lease
    ):
        """
        Given a lease token
        When verifying validity
        Then should check signature and expiration
        """
        validation_service.lease_store[valid_lease.lease_token] = valid_lease

        is_valid = await validation_service.verify_lease_token_validity(
            valid_lease.lease_token
        )

        assert is_valid is True
        assert valid_lease.lease_token in validation_service.lease_store


class TestRejectionLogging:
    """Test rejection logging with detailed reasons"""

    @pytest.mark.asyncio
    async def test_log_rejection_with_reason(
        self, validation_service, expired_result, expired_lease
    ):
        """
        Given a rejected result
        When logging rejection
        Then should include task_id, peer_id, reason, and timestamp
        """
        validation_service.lease_store[expired_lease.lease_token] = expired_lease

        rejection = await validation_service.reject_late_result(expired_result)
        # Fix: need to add lease_token to rejection dict
        rejection["lease_token"] = expired_result.lease_token
        log_entry = await validation_service.log_rejection(rejection)

        assert log_entry is not None
        assert log_entry.task_id == str(expired_result.task_id)
        assert log_entry.peer_id == expired_result.peer_id
        assert log_entry.reason == "lease_expired"
        assert log_entry.lease_token == expired_result.lease_token
        assert log_entry.timestamp is not None
        assert log_entry.expires_at is not None

    @pytest.mark.asyncio
    async def test_log_multiple_rejections(self, validation_service):
        """
        Given multiple rejected results
        When logging rejections
        Then should maintain separate log entries
        """
        # Create multiple expired leases
        expired_leases = []
        expired_results = []

        for i in range(3):
            lease = TaskLease(
                task_id=uuid4(),
                lease_owner_peer_id=f"12D3KooWPeer{i}...",
                lease_token=f"expired_token_{i}",
                lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
                granted_at=datetime.now(timezone.utc) - timedelta(minutes=15),
                heartbeat_interval=30,
            )
            result = TaskResult(
                task_id=lease.task_id,
                peer_id=lease.lease_owner_peer_id,
                lease_token=lease.lease_token,
                status=TaskStatus.COMPLETED,
                output_payload={"result": f"task_{i}"},
                execution_metadata={},
                submitted_at=datetime.now(timezone.utc),
            )
            expired_leases.append(lease)
            expired_results.append(result)
            validation_service.lease_store[lease.lease_token] = lease

        log_entries = []
        for result in expired_results:
            rejection = await validation_service.reject_late_result(result)
            # Fix: need to add lease_token to rejection dict
            rejection["lease_token"] = result.lease_token
            log_entry = await validation_service.log_rejection(rejection)
            log_entries.append(log_entry)

        assert len(log_entries) == 3
        assert len(set(e.task_id for e in log_entries)) == 3
        assert len(set(e.peer_id for e in log_entries)) == 3


class TestEdgeCases:
    """Test edge cases and error conditions"""

    @pytest.mark.asyncio
    async def test_reject_result_with_missing_lease(
        self, validation_service, valid_result
    ):
        """
        Given a result with non-existent lease
        When submitting result
        Then should reject with lease_not_found reason
        """
        with pytest.raises(LeaseNotFoundError):
            await validation_service.validate_lease_token(
                valid_result.lease_token,
                valid_result.task_id,
                valid_result.peer_id,
            )

    @pytest.mark.asyncio
    async def test_reject_result_wrong_task_id(
        self, validation_service, valid_lease, valid_result
    ):
        """
        Given a result with wrong task_id
        When validating
        Then should reject with task_mismatch reason
        """
        validation_service.lease_store[valid_lease.lease_token] = valid_lease

        with pytest.raises(LeaseValidationError):
            await validation_service.validate_lease_token(
                valid_lease.lease_token,
                uuid4(),  # Different task_id
                valid_lease.lease_owner_peer_id,
            )

    @pytest.mark.asyncio
    async def test_handle_lease_at_exact_expiration(self, validation_service):
        """
        Given a lease at exact expiration time
        When checking expiration
        Then should be considered expired
        """
        now = datetime.now(timezone.utc)
        lease = TaskLease(
            task_id=uuid4(),
            lease_owner_peer_id="12D3KooWTest...",
            lease_token="token_at_expiration",
            lease_expires_at=now,
            granted_at=now - timedelta(minutes=10),
            heartbeat_interval=30,
        )

        is_expired = await validation_service.is_lease_expired(lease)
        assert is_expired is True
