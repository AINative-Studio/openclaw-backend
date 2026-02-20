"""
Test suite for Message Signing Service (E7-S2)

BDD-style tests for Ed25519 message signing and verification.
"""

import pytest
import time
import hashlib
import base64
from cryptography.hazmat.primitives.asymmetric import ed25519

from backend.security.message_signing_service import MessageSigningService
from backend.models.message_envelope import MessageEnvelope
from backend.p2p.libp2p_identity import LibP2PIdentity


class TestMessageSigningService:
    """Test suite for message signing service"""

    @pytest.fixture
    def identity(self):
        """Create a test identity with Ed25519 keypair"""
        identity = LibP2PIdentity()
        identity.generate()
        return identity

    @pytest.fixture
    def signing_service(self, identity):
        """Create message signing service with test identity"""
        return MessageSigningService(identity)

    @pytest.fixture
    def sample_payload(self):
        """Sample message payload for testing"""
        return {
            "type": "heartbeat",
            "data": {
                "status": "active",
                "cpu_usage": 45.2,
                "memory_usage": 67.8
            }
        }

    def test_sign_message(self, signing_service, sample_payload):
        """
        Given message payload, when signing,
        then should return valid Ed25519 signature
        """
        # When
        envelope = signing_service.sign_message(sample_payload)

        # Then
        assert envelope is not None
        assert isinstance(envelope, MessageEnvelope)
        assert envelope.signature is not None
        assert len(envelope.signature) > 0

        # Verify signature is base64 encoded
        try:
            decoded = base64.b64decode(envelope.signature)
            # Ed25519 signatures are 64 bytes
            assert len(decoded) == 64
        except Exception as e:
            pytest.fail(f"Signature is not valid base64: {e}")

    def test_verify_signature(self, signing_service, sample_payload):
        """
        Given signed message, when verifying,
        then should validate signature matches payload
        """
        # Given - sign the message
        envelope = signing_service.sign_message(sample_payload)

        # When - verify the signature
        is_valid = signing_service.verify_signature(envelope, sample_payload)

        # Then
        assert is_valid is True

    def test_reject_tampered_message(self, signing_service, sample_payload):
        """
        Given tampered message, when verifying,
        then should reject with signature error
        """
        # Given - sign the original message
        envelope = signing_service.sign_message(sample_payload)

        # When - tamper with the payload
        tampered_payload = sample_payload.copy()
        tampered_payload["data"]["status"] = "inactive"

        # Then - verification should fail
        is_valid = signing_service.verify_signature(envelope, tampered_payload)
        assert is_valid is False

    def test_signature_includes_timestamp(self, signing_service, sample_payload):
        """
        Given signed message, when checking envelope,
        then should include UTC timestamp
        """
        # Given
        before_time = int(time.time())

        # When
        envelope = signing_service.sign_message(sample_payload)

        # Then
        after_time = int(time.time())
        assert envelope.timestamp is not None
        assert isinstance(envelope.timestamp, int)
        assert before_time <= envelope.timestamp <= after_time

    def test_signature_includes_peer_id(self, signing_service, identity, sample_payload):
        """
        Given signed message, when checking envelope,
        then should include sender peer_id
        """
        # When
        envelope = signing_service.sign_message(sample_payload)

        # Then
        assert envelope.peer_id is not None
        assert envelope.peer_id == identity.peer_id
        assert envelope.peer_id.startswith("12D3KooW")

    def test_payload_hash_is_sha256(self, signing_service, sample_payload):
        """
        Given message payload, when signing,
        then should compute SHA-256 hash with correct format
        """
        # When
        envelope = signing_service.sign_message(sample_payload)

        # Then
        assert envelope.payload_hash is not None
        assert envelope.payload_hash.startswith("sha256:")

        # Verify the hash is correct
        hash_value = envelope.payload_hash.replace("sha256:", "")
        assert len(hash_value) == 64  # SHA-256 hex digest is 64 characters

    def test_verify_with_different_identity_fails(self, signing_service, sample_payload):
        """
        Given message signed by one identity,
        when verifying with different identity's public key,
        then should fail verification
        """
        # Given - sign with first identity
        envelope = signing_service.sign_message(sample_payload)

        # Create a different identity
        different_identity = LibP2PIdentity()
        different_identity.generate()
        different_service = MessageSigningService(different_identity)

        # When - verify with different identity
        is_valid = different_service.verify_signature(envelope, sample_payload)

        # Then
        assert is_valid is False

    def test_tampered_signature_fails_verification(self, signing_service, sample_payload):
        """
        Given message with tampered signature,
        when verifying,
        then should fail verification
        """
        # Given - sign the message
        envelope = signing_service.sign_message(sample_payload)

        # Tamper with signature
        tampered_signature = base64.b64encode(b"tampered" * 8).decode('utf-8')
        envelope.signature = tampered_signature

        # When
        is_valid = signing_service.verify_signature(envelope, sample_payload)

        # Then
        assert is_valid is False

    def test_envelope_serialization(self, signing_service, sample_payload):
        """
        Given signed envelope,
        when converting to dict,
        then should have all required fields
        """
        # When
        envelope = signing_service.sign_message(sample_payload)
        envelope_dict = envelope.model_dump()

        # Then
        assert "payload_hash" in envelope_dict
        assert "peer_id" in envelope_dict
        assert "timestamp" in envelope_dict
        assert "signature" in envelope_dict

    def test_multiple_signatures_with_same_identity(self, signing_service, sample_payload):
        """
        Given same payload signed multiple times,
        when comparing signatures,
        then timestamps should differ but all should verify
        """
        # When
        envelope1 = signing_service.sign_message(sample_payload)
        time.sleep(1)  # Ensure different timestamp
        envelope2 = signing_service.sign_message(sample_payload)

        # Then
        assert envelope1.timestamp != envelope2.timestamp
        assert signing_service.verify_signature(envelope1, sample_payload)
        assert signing_service.verify_signature(envelope2, sample_payload)

    def test_empty_payload_can_be_signed(self, signing_service):
        """
        Given empty payload,
        when signing,
        then should create valid signature
        """
        # Given
        empty_payload = {}

        # When
        envelope = signing_service.sign_message(empty_payload)

        # Then
        assert envelope is not None
        assert signing_service.verify_signature(envelope, empty_payload)

    def test_large_payload_can_be_signed(self, signing_service):
        """
        Given large payload,
        when signing,
        then should create valid signature
        """
        # Given
        large_payload = {
            "type": "data_sync",
            "data": ["item_" + str(i) for i in range(10000)]
        }

        # When
        envelope = signing_service.sign_message(large_payload)

        # Then
        assert envelope is not None
        assert signing_service.verify_signature(envelope, large_payload)

    def test_signature_deterministic_for_same_payload_and_timestamp(
        self, signing_service, sample_payload
    ):
        """
        Given same payload at same timestamp,
        when signing with fixed timestamp,
        then should produce same signature
        """
        # Given - freeze timestamp
        fixed_timestamp = 1708380000

        # When
        envelope1 = signing_service.sign_message(
            sample_payload, timestamp=fixed_timestamp
        )
        envelope2 = signing_service.sign_message(
            sample_payload, timestamp=fixed_timestamp
        )

        # Then
        assert envelope1.signature == envelope2.signature
        assert envelope1.payload_hash == envelope2.payload_hash


