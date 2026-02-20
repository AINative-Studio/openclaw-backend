"""
Tests for TokenService (E7-S1)

BDD-style tests for JWT token encoding/decoding service.
Refs: OpenCLAW P2P Swarm PRD Section on Security, Backlog E7-S1
"""

import pytest
import time
from datetime import datetime, timedelta


def test_create_capability_token():
    """
    Given peer capabilities, when creating token,
    then should encode JWT with claims
    """
    from backend.security.token_service import TokenService
    from backend.models.capability_token import CapabilityToken, TokenLimits

    service = TokenService(secret_key="test-secret-key-12345")

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token_model = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b", "can_execute:gpt-3.5-turbo"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha", "project-beta"],
        expires_at=expires_at
    )

    encoded_token = service.encode_token(token_model)

    assert isinstance(encoded_token, str)
    assert len(encoded_token) > 0
    # JWT format: header.payload.signature
    assert encoded_token.count('.') == 2


def test_verify_capability_token():
    """
    Given signed token, when verifying,
    then should validate signature and expiration
    """
    from backend.security.token_service import TokenService
    from backend.models.capability_token import CapabilityToken, TokenLimits

    service = TokenService(secret_key="test-secret-key-12345")

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token_model = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha"],
        expires_at=expires_at
    )

    encoded_token = service.encode_token(token_model)
    decoded_token = service.decode_token(encoded_token)

    assert decoded_token.peer_id == "12D3KooWEyopopk1234567890"
    assert "can_execute:llama-2-7b" in decoded_token.capabilities
    assert decoded_token.limits.max_gpu_minutes == 1000
    assert decoded_token.limits.max_concurrent_tasks == 3
    assert decoded_token.data_scope == ["project-alpha"]
    assert decoded_token.expires_at == expires_at


def test_check_capability_allowed():
    """
    Given token with GPU capability, when checking,
    then should allow GPU task execution
    """
    from backend.security.token_service import TokenService
    from backend.models.capability_token import CapabilityToken, TokenLimits

    service = TokenService(secret_key="test-secret-key-12345")

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token_model = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b", "can_execute:gpt-3.5-turbo"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha"],
        expires_at=expires_at
    )

    encoded_token = service.encode_token(token_model)
    is_allowed = service.check_capability(encoded_token, "can_execute:llama-2-7b")

    assert is_allowed is True


def test_token_expiration():
    """
    Given expired token, when validating,
    then should raise TokenExpiredError
    """
    from backend.security.token_service import TokenService, TokenExpiredError
    from backend.models.capability_token import CapabilityToken, TokenLimits

    service = TokenService(secret_key="test-secret-key-12345")

    # Create token that expires in 1 second
    expires_at = int((datetime.utcnow() + timedelta(seconds=1)).timestamp())

    token_model = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha"],
        expires_at=expires_at
    )

    encoded_token = service.encode_token(token_model)

    # Wait for token to expire
    time.sleep(2)

    with pytest.raises(TokenExpiredError) as exc_info:
        service.decode_token(encoded_token)

    assert "expired" in str(exc_info.value).lower()


def test_missing_required_capability():
    """
    Given token without required capability, when checking,
    then should return False
    """
    from backend.security.token_service import TokenService
    from backend.models.capability_token import CapabilityToken, TokenLimits

    service = TokenService(secret_key="test-secret-key-12345")

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token_model = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha"],
        expires_at=expires_at
    )

    encoded_token = service.encode_token(token_model)
    is_allowed = service.check_capability(encoded_token, "can_execute:gpt-4")

    assert is_allowed is False


def test_invalid_token_signature():
    """
    Given token with invalid signature, when decoding,
    then should raise InvalidTokenError
    """
    from backend.security.token_service import TokenService, InvalidTokenError

    service = TokenService(secret_key="test-secret-key-12345")

    # Malformed token
    invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature"

    with pytest.raises(InvalidTokenError):
        service.decode_token(invalid_token)


def test_wrong_secret_key():
    """
    Given token signed with different key, when decoding,
    then should raise InvalidTokenError
    """
    from backend.security.token_service import TokenService, InvalidTokenError
    from backend.models.capability_token import CapabilityToken, TokenLimits

    service1 = TokenService(secret_key="secret-key-1")
    service2 = TokenService(secret_key="secret-key-2")

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token_model = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha"],
        expires_at=expires_at
    )

    encoded_token = service1.encode_token(token_model)

    with pytest.raises(InvalidTokenError):
        service2.decode_token(encoded_token)


def test_check_data_scope_allowed():
    """
    Given token with project in data_scope, when checking access,
    then should return True
    """
    from backend.security.token_service import TokenService
    from backend.models.capability_token import CapabilityToken, TokenLimits

    service = TokenService(secret_key="test-secret-key-12345")

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token_model = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha", "project-beta"],
        expires_at=expires_at
    )

    encoded_token = service.encode_token(token_model)
    has_access = service.check_data_access(encoded_token, "project-alpha")

    assert has_access is True


def test_check_data_scope_denied():
    """
    Given token without project in data_scope, when checking access,
    then should return False
    """
    from backend.security.token_service import TokenService
    from backend.models.capability_token import CapabilityToken, TokenLimits

    service = TokenService(secret_key="test-secret-key-12345")

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token_model = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha"],
        expires_at=expires_at
    )

    encoded_token = service.encode_token(token_model)
    has_access = service.check_data_access(encoded_token, "project-gamma")

    assert has_access is False


def test_token_with_rs256_algorithm():
    """
    Given RS256 algorithm with public/private keys, when encoding/decoding,
    then should work with asymmetric encryption
    """
    from backend.security.token_service import TokenService
    from backend.models.capability_token import CapabilityToken, TokenLimits
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend

    # Generate RSA key pair
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    service = TokenService(
        secret_key=private_pem.decode(),
        algorithm="RS256",
        public_key=public_pem.decode()
    )

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token_model = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha"],
        expires_at=expires_at
    )

    encoded_token = service.encode_token(token_model)
    decoded_token = service.decode_token(encoded_token)

    assert decoded_token.peer_id == "12D3KooWEyopopk1234567890"


def test_get_token_claims():
    """
    Given encoded token, when getting claims without verification,
    then should return payload data
    """
    from backend.security.token_service import TokenService
    from backend.models.capability_token import CapabilityToken, TokenLimits

    service = TokenService(secret_key="test-secret-key-12345")

    expires_at = int((datetime.utcnow() + timedelta(hours=1)).timestamp())

    token_model = CapabilityToken(
        peer_id="12D3KooWEyopopk1234567890",
        capabilities=["can_execute:llama-2-7b"],
        limits=TokenLimits(max_gpu_minutes=1000, max_concurrent_tasks=3),
        data_scope=["project-alpha"],
        expires_at=expires_at
    )

    encoded_token = service.encode_token(token_model)
    claims = service.get_token_claims(encoded_token)

    assert claims["peer_id"] == "12D3KooWEyopopk1234567890"
    assert "can_execute:llama-2-7b" in claims["capabilities"]
    assert claims["limits"]["max_gpu_minutes"] == 1000
