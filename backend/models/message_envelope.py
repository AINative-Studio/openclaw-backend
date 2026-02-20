"""
Message Envelope Schema (E7-S2)

Pydantic model for signed message envelopes with Ed25519 signatures.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional


class MessageEnvelope(BaseModel):
    """
    Message envelope containing signature and metadata for authenticated messaging.

    All P2P messages are wrapped in this envelope to provide:
    - Message integrity via SHA-256 payload hashing
    - Authentication via Ed25519 signatures
    - Sender identity via peer_id
    - Temporal ordering via UTC timestamps

    Schema:
        payload_hash: SHA-256 hash of the message payload (format: "sha256:...")
        peer_id: libp2p peer ID of the sender (format: "12D3KooW...")
        timestamp: UTC timestamp when message was signed (Unix epoch seconds)
        signature: Base64-encoded Ed25519 signature of payload_hash
    """

    payload_hash: str = Field(
        ...,
        description="SHA-256 hash of message payload with 'sha256:' prefix",
        min_length=71,  # "sha256:" (7 chars) + 64 hex chars
        max_length=71
    )

    peer_id: str = Field(
        ...,
        description="libp2p peer ID of message sender",
        min_length=10,
        pattern=r"^12D3KooW[A-Za-z0-9]+$"
    )

    timestamp: int = Field(
        ...,
        description="UTC timestamp when message was signed (Unix epoch seconds)",
        gt=0
    )

    signature: str = Field(
        ...,
        description="Base64-encoded Ed25519 signature",
        min_length=1
    )

    @field_validator('payload_hash')
    @classmethod
    def validate_payload_hash_format(cls, v: str) -> str:
        """
        Validate that payload_hash starts with 'sha256:' prefix.
        """
        if not v.startswith("sha256:"):
            raise ValueError("payload_hash must start with 'sha256:' prefix")

        # Verify hash part is valid hex
        hash_value = v.replace("sha256:", "")
        if len(hash_value) != 64:
            raise ValueError("SHA-256 hash must be 64 hexadecimal characters")

        try:
            int(hash_value, 16)
        except ValueError:
            raise ValueError("Hash value must be valid hexadecimal")

        return v

    @field_validator('peer_id')
    @classmethod
    def validate_peer_id_format(cls, v: str) -> str:
        """
        Validate that peer_id follows libp2p format.
        """
        if not v.startswith("12D3KooW"):
            raise ValueError("peer_id must start with '12D3KooW' prefix")

        return v

    class Config:
        """Pydantic configuration"""
        json_schema_extra = {
            "example": {
                "payload_hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "peer_id": "12D3KooWTest1234567890",
                "timestamp": 1708380000,
                "signature": "SGVsbG8gV29ybGQh"
            }
        }