class TestMessageEnvelope:
    """Test suite for MessageEnvelope model"""

    def test_envelope_creation(self):
        """
        Given envelope parameters,
        when creating MessageEnvelope,
        then should validate all fields
        """
        # When - use valid 64-character hex hash
        valid_hash = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        envelope = MessageEnvelope(
            payload_hash=valid_hash,
            peer_id="12D3KooWTest",
            timestamp=1708380000,
            signature="base64signature"
        )

        # Then
        assert envelope.payload_hash == valid_hash
        assert envelope.peer_id == "12D3KooWTest"
        assert envelope.timestamp == 1708380000
        assert envelope.signature == "base64signature"

    def test_envelope_requires_all_fields(self):
        """
        Given missing required fields,
        when creating MessageEnvelope,
        then should raise validation error
        """
        # When/Then
        with pytest.raises(Exception):  # Pydantic validation error
            MessageEnvelope(
                payload_hash="sha256:abc123",
                peer_id="12D3KooWTest"
                # Missing timestamp and signature
            )

    def test_envelope_validates_hash_format(self):
        """
        Given invalid payload_hash format,
        when creating MessageEnvelope,
        then should raise validation error
        """
        # When/Then - missing prefix
        with pytest.raises(Exception):
            MessageEnvelope(
                payload_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                peer_id="12D3KooWTest",
                timestamp=1708380000,
                signature="sig"
            )

        # When/Then - wrong hash length
        with pytest.raises(Exception):
            MessageEnvelope(
                payload_hash="sha256:abc",
                peer_id="12D3KooWTest",
                timestamp=1708380000,
                signature="sig"
            )

        # When/Then - non-hex characters
        with pytest.raises(Exception):
            MessageEnvelope(
                payload_hash="sha256:ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ",
                peer_id="12D3KooWTest",
                timestamp=1708380000,
                signature="sig"
            )

    def test_envelope_validates_peer_id_format(self):
        """
        Given invalid peer_id format,
        when creating MessageEnvelope,
        then should raise validation error
        """
        valid_hash = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

        # When/Then - missing prefix
        with pytest.raises(Exception):
            MessageEnvelope(
                payload_hash=valid_hash,
                peer_id="InvalidPeerID",
                timestamp=1708380000,
                signature="sig"
            )


