"""
Tests for Message Verification Service (E7-S3)

BDD-style tests for signature verification, public key lookup,
and message authenticity validation.
"""

import pytest
import time
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

from backend.security.message_verification_service import MessageVerificationService
from backend.security.peer_key_store import PeerKeyStore


@pytest.fixture
def peer_key_store():
    """Create in-memory peer key store for testing."""
    return PeerKeyStore()


@pytest.fixture
def verification_service(peer_key_store):
    """Create message verification service."""
    return MessageVerificationService(peer_key_store)


@pytest.fixture
def sender_keypair():
    """Generate Ed25519 keypair for sender."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def valid_message_envelope(sender_keypair):
    """Create a valid signed message envelope."""
    private_key, public_key = sender_keypair
    sender_peer_id = "12D3KooWTestSender123"

    # Create message payload
    payload = b"Hello, this is a test message"
    timestamp = int(time.time())

    # Sign the payload
    signature = private_key.sign(payload)

    return {
        "sender_peer_id": sender_peer_id,
        "payload": payload,
        "signature": signature,
        "timestamp": timestamp,
        "public_key": public_key
    }


class TestMessageVerificationBasics:
    """Test basic message verification functionality."""

    def test_verify_valid_signature(self, verification_service, peer_key_store, valid_message_envelope):
        """
        Given a correctly signed message
        When verifying the signature
        Then should return True
        """
        # Arrange
        envelope = valid_message_envelope
        peer_key_store.store_public_key(
            envelope["sender_peer_id"],
            envelope["public_key"]
        )

        # Act
        result = verification_service.verify_message(
            sender_peer_id=envelope["sender_peer_id"],
            payload=envelope["payload"],
            signature=envelope["signature"],
            timestamp=envelope["timestamp"]
        )

        # Assert
        assert result is True

    def test_reject_invalid_signature(self, verification_service, peer_key_store, valid_message_envelope):
        """
        Given a message with invalid signature
        When verifying the signature
        Then should return False and log warning
        """
        # Arrange
        envelope = valid_message_envelope
        peer_key_store.store_public_key(
            envelope["sender_peer_id"],
            envelope["public_key"]
        )

        # Tamper with signature (flip last byte)
        tampered_signature = bytearray(envelope["signature"])
        tampered_signature[-1] ^= 0xFF
        tampered_signature = bytes(tampered_signature)

        # Act
        result = verification_service.verify_message(
            sender_peer_id=envelope["sender_peer_id"],
            payload=envelope["payload"],
            signature=tampered_signature,
            timestamp=envelope["timestamp"]
        )

        # Assert
        assert result is False

    def test_reject_tampered_payload(self, verification_service, peer_key_store, valid_message_envelope):
        """
        Given a message with tampered payload
        When verifying the signature
        Then should return False
        """
        # Arrange
        envelope = valid_message_envelope
        peer_key_store.store_public_key(
            envelope["sender_peer_id"],
            envelope["public_key"]
        )

        # Tamper with payload
        tampered_payload = b"Tampered message"

        # Act
        result = verification_service.verify_message(
            sender_peer_id=envelope["sender_peer_id"],
            payload=tampered_payload,
            signature=envelope["signature"],
            timestamp=envelope["timestamp"]
        )

        # Assert
        assert result is False


class TestPeerKeyLookup:
    """Test public key lookup and peer validation."""

    def test_reject_unknown_sender(self, verification_service, valid_message_envelope):
        """
        Given a message from unknown peer
        When verifying the signature
        Then should reject with unknown peer error
        """
        # Arrange
        envelope = valid_message_envelope
        # Don't store the public key

        # Act & Assert
        with pytest.raises(ValueError, match="Unknown peer"):
            verification_service.verify_message(
                sender_peer_id=envelope["sender_peer_id"],
                payload=envelope["payload"],
                signature=envelope["signature"],
                timestamp=envelope["timestamp"]
            )

    def test_cache_public_key_lookup(self, verification_service, peer_key_store, sender_keypair):
        """
        Given a stored public key
        When looking up multiple times
        Then should use cache for performance
        """
        # Arrange
        private_key, public_key = sender_keypair
        peer_id = "12D3KooWCachedPeer"
        peer_key_store.store_public_key(peer_id, public_key)

        # Act
        key1 = verification_service._get_peer_public_key(peer_id)
        key2 = verification_service._get_peer_public_key(peer_id)

        # Assert
        assert key1 == key2
        # Verify cache hit (second lookup should be from cache)
        assert verification_service._key_cache_hits > 0


class TestTimestampValidation:
    """Test timestamp validation for message freshness."""

    def test_reject_expired_timestamp(self, verification_service, peer_key_store, sender_keypair):
        """
        Given a message with old timestamp (>5 minutes)
        When verifying the signature
        Then should reject with timestamp error
        """
        # Arrange
        private_key, public_key = sender_keypair
        sender_peer_id = "12D3KooWOldMessage"
        peer_key_store.store_public_key(sender_peer_id, public_key)

        # Create message with old timestamp (6 minutes ago)
        old_timestamp = int((datetime.now() - timedelta(minutes=6)).timestamp())
        payload = b"Old message"
        signature = private_key.sign(payload)

        # Act & Assert
        with pytest.raises(ValueError, match="Message timestamp expired"):
            verification_service.verify_message(
                sender_peer_id=sender_peer_id,
                payload=payload,
                signature=signature,
                timestamp=old_timestamp
            )

    def test_accept_recent_timestamp(self, verification_service, peer_key_store, sender_keypair):
        """
        Given a message with recent timestamp (<5 minutes)
        When verifying the signature
        Then should accept the message
        """
        # Arrange
        private_key, public_key = sender_keypair
        sender_peer_id = "12D3KooWRecentMessage"
        peer_key_store.store_public_key(sender_peer_id, public_key)

        # Create message with recent timestamp (1 minute ago)
        recent_timestamp = int((datetime.now() - timedelta(minutes=1)).timestamp())
        payload = b"Recent message"
        signature = private_key.sign(payload)

        # Act
        result = verification_service.verify_message(
            sender_peer_id=sender_peer_id,
            payload=payload,
            signature=signature,
            timestamp=recent_timestamp
        )

        # Assert
        assert result is True

    def test_reject_future_timestamp(self, verification_service, peer_key_store, sender_keypair):
        """
        Given a message with future timestamp
        When verifying the signature
        Then should reject with timestamp error
        """
        # Arrange
        private_key, public_key = sender_keypair
        sender_peer_id = "12D3KooWFutureMessage"
        peer_key_store.store_public_key(sender_peer_id, public_key)

        # Create message with future timestamp (10 minutes from now)
        future_timestamp = int((datetime.now() + timedelta(minutes=10)).timestamp())
        payload = b"Future message"
        signature = private_key.sign(payload)

        # Act & Assert
        with pytest.raises(ValueError, match="Message timestamp is in the future"):
            verification_service.verify_message(
                sender_peer_id=sender_peer_id,
                payload=payload,
                signature=signature,
                timestamp=future_timestamp
            )


class TestPerformance:
    """Test verification performance requirements."""

    def test_verify_performance(self, verification_service, peer_key_store, sender_keypair):
        """
        Given 1000 messages
        When verifying each message
        Then should complete in < 1 second
        """
        # Arrange
        private_key, public_key = sender_keypair
        sender_peer_id = "12D3KooWPerfTest"
        peer_key_store.store_public_key(sender_peer_id, public_key)

        # Create 1000 signed messages
        messages = []
        for i in range(1000):
            payload = f"Message {i}".encode()
            signature = private_key.sign(payload)
            timestamp = int(time.time())
            messages.append((payload, signature, timestamp))

        # Act
        start_time = time.time()
        for payload, signature, timestamp in messages:
            verification_service.verify_message(
                sender_peer_id=sender_peer_id,
                payload=payload,
                signature=signature,
                timestamp=timestamp
            )
        end_time = time.time()

        # Assert
        duration = end_time - start_time
        assert duration < 1.0, f"Verification took {duration:.3f}s, expected < 1.0s"


class TestPeerKeyStore:
    """Test public key storage and retrieval."""

    def test_store_and_retrieve_public_key(self, peer_key_store, sender_keypair):
        """
        Given a peer public key
        When storing and retrieving
        Then should return the same key
        """
        # Arrange
        _, public_key = sender_keypair
        peer_id = "12D3KooWStoreTest"

        # Act
        peer_key_store.store_public_key(peer_id, public_key)
        retrieved_key = peer_key_store.get_public_key(peer_id)

        # Assert
        assert retrieved_key == public_key

    def test_retrieve_nonexistent_key(self, peer_key_store):
        """
        Given a peer ID with no stored key
        When retrieving the key
        Then should return None
        """
        # Act
        key = peer_key_store.get_public_key("12D3KooWNonexistent")

        # Assert
        assert key is None

    def test_update_public_key(self, peer_key_store):
        """
        Given an existing peer public key
        When updating with new key
        Then should store the new key
        """
        # Arrange
        peer_id = "12D3KooWUpdateTest"
        old_key = ed25519.Ed25519PrivateKey.generate().public_key()
        new_key = ed25519.Ed25519PrivateKey.generate().public_key()

        # Act
        peer_key_store.store_public_key(peer_id, old_key)
        peer_key_store.store_public_key(peer_id, new_key)
        retrieved_key = peer_key_store.get_public_key(peer_id)

        # Assert
        assert retrieved_key == new_key

    def test_remove_public_key(self, peer_key_store, sender_keypair):
        """
        Given a stored public key
        When removing the key
        Then should no longer be retrievable
        """
        # Arrange
        _, public_key = sender_keypair
        peer_id = "12D3KooWRemoveTest"
        peer_key_store.store_public_key(peer_id, public_key)

        # Act
        peer_key_store.remove_public_key(peer_id)
        retrieved_key = peer_key_store.get_public_key(peer_id)

        # Assert
        assert retrieved_key is None

    def test_remove_nonexistent_key(self, peer_key_store):
        """
        Given a peer ID with no stored key
        When removing the key
        Then should return False
        """
        # Act
        result = peer_key_store.remove_public_key("12D3KooWNonexistent")

        # Assert
        assert result is False

    def test_has_public_key(self, peer_key_store, sender_keypair):
        """
        Given stored and non-stored peer IDs
        When checking if keys exist
        Then should return correct status
        """
        # Arrange
        _, public_key = sender_keypair
        peer_id = "12D3KooWHasKeyTest"

        # Act & Assert
        assert peer_key_store.has_public_key(peer_id) is False
        peer_key_store.store_public_key(peer_id, public_key)
        assert peer_key_store.has_public_key(peer_id) is True

    def test_clear_store(self, peer_key_store, sender_keypair):
        """
        Given a store with multiple keys
        When clearing the store
        Then all keys should be removed
        """
        # Arrange
        _, public_key = sender_keypair
        peer_key_store.store_public_key("12D3KooWPeer1", public_key)
        peer_key_store.store_public_key("12D3KooWPeer2", public_key)

        # Act
        peer_key_store.clear()

        # Assert
        assert peer_key_store.count() == 0
        assert peer_key_store.has_public_key("12D3KooWPeer1") is False

    def test_count_keys(self, peer_key_store, sender_keypair):
        """
        Given multiple stored keys
        When counting keys
        Then should return correct count
        """
        # Arrange
        _, public_key = sender_keypair

        # Act & Assert
        assert peer_key_store.count() == 0
        peer_key_store.store_public_key("12D3KooWPeer1", public_key)
        assert peer_key_store.count() == 1
        peer_key_store.store_public_key("12D3KooWPeer2", public_key)
        assert peer_key_store.count() == 2

    def test_get_all_peer_ids(self, peer_key_store, sender_keypair):
        """
        Given multiple stored keys
        When getting all peer IDs
        Then should return complete list
        """
        # Arrange
        _, public_key = sender_keypair
        peer_key_store.store_public_key("12D3KooWPeer1", public_key)
        peer_key_store.store_public_key("12D3KooWPeer2", public_key)

        # Act
        peer_ids = peer_key_store.get_all_peer_ids()

        # Assert
        assert len(peer_ids) == 2
        assert "12D3KooWPeer1" in peer_ids
        assert "12D3KooWPeer2" in peer_ids

    def test_import_export_public_key_bytes(self, peer_key_store, sender_keypair):
        """
        Given a public key
        When exporting and importing as bytes
        Then should preserve the key
        """
        # Arrange
        _, public_key = sender_keypair
        peer_id = "12D3KooWImportExport"
        peer_key_store.store_public_key(peer_id, public_key)

        # Act - Export
        key_bytes = peer_key_store.export_public_key_bytes(peer_id)

        # Clear and re-import
        peer_key_store.clear()
        peer_key_store.import_public_key_bytes(peer_id, key_bytes)

        # Assert
        imported_key = peer_key_store.get_public_key(peer_id)
        assert imported_key is not None
        # Verify keys match by comparing bytes
        original_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        imported_bytes = imported_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        assert original_bytes == imported_bytes

    def test_export_nonexistent_key(self, peer_key_store):
        """
        Given a non-existent peer ID
        When exporting key bytes
        Then should return None
        """
        # Act
        key_bytes = peer_key_store.export_public_key_bytes("12D3KooWNonexistent")

        # Assert
        assert key_bytes is None

    def test_import_invalid_key_bytes_length(self, peer_key_store):
        """
        Given invalid key bytes (wrong length)
        When importing
        Then should raise ValueError
        """
        # Act & Assert
        with pytest.raises(ValueError, match="must be 32 bytes"):
            peer_key_store.import_public_key_bytes("12D3KooWInvalid", b"too_short")

    def test_import_valid_weak_key_bytes(self, peer_key_store):
        """
        Given valid but weak key bytes (all zeros)
        When importing
        Then should successfully import
        """
        # Note: Ed25519 accepts 32 zero bytes as a valid (though cryptographically weak) key
        # This test verifies the import mechanism works correctly
        # Act
        peer_key_store.import_public_key_bytes("12D3KooWWeakKey", b"\x00" * 32)

        # Assert
        key = peer_key_store.get_public_key("12D3KooWWeakKey")
        assert key is not None

    def test_store_empty_peer_id(self, peer_key_store, sender_keypair):
        """
        Given an empty peer ID
        When storing a key
        Then should raise ValueError
        """
        # Arrange
        _, public_key = sender_keypair

        # Act & Assert
        with pytest.raises(ValueError, match="peer_id cannot be empty"):
            peer_key_store.store_public_key("", public_key)

    def test_store_invalid_public_key_type(self, peer_key_store):
        """
        Given an invalid public key type
        When storing
        Then should raise ValueError
        """
        # Act & Assert
        with pytest.raises(ValueError, match="must be an Ed25519PublicKey"):
            peer_key_store.store_public_key("12D3KooWInvalid", "not_a_key")


class TestSecurityFeatures:
    """Test security-specific features."""

    def test_constant_time_signature_comparison(self, verification_service, peer_key_store, sender_keypair):
        """
        Given valid and invalid signatures
        When verifying signatures
        Then should use constant-time comparison
        """
        # This is more of a documentation test - the implementation should use
        # cryptography library's built-in constant-time comparison
        # We verify that the service handles both cases consistently

        # Arrange
        private_key, public_key = sender_keypair
        peer_id = "12D3KooWConstantTime"
        peer_key_store.store_public_key(peer_id, public_key)

        payload = b"Test message"
        valid_signature = private_key.sign(payload)
        invalid_signature = b"\x00" * 64
        timestamp = int(time.time())

        # Act & Assert
        assert verification_service.verify_message(peer_id, payload, valid_signature, timestamp) is True
        assert verification_service.verify_message(peer_id, payload, invalid_signature, timestamp) is False

    def test_rate_limiting_on_verification_failures(self, verification_service, peer_key_store, sender_keypair):
        """
        Given multiple verification failures from same peer
        When checking failure count
        Then should track failures for rate limiting
        """
        # Arrange
        private_key, public_key = sender_keypair
        peer_id = "12D3KooWRateLimit"
        peer_key_store.store_public_key(peer_id, public_key)

        payload = b"Test"
        invalid_signature = b"\x00" * 64
        timestamp = int(time.time())

        # Act - Generate multiple failures
        for _ in range(5):
            verification_service.verify_message(peer_id, payload, invalid_signature, timestamp)

        # Assert
        failures = verification_service.get_failure_count(peer_id)
        assert failures == 5

    def test_reset_failure_count(self, verification_service, peer_key_store, sender_keypair):
        """
        Given a peer with failure count
        When resetting the count
        Then should reset to zero
        """
        # Arrange
        private_key, public_key = sender_keypair
        peer_id = "12D3KooWResetCount"
        peer_key_store.store_public_key(peer_id, public_key)

        payload = b"Test"
        invalid_signature = b"\x00" * 64
        timestamp = int(time.time())

        # Generate some failures
        for _ in range(3):
            verification_service.verify_message(peer_id, payload, invalid_signature, timestamp)

        # Act
        verification_service.reset_failure_count(peer_id)

        # Assert
        assert verification_service.get_failure_count(peer_id) == 0

    def test_clear_cache(self, verification_service, peer_key_store, sender_keypair):
        """
        Given cached public keys
        When clearing cache
        Then should remove all cached keys
        """
        # Arrange
        private_key, public_key = sender_keypair
        peer_id = "12D3KooWClearCache"
        peer_key_store.store_public_key(peer_id, public_key)

        # Trigger cache by looking up key
        verification_service._get_peer_public_key(peer_id)

        # Act
        verification_service.clear_cache()

        # Assert
        stats = verification_service.get_cache_stats()
        assert stats["cache_size"] == 0
        assert stats["cache_hits"] == 0

    def test_get_cache_stats(self, verification_service, peer_key_store, sender_keypair):
        """
        Given cache operations
        When getting cache stats
        Then should return accurate statistics
        """
        # Arrange
        private_key, public_key = sender_keypair
        peer_id = "12D3KooWCacheStats"
        peer_key_store.store_public_key(peer_id, public_key)

        # Act - Generate cache hits
        verification_service._get_peer_public_key(peer_id)  # First lookup (cache miss)
        verification_service._get_peer_public_key(peer_id)  # Second lookup (cache hit)
        verification_service._get_peer_public_key(peer_id)  # Third lookup (cache hit)

        # Assert
        stats = verification_service.get_cache_stats()
        assert stats["cache_size"] == 1
        assert stats["cache_hits"] == 2

    def test_verification_exception_handling(self, verification_service, peer_key_store):
        """
        Given an exception during verification
        When handling the exception
        Then should track failure and return False
        """
        # Arrange
        peer_id = "12D3KooWException"
        # Store an invalid key by manipulating internals
        # (This is a bit contrived but tests exception handling)
        invalid_key = ed25519.Ed25519PrivateKey.generate().public_key()
        peer_key_store.store_public_key(peer_id, invalid_key)

        payload = b"Test"
        # Create an invalid signature (wrong length)
        invalid_signature = b"invalid"
        timestamp = int(time.time())

        # Act
        result = verification_service.verify_message(peer_id, payload, invalid_signature, timestamp)

        # Assert
        assert result is False
        assert verification_service.get_failure_count(peer_id) == 1

    def test_export_public_key_bytes(self, peer_key_store, sender_keypair):
        """
        Given a stored public key
        When exporting as bytes
        Then should return raw Ed25519 public key bytes
        """
        # Arrange
        _, public_key = sender_keypair
        peer_id = "12D3KooWExportTest"
        peer_key_store.store_public_key(peer_id, public_key)

        # Act
        key_bytes = peer_key_store.export_public_key_bytes(peer_id)

        # Assert
        assert len(key_bytes) == 32  # Ed25519 public keys are 32 bytes
        # Verify it matches the original
        expected_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        assert key_bytes == expected_bytes

    def test_high_failure_count_warning(self, verification_service, peer_key_store, sender_keypair):
        """
        Given a peer with >10 failures
        When tracking failures
        Then should log warning message
        """
        # Arrange
        private_key, public_key = sender_keypair
        peer_id = "12D3KooWHighFailures"
        peer_key_store.store_public_key(peer_id, public_key)

        payload = b"Test"
        invalid_signature = b"\x00" * 64
        timestamp = int(time.time())

        # Act - Generate >10 failures
        for _ in range(12):
            verification_service.verify_message(peer_id, payload, invalid_signature, timestamp)

        # Assert
        failures = verification_service.get_failure_count(peer_id)
        assert failures == 12
