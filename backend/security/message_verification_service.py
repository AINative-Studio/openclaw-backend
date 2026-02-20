"""
Message Verification Service (E7-S3)

Verifies Ed25519 signatures on received messages to ensure authenticity.
Implements constant-time comparison, timestamp validation, and rate limiting.
"""

from typing import Dict
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature
import logging
import hmac

from backend.security.peer_key_store import PeerKeyStore

logger = logging.getLogger(__name__)


class MessageVerificationService:
    """
    Verifies message signatures using Ed25519 cryptography.

    Features:
    - Ed25519 signature verification
    - Public key caching for performance
    - Timestamp validation (reject messages >5 minutes old)
    - Rate limiting tracking for failed verifications
    - Constant-time signature comparison (via cryptography library)

    Security:
    - Messages older than 5 minutes are rejected
    - Messages with future timestamps are rejected
    - Failed verification attempts are tracked per peer
    - Uses cryptography library's constant-time comparison
    """

    # Maximum message age in seconds (5 minutes)
    MAX_MESSAGE_AGE_SECONDS = 300

    # Maximum clock skew tolerance in seconds (30 seconds)
    MAX_CLOCK_SKEW_SECONDS = 30

    def __init__(self, peer_key_store: PeerKeyStore):
        """
        Initialize message verification service.

        Args:
            peer_key_store: Storage for peer public keys
        """
        self._peer_key_store = peer_key_store
        self._key_cache: Dict[str, ed25519.Ed25519PublicKey] = {}
        self._key_cache_hits = 0
        self._failure_counts: Dict[str, int] = {}
        logger.info("MessageVerificationService initialized")

    def verify_message(
        self,
        sender_peer_id: str,
        payload: bytes,
        signature: bytes,
        timestamp: int
    ) -> bool:
        """
        Verify a message signature.

        Args:
            sender_peer_id: Peer ID of the sender
            payload: Message payload bytes
            signature: Ed25519 signature bytes (64 bytes)
            timestamp: Unix timestamp when message was signed

        Returns:
            True if signature is valid, False otherwise

        Raises:
            ValueError: If sender is unknown or timestamp is invalid
        """
        # Validate timestamp first (fail fast)
        self._validate_timestamp(timestamp)

        # Get sender's public key
        public_key = self._get_peer_public_key(sender_peer_id)
        if public_key is None:
            logger.warning(f"Unknown peer: {sender_peer_id}")
            raise ValueError(f"Unknown peer: {sender_peer_id}")

        # Verify signature using Ed25519
        try:
            public_key.verify(signature, payload)
            logger.debug(f"Signature verified for peer {sender_peer_id}")
            # Reset failure count on success
            self._failure_counts[sender_peer_id] = 0
            return True
        except InvalidSignature:
            logger.warning(f"Invalid signature from peer {sender_peer_id}")
            self._track_verification_failure(sender_peer_id)
            return False
        except Exception as e:
            logger.error(f"Signature verification error for peer {sender_peer_id}: {e}")
            self._track_verification_failure(sender_peer_id)
            return False

    def _get_peer_public_key(self, peer_id: str) -> ed25519.Ed25519PublicKey:
        """
        Get peer's public key with caching.

        Args:
            peer_id: Peer ID to lookup

        Returns:
            Ed25519 public key or None if not found
        """
        # Check cache first
        if peer_id in self._key_cache:
            self._key_cache_hits += 1
            return self._key_cache[peer_id]

        # Lookup from store
        public_key = self._peer_key_store.get_public_key(peer_id)
        if public_key:
            # Cache for future lookups
            self._key_cache[peer_id] = public_key
            logger.debug(f"Cached public key for peer {peer_id}")

        return public_key

    def _validate_timestamp(self, timestamp: int) -> None:
        """
        Validate message timestamp.

        Args:
            timestamp: Unix timestamp to validate

        Raises:
            ValueError: If timestamp is too old or in the future
        """
        current_time = datetime.now()
        message_time = datetime.fromtimestamp(timestamp)

        # Check if message is too old
        age = (current_time - message_time).total_seconds()
        if age > self.MAX_MESSAGE_AGE_SECONDS:
            raise ValueError(
                f"Message timestamp expired: {age:.1f}s old "
                f"(max {self.MAX_MESSAGE_AGE_SECONDS}s)"
            )

        # Check if message is from the future (with clock skew tolerance)
        if message_time > current_time + timedelta(seconds=self.MAX_CLOCK_SKEW_SECONDS):
            raise ValueError(
                f"Message timestamp is in the future: {message_time} "
                f"(current: {current_time})"
            )

    def _track_verification_failure(self, peer_id: str) -> None:
        """
        Track verification failures for rate limiting.

        Args:
            peer_id: Peer ID that failed verification
        """
        if peer_id not in self._failure_counts:
            self._failure_counts[peer_id] = 0
        self._failure_counts[peer_id] += 1

        failure_count = self._failure_counts[peer_id]
        if failure_count > 10:
            logger.warning(
                f"Peer {peer_id} has {failure_count} verification failures - "
                "consider rate limiting or blocking"
            )

    def get_failure_count(self, peer_id: str) -> int:
        """
        Get verification failure count for a peer.

        Args:
            peer_id: Peer ID to check

        Returns:
            Number of verification failures
        """
        return self._failure_counts.get(peer_id, 0)

    def reset_failure_count(self, peer_id: str) -> None:
        """
        Reset verification failure count for a peer.

        Args:
            peer_id: Peer ID to reset
        """
        if peer_id in self._failure_counts:
            del self._failure_counts[peer_id]
            logger.debug(f"Reset failure count for peer {peer_id}")

    def clear_cache(self) -> None:
        """Clear the public key cache."""
        cache_size = len(self._key_cache)
        self._key_cache.clear()
        self._key_cache_hits = 0
        logger.debug(f"Cleared public key cache ({cache_size} entries)")

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache size and hit count
        """
        return {
            "cache_size": len(self._key_cache),
            "cache_hits": self._key_cache_hits
        }
