"""
Integration Tests for Token Lifecycle (E7-S5)

Tests complete token lifecycle including creation, renewal, revocation,
and database persistence.

Refs: #47
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.db.base import Base
from backend.services.token_rotation_service import TokenRotationService
from backend.models.capability_token import CapabilityToken, TokenLimits
from backend.models.token_revocation import TokenRevocation


@pytest.fixture(scope="function")
def test_db():
    """Create in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def rotation_service(test_db):
    """Token rotation service with real database"""
    return TokenRotationService(db=test_db)


@pytest.fixture
def sample_limits():
    """Sample token limits"""
    return TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=5)


@pytest.fixture
def sample_capabilities():
    """Sample capability list"""
    return ["can_execute:llama-2-7b", "can_read:task:integration_test"]


class TestTokenLifecycle:
    """Test complete token lifecycle"""

    @pytest.mark.asyncio
    async def test_token_creation_and_renewal_lifecycle(
        self, rotation_service, test_db, sample_capabilities, sample_limits
    ):
        """
        Given new token, when renewing,
        then should create new token and persist revocation
        """
        # Create initial token
        token = CapabilityToken.create(
            peer_id="peer_lifecycle_test",
            capabilities=sample_capabilities,
            limits=sample_limits,
            expires_in_seconds=3600
        )

        # Renew token
        new_token = await rotation_service.renew_token(token)

        # Verify new token
        assert new_token.jti != token.jti
        assert new_token.peer_id == token.peer_id
        assert new_token.parent_jti == token.jti

        # Verify old token is revoked in database
        revocation = test_db.query(TokenRevocation).filter(
            TokenRevocation.jti == token.jti
        ).first()

        assert revocation is not None
        assert revocation.reason == "rotation"
        assert revocation.replaced_by_jti == new_token.jti

    @pytest.mark.asyncio
    async def test_multiple_renewals_create_chain(
        self, rotation_service, test_db, sample_capabilities, sample_limits
    ):
        """
        Given token renewed multiple times,
        then should create audit chain in database
        """
        # Create initial token
        token1 = CapabilityToken.create(
            peer_id="peer_chain_test",
            capabilities=sample_capabilities,
            limits=sample_limits,
            expires_in_seconds=3600
        )

        # First renewal
        token2 = await rotation_service.renew_token(token1)

        # Second renewal
        token3 = await rotation_service.renew_token(token2)

        # Verify chain in database
        revocations = test_db.query(TokenRevocation).order_by(
            TokenRevocation.revoked_at
        ).all()

        assert len(revocations) == 2

        # Verify first revocation
        assert revocations[0].jti == token1.jti
        assert revocations[0].replaced_by_jti == token2.jti

        # Verify second revocation
        assert revocations[1].jti == token2.jti
        assert revocations[1].replaced_by_jti == token3.jti

        # Verify lineage
        assert token2.parent_jti == token1.jti
        assert token3.parent_jti == token2.jti

    @pytest.mark.asyncio
    async def test_revoked_token_validation(
        self, rotation_service, test_db, sample_capabilities, sample_limits
    ):
        """
        Given revoked token, when validating,
        then should reject after grace period
        """
        # Create and revoke token
        token = CapabilityToken.create(
            peer_id="peer_validation_test",
            capabilities=sample_capabilities,
            limits=sample_limits,
            expires_in_seconds=3600
        )

        await rotation_service.revoke_token(
            jti=token.jti,
            expires_at=datetime.fromtimestamp(token.expires_at),
            reason="test"
        )

        # Should be valid within grace period
        is_valid_with_grace = await rotation_service.validate_token(
            token,
            grace_period_seconds=300
        )
        assert is_valid_with_grace is True

        # Should be invalid without grace period
        is_valid_no_grace = await rotation_service.validate_token(
            token,
            grace_period_seconds=0
        )
        assert is_valid_no_grace is False


