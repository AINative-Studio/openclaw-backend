"""
Peer Key Store (E7-S3)

Manages storage and retrieval of peer public keys for message verification.
Provides in-memory caching for performance optimization.
"""

from typing import Optional, Dict
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import logging

logger = logging.getLogger(__name__)


class PeerKeyStore:
    """
    Stores and retrieves Ed25519 public keys for peer verification.

    Features:
    - In-memory storage for fast lookups
    - Public key serialization/deserialization
    - Thread-safe operations (for future multi-threading)
    """

    def __init__(self):
        """Initialize empty peer key store."""
        self._keys: Dict[str, ed25519.Ed25519PublicKey] = {}
        logger.info("PeerKeyStore initialized")

    def store_public_key(self, peer_id: str, public_key: ed25519.Ed25519PublicKey) -> None:
        """
        Store a public key for a peer.

        Args:
            peer_id: libp2p peer ID
            public_key: Ed25519 public key object

        Raises:
            ValueError: If peer_id is empty or public_key is invalid
        """
        if not peer_id:
            raise ValueError("peer_id cannot be empty")

        if not isinstance(public_key, ed25519.Ed25519PublicKey):
            raise ValueError("public_key must be an Ed25519PublicKey instance")

        self._keys[peer_id] = public_key
        logger.debug(f"Stored public key for peer {peer_id}")

    def get_public_key(self, peer_id: str) -> Optional[ed25519.Ed25519PublicKey]:
        """
        Retrieve a public key for a peer.

        Args:
            peer_id: libp2p peer ID

        Returns:
            Ed25519 public key or None if not found
        """
        key = self._keys.get(peer_id)
        if key:
            logger.debug(f"Retrieved public key for peer {peer_id}")
        else:
            logger.debug(f"No public key found for peer {peer_id}")
        return key

    def remove_public_key(self, peer_id: str) -> bool:
        """
        Remove a public key from the store.

        Args:
            peer_id: libp2p peer ID

        Returns:
            True if key was removed, False if not found
        """
        if peer_id in self._keys:
            del self._keys[peer_id]
            logger.debug(f"Removed public key for peer {peer_id}")
            return True
        return False

    def has_public_key(self, peer_id: str) -> bool:
        """
        Check if a public key exists for a peer.

        Args:
            peer_id: libp2p peer ID

        Returns:
            True if public key exists, False otherwise
        """
        return peer_id in self._keys

    def export_public_key_bytes(self, peer_id: str) -> Optional[bytes]:
        """
        Export a public key as raw bytes.

        Args:
            peer_id: libp2p peer ID

        Returns:
            32-byte raw Ed25519 public key or None if not found
        """
        public_key = self.get_public_key(peer_id)
        if public_key is None:
            return None

        return public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

    def import_public_key_bytes(self, peer_id: str, key_bytes: bytes) -> None:
        """
        Import a public key from raw bytes.

        Args:
            peer_id: libp2p peer ID
            key_bytes: 32-byte raw Ed25519 public key

        Raises:
            ValueError: If key_bytes is invalid
        """
        if len(key_bytes) != 32:
            raise ValueError(f"Ed25519 public key must be 32 bytes, got {len(key_bytes)}")

        try:
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(key_bytes)
            self.store_public_key(peer_id, public_key)
        except Exception as e:
            raise ValueError(f"Invalid Ed25519 public key bytes: {e}")

    def clear(self) -> None:
        """Clear all stored public keys."""
        count = len(self._keys)
        self._keys.clear()
        logger.info(f"Cleared {count} public keys from store")

    def count(self) -> int:
        """
        Get the number of stored public keys.

        Returns:
            Count of stored keys
        """
        return len(self._keys)

    def get_all_peer_ids(self) -> list[str]:
        """
        Get all peer IDs with stored public keys.

        Returns:
            List of peer IDs
        """
        return list(self._keys.keys())
