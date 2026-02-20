"""
Message Signing Service (E7-S2)

Implements Ed25519 message signing for authenticated P2P messaging.
"""

import hashlib
import json
import time
import base64
from typing import Dict, Any, Optional

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

from backend.p2p.libp2p_identity import LibP2PIdentity
from backend.models.message_envelope import MessageEnvelope


class MessageSigningService:
    """
    Service for signing and verifying P2P messages using Ed25519 signatures.

    This service provides message authentication and integrity verification for
    all P2P communications. Each message is:
    1. Serialized to canonical JSON format
    2. Hashed using SHA-256
    3. Signed with sender's Ed25519 private key
    4. Wrapped in a MessageEnvelope with metadata

    Usage:
        identity = LibP2PIdentity()
        identity.generate()

        service = MessageSigningService(identity)
        envelope = service.sign_message({"type": "heartbeat", "data": {...}})

        # Later, verify the message
        is_valid = service.verify_signature(envelope, original_payload)
    """

    def __init__(self, identity: LibP2PIdentity):
        """
        Initialize message signing service with peer identity.

        Args:
            identity: LibP2PIdentity instance with Ed25519 keypair
        """
        if identity.private_key is None:
            raise ValueError(
                "Identity must have a private key. Call identity.generate() first."
            )

        self._identity = identity

    def sign_message(
        self,
        payload: Dict[str, Any],
        timestamp: Optional[int] = None
    ) -> MessageEnvelope:
        """
        Sign a message payload and create a signed envelope.

        Process:
        1. Compute SHA-256 hash of canonical JSON payload
        2. Sign hash with Ed25519 private key
        3. Create envelope with signature and metadata

        Args:
            payload: Message payload (any JSON-serializable dict)
            timestamp: Optional fixed timestamp (defaults to current time)

        Returns:
            MessageEnvelope with signature and metadata

        Raises:
            ValueError: If identity is invalid or signing fails
        """
        # Compute payload hash
        payload_hash = self._compute_payload_hash(payload)

        # Get current timestamp if not provided
        if timestamp is None:
            timestamp = int(time.time())

        # Create signing data: combine hash and timestamp for signature
        # This prevents replay attacks with different timestamps
        signing_data = f"{payload_hash}:{timestamp}".encode('utf-8')

        # Sign with Ed25519 private key
        signature_bytes = self._identity.private_key.sign(signing_data)

        # Encode signature as base64
        signature = base64.b64encode(signature_bytes).decode('utf-8')

        # Create envelope
        return MessageEnvelope(
            payload_hash=payload_hash,
            peer_id=self._identity.peer_id,
            timestamp=timestamp,
            signature=signature
        )

    def verify_signature(
        self,
        envelope: MessageEnvelope,
        payload: Dict[str, Any]
    ) -> bool:
        """
        Verify that a message envelope's signature is valid.

        Process:
        1. Recompute payload hash from provided payload
        2. Verify hash matches envelope's payload_hash
        3. Verify Ed25519 signature using sender's public key

        Args:
            envelope: Signed message envelope
            payload: Original message payload

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Recompute payload hash
            computed_hash = self._compute_payload_hash(payload)

            # Verify hash matches
            if computed_hash != envelope.payload_hash:
                return False

            # Reconstruct signing data
            signing_data = f"{envelope.payload_hash}:{envelope.timestamp}".encode('utf-8')

            # Decode signature from base64
            signature_bytes = base64.b64decode(envelope.signature)

            # Verify signature with Ed25519 public key
            # Note: For now, we verify with our own public key
            # In a real P2P system, we'd need to fetch the sender's public key
            # from a key registry based on envelope.peer_id
            self._identity.public_key.verify(signature_bytes, signing_data)

            return True

        except InvalidSignature:
            return False
        except Exception:
            # Any other error (base64 decode, etc.) means invalid signature
            return False

    def verify_signature_with_public_key(
        self,
        envelope: MessageEnvelope,
        payload: Dict[str, Any],
        public_key: ed25519.Ed25519PublicKey
    ) -> bool:
        """
        Verify signature using a specific public key.

        This is useful for verifying messages from other peers where we
        have their public key but not their full identity.

        Args:
            envelope: Signed message envelope
            payload: Original message payload
            public_key: Ed25519 public key to verify with

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Recompute payload hash
            computed_hash = self._compute_payload_hash(payload)

            # Verify hash matches
            if computed_hash != envelope.payload_hash:
                return False

            # Reconstruct signing data
            signing_data = f"{envelope.payload_hash}:{envelope.timestamp}".encode('utf-8')

            # Decode signature from base64
            signature_bytes = base64.b64decode(envelope.signature)

            # Verify signature with provided public key
            public_key.verify(signature_bytes, signing_data)

            return True

        except InvalidSignature:
            return False
        except Exception:
            return False

    def _compute_payload_hash(self, payload: Dict[str, Any]) -> str:
        """
        Compute SHA-256 hash of message payload.

        Uses canonical JSON serialization to ensure consistent hashing:
        - Keys sorted alphabetically
        - No whitespace
        - UTF-8 encoding

        Args:
            payload: Message payload

        Returns:
            Hash string in format "sha256:<hex_digest>"
        """
        # Serialize to canonical JSON
        # sort_keys ensures consistent ordering across implementations
        # separators removes whitespace for canonical form
        canonical_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False
        )

        # Compute SHA-256 hash
        hash_bytes = hashlib.sha256(canonical_json.encode('utf-8')).digest()

        # Convert to hex and add prefix
        return f"sha256:{hash_bytes.hex()}"

    @property
    def peer_id(self) -> str:
        """Get the peer ID of this signing service."""
        return self._identity.peer_id

    @property
    def public_key_hex(self) -> str:
        """Get the public key as hex string for sharing."""
        return self._identity.export_public_key().hex()
