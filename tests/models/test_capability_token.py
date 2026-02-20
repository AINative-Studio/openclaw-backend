"""
Tests for CapabilityToken model (E7-S1)

BDD-style tests for capability token schema validation.
Refs: OpenCLAW P2P Swarm PRD Section on Security, Backlog E7-S1
"""

import pytest
from datetime import datetime, timedelta
from pydantic import ValidationError


def test_create_valid_capability_token():
    """
    Given all required token fields, when creating CapabilityToken,
    then should create valid token model
    """
    from backend.models.capability_token import CapabilityToken, TokenLimits

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b", "can_execute:gpt-3.5-turbo"],
        limits=TokenLimits(
            max_gpu_minutes=1000,
            max_concurrent_tasks=3
        ),
        data_scope=["project-alpha", "project-beta"],
        expires_at=expires_at
    )

    assert token.peer_id == "12D3KooWEyopopk1234567890"
    assert len(token.capabilities) == 2
    assert "can_execute:llama-2-7b" in token.capabilities
    assert token.limits.max_gpu_minutes == 1000
    assert token.limits.max_concurrent_tasks == 3
    assert len(token.data_scope) == 2
    assert token.expires_at == expires_at


def test_capability_token_missing_peer_id():
    """
    Given token without peer_id, when creating CapabilityToken,
    then should raise ValidationError
    """
    from backend.models.capability_token import CapabilityToken, TokenLimits

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    with pytest.raises(ValidationError) as exc_info:
        CapabilityToken(
            capabilities=["can_execute:llama-2-7b"],
            limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
            data_scope=["project-alpha"],
            expires_at=expires_at
        )

    assert "peer_id" in str(exc_info.value)


def test_capability_token_empty_peer_id():
    """
    Given token with empty peer_id, when creating CapabilityToken,
    then should raise ValidationError
    """
    from backend.models.capability_token import CapabilityToken, TokenLimits

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    with pytest.raises(ValidationError) as exc_info:
        CapabilityToken(
            peer_id="",
            capabilities=["can_execute:llama-2-7b"],
            limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
            data_scope=["project-alpha"],
            expires_at=expires_at
        )

    assert "peer_id" in str(exc_info.value).lower()


def test_capability_token_negative_limits():
    """
    Given token with negative limits, when creating CapabilityToken,
    then should raise ValidationError
    """
    from backend.models.capability_token import CapabilityToken, TokenLimits

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    with pytest.raises(ValidationError) as exc_info:
        CapabilityToken(
            peer_id="12D3KooWEyopopk1234567890",
            capabilities=["can_execute:llama-2-7b"],
            limits=TokenLimits(max_gpu_minutes=-100, max_concurrent_tasks=3),
            data_scope=["project-alpha"],
            expires_at=expires_at
        )

    assert "max_gpu_minutes" in str(exc_info.value).lower()


def test_capability_token_past_expiration():
    """
    Given token with past expiration, when creating CapabilityToken,
    then should raise ValidationError
    """
    from backend.models.capability_token import CapabilityToken, TokenLimits

    # Past timestamp
    expires_at = int((datetime.utcnow() - timedelta(hours=1)).timestamp())

    with pytest.raises(ValidationError) as exc_info:
        CapabilityToken(
            peer_id="12D3KooWEyopopk1234567890",
            capabilities=["can_execute:llama-2-7b"],
            limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
            data_scope=["project-alpha"],
            expires_at=expires_at
        )

    assert "expires_at" in str(exc_info.value).lower() or "expir" in str(exc_info.value).lower()


def test_capability_token_empty_capabilities():
    """
    Given token with empty capabilities list, when creating CapabilityToken,
    then should raise ValidationError
    """
    from backend.models.capability_token import CapabilityToken, TokenLimits

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    with pytest.raises(ValidationError) as exc_info:
        CapabilityToken(
            peer_id="12D3KooWEyopopk1234567890",
            capabilities=[],
            limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
            data_scope=["project-alpha"],
            expires_at=expires_at
        )

    assert "capabilities" in str(exc_info.value).lower()


def test_capability_token_default_data_scope():
    """
    Given token without data_scope, when creating CapabilityToken,
    then should use empty list as default
    """
    from backend.models.capability_token import CapabilityToken, TokenLimits

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        expires_at=expires_at
    )

    assert token.data_scope == []


def test_has_capability_success():
    """
    Given token with specific capability, when checking has_capability,
    then should return True
    """
    from backend.models.capability_token import CapabilityToken, TokenLimits

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b", "can_execute:gpt-3.5-turbo"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha"],
        expires_at=expires_at
    )

    assert token.has_capability("can_execute:llama-2-7b") is True
    assert token.has_capability("can_execute:gpt-3.5-turbo") is True


def test_has_capability_missing():
    """
    Given token without specific capability, when checking has_capability,
    then should return False
    """
    from backend.models.capability_token import CapabilityToken, TokenLimits

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha"],
        expires_at=expires_at
    )

    assert token.has_capability("can_execute:gpt-4") is False


def test_has_data_access_success():
    """
    Given token with project in data_scope, when checking has_data_access,
    then should return True
    """
    from backend.models.capability_token import CapabilityToken, TokenLimits

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha", "project-beta"],
        expires_at=expires_at
    )

    assert token.has_data_access("project-alpha") is True
    assert token.has_data_access("project-beta") is True


def test_has_data_access_missing():
    """
    Given token without project in data_scope, when checking has_data_access,
    then should return False
    """
    from backend.models.capability_token import CapabilityToken, TokenLimits

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha"],
        expires_at=expires_at
    )

    assert token.has_data_access("project-gamma") is False


def test_has_data_access_empty_scope():
    """
    Given token with empty data_scope, when checking has_data_access,
    then should return True (no restrictions)
    """
    from backend.models.capability_token import CapabilityToken, TokenLimits

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=[],
        expires_at=expires_at
    )

    # Empty data_scope means no restrictions - access all projects
    assert token.has_data_access("any-project") is True


def test_is_expired_false():
    """
    Given non-expired token, when checking is_expired,
    then should return False
    """
    from backend.models.capability_token import CapabilityToken, TokenLimits

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha"],
        expires_at=expires_at
    )

    assert token.is_expired() is False


def test_token_limits_validation():
    """
    Given valid limits, when creating TokenLimits,
    then should validate constraints
    """
    from backend.models.capability_token import TokenLimits

    limits = TokenLimits(
        max_gpu_minutes=5000,
        max_concurrent_tasks=10
    )

    assert limits.max_gpu_minutes == 5000
    assert limits.max_concurrent_tasks == 10


def test_token_limits_zero_values():
    """
    Given zero limits, when creating TokenLimits,
    then should accept zero as valid
    """
    from backend.models.capability_token import TokenLimits

    limits = TokenLimits(
        max_gpu_minutes=0,
        max_concurrent_tasks=0
    )

    assert limits.max_gpu_minutes == 0
    assert limits.max_concurrent_tasks == 0