class TestGracePeriodIntegration:
    """Test grace period functionality with database"""

    @pytest.mark.asyncio
    async def test_grace_period_allows_old_token(
        self, rotation_service, test_db, sample_capabilities, sample_limits
    ):
        """
        Given token renewed with grace period,
        when validating old token immediately,
        then should still be valid
        """
        # Create and renew token
        old_token = CapabilityToken.create(
            peer_id="peer_grace_test",
            capabilities=sample_capabilities,
            limits=sample_limits,
            expires_in_seconds=3600
        )

        new_token = await rotation_service.renew_token(
            old_token,
            grace_period_seconds=300
        )

        # Old token should still be valid within grace period
        is_valid = await rotation_service.validate_token(
            old_token,
            grace_period_seconds=300
        )

        assert is_valid is True

        # Verify revocation exists
        revocation = test_db.query(TokenRevocation).filter(
            TokenRevocation.jti == old_token.jti
        ).first()
        assert revocation is not None

    @pytest.mark.asyncio
    async def test_grace_period_expires(
        self, rotation_service, test_db, sample_capabilities, sample_limits
    ):
        """
        Given token revoked long ago,
        when checking grace period,
        then should be expired
        """
        # Create token
        token = CapabilityToken.create(
            peer_id="peer_expired_grace",
            capabilities=sample_capabilities,
            limits=sample_limits,
            expires_in_seconds=3600
        )

        # Revoke token
        await rotation_service.revoke_token(
            jti=token.jti,
            expires_at=datetime.fromtimestamp(token.expires_at),
            reason="test"
        )

        # Manually update revoked_at to be old
        revocation = test_db.query(TokenRevocation).filter(
            TokenRevocation.jti == token.jti
        ).first()
        revocation.revoked_at = datetime.utcnow() - timedelta(minutes=10)
        test_db.commit()

        # Should not be within grace period
        is_within_grace = await rotation_service.is_within_grace_period(
            token.jti,
            grace_period_seconds=300  # 5 minutes
        )

        assert is_within_grace is False


class TestRevocationCleanupIntegration:
    """Test automatic cleanup of old revocations"""

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_entries(
        self, rotation_service, test_db, sample_capabilities, sample_limits
    ):
        """
        Given old revocations in database,
        when running cleanup,
        then should remove expired entries
        """
        # Create old token
        old_token = CapabilityToken.create(
            peer_id="peer_old_revocation",
            capabilities=sample_capabilities,
            limits=sample_limits,
            expires_in_seconds=3600
        )

        # Revoke it
        await rotation_service.revoke_token(
            jti=old_token.jti,
            expires_at=datetime.fromtimestamp(old_token.expires_at),
            reason="test"
        )

        # Manually update dates to be old
        revocation = test_db.query(TokenRevocation).filter(
            TokenRevocation.jti == old_token.jti
        ).first()
        revocation.expires_at = datetime.utcnow() - timedelta(days=35)
        revocation.revoked_at = datetime.utcnow() - timedelta(days=35)
        test_db.commit()

        # Run cleanup
        deleted = await rotation_service.cleanup_old_revocations(retention_days=30)

        assert deleted == 1

        # Verify entry is gone
        remaining = test_db.query(TokenRevocation).filter(
            TokenRevocation.jti == old_token.jti
        ).first()

        assert remaining is None

    @pytest.mark.asyncio
    async def test_cleanup_preserves_recent_entries(
        self, rotation_service, test_db, sample_capabilities, sample_limits
    ):
        """
        Given recent revocations,
        when running cleanup,
        then should preserve them
        """
        # Create recent token
        recent_token = CapabilityToken.create(
            peer_id="peer_recent_revocation",
            capabilities=sample_capabilities,
            limits=sample_limits,
            expires_in_seconds=3600
        )

        # Revoke it
        await rotation_service.revoke_token(
            jti=recent_token.jti,
            expires_at=datetime.fromtimestamp(recent_token.expires_at),
            reason="test"
        )

        # Run cleanup
        deleted = await rotation_service.cleanup_old_revocations(retention_days=30)

        assert deleted == 0

        # Verify entry still exists
        remaining = test_db.query(TokenRevocation).filter(
            TokenRevocation.jti == recent_token.jti
        ).first()

        assert remaining is not None


