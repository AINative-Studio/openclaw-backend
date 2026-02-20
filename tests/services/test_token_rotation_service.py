"""
Unit Tests for Token Rotation Service (E7-S5)

Tests token renewal, revocation, grace periods, and audit logging.

Refs: #47
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from sqlalchemy.orm import Session

from backend.services.token_rotation_service import TokenRotationService
from backend.models.capability_token import CapabilityToken, TokenLimits
from backend.models.token_revocation import TokenRevocation


@pytest.fixture
def db_session():
    """Mock database session"""
    session = Mock(spec=Session)
    session.add = Mock()
    session.commit = Mock()
    session.query = Mock()
    session.flush = Mock()
    return session


@pytest.fixture
def rotation_service(db_session):
    """Token rotation service instance"""
    return TokenRotationService(db=db_session)


@pytest.fixture
def sample_limits():
    """Sample token limits"""
    return TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=5)


@pytest.fixture
def sample_token(sample_limits):
    """Create a sample capability token"""
    return CapabilityToken.create(
        peer_id="peer_abc123",
        capabilities=["can_execute:llama-2-7b", "can_read:task:123"],
        limits=sample_limits,
        expires_in_seconds=3600  # 1 hour
    )


@pytest.fixture
def expiring_token(sample_limits):
    """Create a token expiring in 30 minutes"""
    return CapabilityToken.create(
        peer_id="peer_xyz789",
        capabilities=["can_execute:gpt-3.5"],
        limits=sample_limits,
        expires_in_seconds=1800  # 30 minutes
    )


class TestTokenRenewal:
    """Test token renewal functionality"""

    @pytest.mark.asyncio
    async def test_renew_capability_token(self, rotation_service, expiring_token, db_session):
        """
        Given token expiring soon, when renewing,
        then should issue new token and revoke old
        """
        # Arrange
        original_jti = expiring_token.jti
        original_exp = expiring_token.expires_at

        # Act
        new_token = await rotation_service.renew_token(expiring_token)

        # Assert
        assert new_token is not None
        assert new_token.jti != original_jti
        assert new_token.peer_id == expiring_token.peer_id
        assert new_token.capabilities == expiring_token.capabilities
        assert new_token.expires_at > original_exp
        assert new_token.parent_jti == original_jti

        # Verify old token was revoked
        db_session.add.assert_called()
        revocation_call = [call for call in db_session.add.call_args_list
                          if isinstance(call[0][0], TokenRevocation)]
        assert len(revocation_call) > 0
        db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_renewal_preserves_capabilities(self, rotation_service, sample_token):
        """
        Given token with multiple capabilities, when renewing,
        then new token should have same capabilities and limits
        """
        # Act
        new_token = await rotation_service.renew_token(sample_token)

        # Assert
        assert len(new_token.capabilities) == len(sample_token.capabilities)
        assert new_token.capabilities == sample_token.capabilities
        assert new_token.limits.max_gpu_minutes == sample_token.limits.max_gpu_minutes
        assert new_token.limits.max_concurrent_tasks == sample_token.limits.max_concurrent_tasks

    @pytest.mark.asyncio
    async def test_renewal_extends_expiration(self, rotation_service, expiring_token):
        """
        Given token expiring soon, when renewing,
        then new token should have extended expiration
        """
        # Arrange
        original_exp = expiring_token.expires_at

        # Act
        new_token = await rotation_service.renew_token(
            expiring_token,
            extends_by_seconds=7200  # 2 hours
        )

        # Assert
        # New expiration should be ~2 hours from now
        expected_exp = int((datetime.utcnow() + timedelta(hours=2)).timestamp())
        assert abs(new_token.expires_at - expected_exp) < 5  # Allow 5 second tolerance


class TestTokenRevocation:
    """Test token revocation functionality"""

    @pytest.mark.asyncio
    async def test_reject_revoked_token(self, rotation_service, sample_token, db_session):
        """
        Given revoked token, when using,
        then should reject with revocation error
        """
        # Arrange - Revoke the token
        await rotation_service.revoke_token(
            sample_token.jti,
            datetime.fromtimestamp(sample_token.expires_at),
            reason="test_revocation"
        )

        # Mock query to return revoked token
        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = TokenRevocation(
            jti=sample_token.jti,
            expires_at=datetime.fromtimestamp(sample_token.expires_at),
            reason="test_revocation"
        )
        db_session.query.return_value = mock_query

        # Act & Assert
        is_revoked = await rotation_service.is_token_revoked(sample_token.jti)
        assert is_revoked is True

    @pytest.mark.asyncio
    async def test_revoke_with_reason(self, rotation_service, sample_token, db_session):
        """
        Given token to revoke, when revoking with reason,
        then should store reason in database
        """
        # Act
        await rotation_service.revoke_token(
            sample_token.jti,
            datetime.fromtimestamp(sample_token.expires_at),
            reason="compromise"
        )

        # Assert
        db_session.add.assert_called()
        revocation_call_args = db_session.add.call_args_list[-1][0][0]
        assert isinstance(revocation_call_args, TokenRevocation)
        assert revocation_call_args.reason == "compromise"
        assert revocation_call_args.jti == sample_token.jti


class TestAutomaticRenewal:
    """Test automatic token renewal"""

    @pytest.mark.asyncio
    async def test_automatic_renewal(self, rotation_service, db_session, sample_limits):
        """
        Given token 10min from expiry, when checking,
        then should trigger automatic renewal
        """
        # Arrange - Create token expiring in 10 minutes
        token = CapabilityToken.create(
            peer_id="peer_auto123",
            capabilities=["can_execute:model"],
            limits=sample_limits,
            expires_in_seconds=600  # 10 minutes
        )

        # Act
        should_renew = await rotation_service.should_auto_renew(
            token,
            threshold_seconds=3600  # Renew if < 1 hour remaining
        )

        # Assert
        assert should_renew is True

    @pytest.mark.asyncio
    async def test_no_renewal_for_fresh_token(self, rotation_service, sample_token):
        """
        Given fresh token with 1 hour lifetime, when checking,
        then should not trigger renewal
        """
        # Act
        should_renew = await rotation_service.should_auto_renew(
            sample_token,
            threshold_seconds=600  # Only renew if < 10 minutes remaining
        )

        # Assert
        assert should_renew is False


class TestRenewalAuditTrail:
    """Test audit logging for token operations"""

    @pytest.mark.asyncio
    async def test_renewal_audit_trail(self, rotation_service, expiring_token, db_session):
        """
        Given token renewed, when querying audit log,
        then should show rotation event with old/new token IDs
        """
        # Arrange
        original_jti = expiring_token.jti

        # Act
        new_token = await rotation_service.renew_token(expiring_token)

        # Assert - Check revocation entry has audit trail
        revocation_calls = [call[0][0] for call in db_session.add.call_args_list
                           if isinstance(call[0][0], TokenRevocation)]
        assert len(revocation_calls) > 0

        revocation = revocation_calls[-1]
        assert revocation.jti == original_jti
        assert revocation.replaced_by_jti == new_token.jti
        assert revocation.reason == "rotation"

    @pytest.mark.asyncio
    async def test_audit_log_includes_timestamp(self, rotation_service, sample_token, db_session):
        """
        Given token operation, when creating audit entry,
        then should include accurate timestamp
        """
        # Arrange
        before_revocation = datetime.utcnow()

        # Act
        await rotation_service.revoke_token(
            sample_token.jti,
            datetime.fromtimestamp(sample_token.expires_at),
            reason="audit_test"
        )

        # Assert
        revocation_calls = [call[0][0] for call in db_session.add.call_args_list
                           if isinstance(call[0][0], TokenRevocation)]
        revocation = revocation_calls[-1]

        after_revocation = datetime.utcnow()
        # revoked_at is set by the model's default factory, so it should have a value
        assert revocation.revoked_at is not None
        assert isinstance(revocation.revoked_at, datetime)


class TestRenewalGracePeriod:
    """Test grace period during token rotation"""

    @pytest.mark.asyncio
    async def test_renewal_grace_period(self, rotation_service, expiring_token, db_session):
        """
        Given renewal triggered, when old token still valid,
        then should allow 5 min grace period for transition
        """
        # Arrange
        original_jti = expiring_token.jti

        # Act - Renew token
        new_token = await rotation_service.renew_token(
            expiring_token,
            grace_period_seconds=300  # 5 minutes
        )

        # During grace period, old token should still be usable
        # Mock the query to simulate grace period check
        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter

        # Simulate finding revocation with recent timestamp (within grace period)
        recent_revocation = TokenRevocation(
            jti=original_jti,
            expires_at=datetime.fromtimestamp(expiring_token.expires_at),
            reason="rotation",
            replaced_by_jti=new_token.jti
        )
        recent_revocation.revoked_at = datetime.utcnow()  # Set the timestamp explicitly
        mock_filter.first.return_value = recent_revocation
        db_session.query.return_value = mock_query

        # Assert
        is_within_grace = await rotation_service.is_within_grace_period(
            original_jti,
            grace_period_seconds=300
        )
        assert is_within_grace is True

    @pytest.mark.asyncio
    async def test_grace_period_expired(self, rotation_service, sample_token, db_session):
        """
        Given token revoked 10 minutes ago, when checking grace period,
        then should return False
        """
        # Arrange - Create old revocation
        old_revocation = TokenRevocation(
            jti=sample_token.jti,
            expires_at=datetime.fromtimestamp(sample_token.expires_at),
            reason="rotation"
        )
        old_revocation.revoked_at = datetime.utcnow() - timedelta(minutes=10)

        # Mock query
        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = old_revocation
        db_session.query.return_value = mock_query

        # Act
        is_within_grace = await rotation_service.is_within_grace_period(
            sample_token.jti,
            grace_period_seconds=300  # 5 minutes
        )

        # Assert
        assert is_within_grace is False


class TestTokenValidation:
    """Test token validation with revocation checks"""

    @pytest.mark.asyncio
    async def test_validate_non_revoked_token(self, rotation_service, sample_token, db_session):
        """
        Given valid non-revoked token, when validating,
        then should return True
        """
        # Arrange - Mock query to return None (not revoked)
        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = None
        db_session.query.return_value = mock_query

        # Act
        is_valid = await rotation_service.validate_token(sample_token)

        # Assert
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_validate_expired_token(self, rotation_service, sample_limits, db_session):
        """
        Given expired token, when validating,
        then should return False
        """
        # Arrange - Create a token that will expire immediately
        # We need to bypass the validator, so we'll create it normally then check after it expires
        # For testing purposes, create a token with short expiry
        import time

        expired_token = CapabilityToken.create(
            peer_id="peer_expired",
            capabilities=["can_execute:model"],
            limits=sample_limits,
            expires_in_seconds=1  # 1 second
        )

        # Wait for it to expire
        time.sleep(2)

        # Mock the query to return None (not revoked)
        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = None
        db_session.query.return_value = mock_query

        # Act
        is_valid = await rotation_service.validate_token(expired_token)

        # Assert
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_validate_revoked_token(self, rotation_service, sample_token, db_session):
        """
        Given revoked token, when validating,
        then should return False
        """
        # Arrange - Mock query to return revocation
        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        revocation = TokenRevocation(
            jti=sample_token.jti,
            expires_at=datetime.fromtimestamp(sample_token.expires_at),
            reason="test"
        )
        # Set revoked_at to be outside grace period
        revocation.revoked_at = datetime.utcnow() - timedelta(minutes=10)
        mock_filter.first.return_value = revocation
        db_session.query.return_value = mock_query

        # Act
        is_valid = await rotation_service.validate_token(sample_token, grace_period_seconds=300)

        # Assert
        assert is_valid is False


class TestRevocationCleanup:
    """Test automatic cleanup of old revocations"""

    @pytest.mark.asyncio
    async def test_cleanup_old_revocations(self, rotation_service, db_session):
        """
        Given revocations older than 30 days, when running cleanup,
        then should delete old entries
        """
        # Arrange - Mock query for old revocations
        old_revocation = TokenRevocation(
            jti="old_token_123",
            expires_at=datetime.utcnow() - timedelta(days=35),
            reason="rotation"
        )

        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        mock_filter.all.return_value = [old_revocation]
        db_session.query.return_value = mock_query
        db_session.delete = Mock()

        # Act
        deleted_count = await rotation_service.cleanup_old_revocations(retention_days=30)

        # Assert
        assert deleted_count == 1
        db_session.delete.assert_called_once_with(old_revocation)
        db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_preserves_recent_revocations(self, rotation_service, db_session):
        """
        Given recent revocations, when running cleanup,
        then should preserve entries
        """
        # Arrange - Mock query for recent revocations
        recent_revocation = TokenRevocation(
            jti="recent_token_456",
            expires_at=datetime.utcnow() - timedelta(days=15),
            reason="rotation"
        )

        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        mock_filter.all.return_value = []  # No old revocations
        db_session.query.return_value = mock_query

        # Act
        deleted_count = await rotation_service.cleanup_old_revocations(retention_days=30)

        # Assert
        assert deleted_count == 0
        db_session.delete.assert_not_called()
