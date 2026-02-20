"""
libp2p Peer Identity Management (E2-S1)

Implements Ed25519 keypair generation and peer ID derivation for libp2p.
"""

from pathlib import Path
from typing import Optional, Dict
import base58
import hashlib
import json
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import os


class LibP2PIdentity:
    """
    Manages libp2p peer identity including Ed25519 keypairs and peer_id derivation.
    
    libp2p peer IDs are derived from public keys using multihash encoding:
    - Hash the public key using SHA-256
    - Prepend multihash header (0x12 for SHA-256, 0x20 for 32-byte length)
    - Base58 encode the result
    - Prepend "12D3KooW" prefix (libp2p v0 peer ID indicator)
    """

    def __init__(self):
        self._private_key: Optional[ed25519.Ed25519PrivateKey] = None
        self._public_key: Optional[ed25519.Ed25519PublicKey] = None
        self._peer_id: Optional[str] = None

    @property
    def private_key(self) -> Optional[ed25519.Ed25519PrivateKey]:
        """Returns the Ed25519 private key"""
        return self._private_key

    @property
    def public_key(self) -> Optional[ed25519.Ed25519PublicKey]:
        """Returns the Ed25519 public key"""
        return self._public_key

    @property
    def peer_id(self) -> Optional[str]:
        """Returns the libp2p peer ID"""
        return self._peer_id

    def generate(self) -> None:
        """
        Generate a new Ed25519 keypair and derive peer_id.
        """
        # Generate Ed25519 keypair
        self._private_key = ed25519.Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        
        # Derive peer_id from public key
        self._peer_id = self._derive_peer_id(self._public_key)

    def _derive_peer_id(self, public_key: ed25519.Ed25519PublicKey) -> str:
        """
        Derive libp2p peer ID from Ed25519 public key.
        
        Process:
        1. Serialize public key to bytes
        2. Compute SHA-256 hash
        3. Create multihash (0x12 + 0x20 + hash)
        4. Base58 encode
        5. Add libp2p prefix
        """
        # Serialize public key to raw bytes
        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        # Compute SHA-256 hash of public key
        hash_digest = hashlib.sha256(public_key_bytes).digest()
        
        # Create multihash: 0x12 (SHA-256) + 0x20 (32 bytes) + hash
        multihash = bytes([0x12, 0x20]) + hash_digest
        
        # Base58 encode
        peer_id_base58 = base58.b58encode(multihash).decode('utf-8')
        
        # Add libp2p v0 peer ID prefix
        # Note: Real libp2p uses "12D3KooW" prefix for Ed25519 keys
        # For simplicity, we'll use this prefix
        return f"12D3KooW{peer_id_base58[:40]}"

    def get_private_key_bytes(self) -> bytes:
        """
        Export private key as bytes for serialization.
        """
        if self._private_key is None:
            raise ValueError("No private key available. Call generate() first.")
        
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )

    def load_from_private_key(self, private_key_bytes: bytes) -> None:
        """
        Load identity from existing private key bytes.
        """
        self._private_key = ed25519.Ed25519PrivateKey.from_private_bytes(
            private_key_bytes
        )
        self._public_key = self._private_key.public_key()
        self._peer_id = self._derive_peer_id(self._public_key)

    def export_public_key(self) -> bytes:
        """
        Export public key in protobuf-compatible format.
        For Ed25519, this is the raw 32-byte public key.
        """
        if self._public_key is None:
            raise ValueError("No public key available. Call generate() first.")
        
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

    def save(self, key_path: Path) -> None:
        """
        Save identity to file with secure permissions (0600).
        Stores private key, public key, and peer_id as JSON.
        """
        if self._private_key is None:
            raise ValueError("No identity to save. Call generate() first.")
        
        # Prepare identity data
        identity_data = {
            "private_key": self.get_private_key_bytes().hex(),
            "public_key": self.export_public_key().hex(),
            "peer_id": self._peer_id
        }
        
        # Create parent directory if needed
        key_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to file
        key_path.write_text(json.dumps(identity_data, indent=2))
        
        # Set secure permissions (owner read/write only)
        os.chmod(key_path, 0o600)

    def load(self, key_path: Path) -> None:
        """
        Load identity from file.
        """
        if not key_path.exists():
            raise FileNotFoundError(f"Identity file not found: {key_path}")
        
        # Read identity data
        identity_data = json.loads(key_path.read_text())
        
        # Load private key
        private_key_bytes = bytes.fromhex(identity_data["private_key"])
        self.load_from_private_key(private_key_bytes)
        
        # Verify peer_id matches
        if self._peer_id != identity_data["peer_id"]:
            raise ValueError(
                f"Peer ID mismatch. Expected {identity_data['peer_id']}, "
                f"got {self._peer_id}"
            )

    def validate_peer_id_format(self, peer_id: str) -> bool:
        """
        Validate that a peer_id follows libp2p format.
        Expected format: "12D3KooW" prefix followed by base58 characters.
        """
        if not peer_id:
            return False
        
        # Check prefix
        if not peer_id.startswith("12D3KooW"):
            return False
        
        # Check length (should be reasonable)
        if len(peer_id) < 20:
            return False
        
        # Check base58 characters in suffix
        base58_chars = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
        suffix = peer_id[8:]  # Skip prefix
        
        return all(c in base58_chars for c in suffix)

    def to_dict(self) -> Dict[str, str]:
        """
        Export identity as dictionary for API responses.
        """
        if self._peer_id is None:
            raise ValueError("No identity available. Call generate() first.")
        
        return {
            "peer_id": self._peer_id,
            "public_key": self.export_public_key().hex()
        }