class TestAuditTrailIntegration:
    """Test audit trail persistence"""

    @pytest.mark.asyncio
    async def test_audit_trail_persists(
        self, rotation_service, test_db, sample_capabilities, sample_limits
    ):
        """
        Given token operations,
        when querying audit trail,
        then should show complete history
        """
        # Create and renew token
        token1 = CapabilityToken.create(
            peer_id="peer_audit_test",
            capabilities=sample_capabilities,
            limits=sample_limits,
            expires_in_seconds=3600
        )

        token2 = await rotation_service.renew_token(token1)

        # Query audit trail
        audit = await rotation_service.get_revocation_audit_trail(token1.jti)

        assert audit is not None
        assert audit.jti == token1.jti
        assert audit.replaced_by_jti == token2.jti
        assert audit.reason == "rotation"
        assert isinstance(audit.revoked_at, datetime)

    @pytest.mark.asyncio
    async def test_audit_trail_multiple_reasons(
        self, rotation_service, test_db, sample_capabilities, sample_limits
    ):
        """
        Given tokens revoked for different reasons,
        when querying,
        then should preserve reason information
        """
        # Create tokens with different revocation reasons
        token1 = CapabilityToken.create(
            peer_id="peer_reasons_1",
            capabilities=sample_capabilities,
            limits=sample_limits,
            expires_in_seconds=3600
        )

        token2 = CapabilityToken.create(
            peer_id="peer_reasons_2",
            capabilities=sample_capabilities,
            limits=sample_limits,
            expires_in_seconds=3600
        )

        # Revoke with different reasons
        await rotation_service.revoke_token(
            jti=token1.jti,
            expires_at=datetime.fromtimestamp(token1.expires_at),
            reason="rotation"
        )

        await rotation_service.revoke_token(
            jti=token2.jti,
            expires_at=datetime.fromtimestamp(token2.expires_at),
            reason="compromise"
        )

        # Query and verify
        audit1 = await rotation_service.get_revocation_audit_trail(token1.jti)
        audit2 = await rotation_service.get_revocation_audit_trail(token2.jti)

        assert audit1.reason == "rotation"
        assert audit2.reason == "compromise"


class TestAutomaticRenewalIntegration:
    """Test automatic renewal with database"""

    @pytest.mark.asyncio
    async def test_auto_renew_creates_new_token(
        self, rotation_service, test_db, sample_capabilities, sample_limits
    ):
        """
        Given expiring token,
        when auto-renewing,
        then should create and persist new token
        """
        # Create expiring token
        expiring_token = CapabilityToken.create(
            peer_id="peer_auto_renew",
            capabilities=sample_capabilities,
            limits=sample_limits,
            expires_in_seconds=1800  # 30 minutes
        )

        # Auto-renew if needed
        new_token = await rotation_service.renew_if_needed(
            expiring_token,
            threshold_seconds=3600  # Renew if < 1 hour
        )

        # Should have renewed
        assert new_token is not None
        assert new_token.jti != expiring_token.jti

        # Verify revocation in database
        revocation = test_db.query(TokenRevocation).filter(
            TokenRevocation.jti == expiring_token.jti
        ).first()

        assert revocation is not None

    @pytest.mark.asyncio
    async def test_auto_renew_skips_fresh_token(
        self, rotation_service, test_db, sample_capabilities, sample_limits
    ):
        """
        Given fresh token,
        when auto-renewing,
        then should not create new token
        """
        # Create fresh token
        fresh_token = CapabilityToken.create(
            peer_id="peer_fresh",
            capabilities=sample_capabilities,
            limits=sample_limits,
            expires_in_seconds=7200  # 2 hours
        )

        # Try auto-renew
        new_token = await rotation_service.renew_if_needed(
            fresh_token,
            threshold_seconds=3600  # Only renew if < 1 hour
        )

        # Should not have renewed
        assert new_token is None

        # Verify no revocation in database
        revocation = test_db.query(TokenRevocation).filter(
            TokenRevocation.jti == fresh_token.jti
        ).first()

        assert revocation is None


class TestConcurrentOperations:
    """Test concurrent token operations"""

    @pytest.mark.asyncio
    async def test_multiple_tokens_same_peer(
        self, rotation_service, test_db, sample_capabilities, sample_limits
    ):
        """
        Given multiple tokens for same peer,
        when managing independently,
        then should track separately
        """
        peer_id = "peer_concurrent"

        # Create multiple tokens for same peer
        token1 = CapabilityToken.create(
            peer_id=peer_id,
            capabilities=sample_capabilities,
            limits=sample_limits,
            expires_in_seconds=3600
        )

        token2 = CapabilityToken.create(
            peer_id=peer_id,
            capabilities=sample_capabilities,
            limits=sample_limits,
            expires_in_seconds=3600
        )

        # Renew both
        new_token1 = await rotation_service.renew_token(token1)
        new_token2 = await rotation_service.renew_token(token2)

        # Verify both are tracked separately
        revocations = test_db.query(TokenRevocation).all()
        assert len(revocations) == 2

        # Verify correct replacements
        rev1 = test_db.query(TokenRevocation).filter(
            TokenRevocation.jti == token1.jti
        ).first()
        rev2 = test_db.query(TokenRevocation).filter(
            TokenRevocation.jti == token2.jti
        ).first()

        assert rev1.replaced_by_jti == new_token1.jti
        assert rev2.replaced_by_jti == new_token2.jti