class TestMessageSigningServiceExtended:
    """Extended test suite for message signing service"""

    @pytest.fixture
    def identity(self):
        """Create a test identity with Ed25519 keypair"""
        identity = LibP2PIdentity()
        identity.generate()
        return identity

    @pytest.fixture
    def signing_service(self, identity):
        """Create message signing service with test identity"""
        return MessageSigningService(identity)

    def test_service_requires_valid_identity(self):
        """
        Given identity without private key,
        when creating MessageSigningService,
        then should raise ValueError
        """
        # Given
        empty_identity = LibP2PIdentity()

        # When/Then
        with pytest.raises(ValueError, match="must have a private key"):
            MessageSigningService(empty_identity)

    def test_verify_signature_with_public_key(self, signing_service, identity):
        """
        Given signed message,
        when verifying with specific public key,
        then should validate successfully
        """
        # Given
        payload = {"type": "test", "data": "value"}
        envelope = signing_service.sign_message(payload)

        # When
        is_valid = signing_service.verify_signature_with_public_key(
            envelope, payload, identity.public_key
        )

        # Then
        assert is_valid is True

    def test_verify_with_wrong_public_key_fails(self, signing_service):
        """
        Given signed message,
        when verifying with wrong public key,
        then should fail verification
        """
        # Given
        payload = {"type": "test", "data": "value"}
        envelope = signing_service.sign_message(payload)

        # Create different identity
        different_identity = LibP2PIdentity()
        different_identity.generate()

        # When
        is_valid = signing_service.verify_signature_with_public_key(
            envelope, payload, different_identity.public_key
        )

        # Then
        assert is_valid is False

    def test_public_key_hex_property(self, signing_service, identity):
        """
        Given signing service,
        when accessing public_key_hex,
        then should return hex-encoded public key
        """
        # When
        public_key_hex = signing_service.public_key_hex

        # Then
        assert public_key_hex is not None
        assert len(public_key_hex) == 64  # Ed25519 public key is 32 bytes = 64 hex chars
        assert public_key_hex == identity.export_public_key().hex()

    def test_peer_id_property(self, signing_service, identity):
        """
        Given signing service,
        when accessing peer_id,
        then should return identity's peer_id
        """
        # When
        peer_id = signing_service.peer_id

        # Then
        assert peer_id == identity.peer_id
        assert peer_id.startswith("12D3KooW")

    def test_verify_with_malformed_base64_signature(self, signing_service):
        """
        Given envelope with malformed base64 signature,
        when verifying,
        then should return False
        """
        # Given
        payload = {"type": "test"}
        envelope = signing_service.sign_message(payload)
        envelope.signature = "not-valid-base64!@#$%"

        # When
        is_valid = signing_service.verify_signature(envelope, payload)

        # Then
        assert is_valid is False

    def test_verify_signature_with_public_key_malformed_signature(self, signing_service, identity):
        """
        Given envelope with malformed signature,
        when verifying with public key,
        then should return False
        """
        # Given
        payload = {"type": "test"}
        envelope = signing_service.sign_message(payload)
        envelope.signature = "not-valid-base64!@#$%"

        # When
        is_valid = signing_service.verify_signature_with_public_key(
            envelope, payload, identity.public_key
        )

        # Then
        assert is_valid is False

    def test_verify_signature_with_public_key_hash_mismatch(self, signing_service, identity):
        """
        Given envelope with payload that doesn't match hash,
        when verifying with public key,
        then should return False
        """
        # Given
        original_payload = {"type": "test", "data": "original"}
        envelope = signing_service.sign_message(original_payload)

        # Different payload
        different_payload = {"type": "test", "data": "modified"}

        # When
        is_valid = signing_service.verify_signature_with_public_key(
            envelope, different_payload, identity.public_key
        )

        # Then
        assert is_valid is False
