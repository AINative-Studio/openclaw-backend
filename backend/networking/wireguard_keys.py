"""
WireGuard keypair generation and management.

This module provides functionality for:
- Generating Ed25519/X25519 keypairs for WireGuard
- Securely storing private keys with appropriate file permissions
- Loading and validating keys
- Converting between key formats

WireGuard uses Curve25519 for key exchange, which uses X25519 keys.
Keys are stored in base64 format as per WireGuard conventions.
"""

import os
import base64
from pathlib import Path
from typing import Tuple

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives import serialization


class WireGuardKeyError(Exception):
    """Custom exception for WireGuard key operations."""
    pass


def generate_keypair() -> Tuple[str, str]:
    """
    Generate a new WireGuard keypair using X25519.

    Returns:
        Tuple[str, str]: A tuple containing (private_key, public_key) in base64 format.
                        Both keys are 44 characters long (32 bytes base64 encoded).

    Example:
        >>> private_key, public_key = generate_keypair()
        >>> len(private_key)
        44
        >>> len(public_key)
        44
    """
    # Generate X25519 private key
    private_key_obj = X25519PrivateKey.generate()

    # Derive public key
    public_key_obj = private_key_obj.public_key()

    # Serialize to bytes
    private_key_bytes = private_key_obj.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )

    public_key_bytes = public_key_obj.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )

    # Encode to base64 (WireGuard format)
    private_key_b64 = base64.b64encode(private_key_bytes).decode('ascii')
    public_key_b64 = base64.b64encode(public_key_bytes).decode('ascii')

    return private_key_b64, public_key_b64


def get_public_key_from_private(private_key: str) -> str:
    """
    Derive the public key from a private key.

    Args:
        private_key: Base64-encoded X25519 private key

    Returns:
        str: Base64-encoded X25519 public key

    Raises:
        WireGuardKeyError: If the private key is invalid
    """
    try:
        # Decode base64 private key
        private_key_bytes = base64.b64decode(private_key)

        # Validate key length (X25519 keys are 32 bytes)
        if len(private_key_bytes) != 32:
            raise WireGuardKeyError(
                f"Invalid private key length: expected 32 bytes, got {len(private_key_bytes)}"
            )

        # Load private key
        private_key_obj = X25519PrivateKey.from_private_bytes(private_key_bytes)

        # Derive public key
        public_key_obj = private_key_obj.public_key()

        # Serialize to bytes and encode
        public_key_bytes = public_key_obj.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

        public_key_b64 = base64.b64encode(public_key_bytes).decode('ascii')

        return public_key_b64

    except (ValueError, TypeError) as e:
        raise WireGuardKeyError(f"Invalid private key format: {str(e)}")
    except Exception as e:
        raise WireGuardKeyError(f"Invalid private key: {str(e)}")


def store_private_key(private_key: str, file_path: str) -> None:
    """
    Store a private key to a file with secure permissions (0600).

    The file will be created with owner read/write only permissions.
    Parent directories will be created if they don't exist.

    Args:
        private_key: Base64-encoded private key to store
        file_path: Path where the key should be stored

    Raises:
        WireGuardKeyError: If the private key is invalid or storage fails
    """
    try:
        # Validate the private key before storing
        # This will raise WireGuardKeyError if invalid
        get_public_key_from_private(private_key)

        # Convert to Path object for easier handling
        path = Path(file_path)

        # Create parent directories if they don't exist
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write the key to file with secure permissions
        # Use os.open with specific flags for security
        fd = os.open(
            str(path),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600  # Owner read/write only
        )

        try:
            # Write the key content
            os.write(fd, private_key.encode('utf-8'))
        finally:
            os.close(fd)

        # Verify permissions were set correctly
        file_stat = os.stat(path)
        actual_mode = file_stat.st_mode & 0o777

        if actual_mode != 0o600:
            # If permissions weren't set correctly, fix them
            os.chmod(path, 0o600)

    except WireGuardKeyError:
        raise
    except Exception as e:
        raise WireGuardKeyError(f"Failed to store private key: {str(e)}")


def load_private_key(file_path: str) -> str:
    """
    Load a private key from a file.

    Args:
        file_path: Path to the key file

    Returns:
        str: Base64-encoded private key

    Raises:
        WireGuardKeyError: If the file doesn't exist or cannot be read
    """
    try:
        path = Path(file_path)

        if not path.exists():
            raise WireGuardKeyError(f"Private key file not found: {file_path}")

        if not path.is_file():
            raise WireGuardKeyError(f"Path is not a file: {file_path}")

        # Read the key
        with open(path, 'r', encoding='utf-8') as f:
            private_key = f.read().strip()

        # Validate the loaded key
        get_public_key_from_private(private_key)

        return private_key

    except WireGuardKeyError:
        raise
    except Exception as e:
        raise WireGuardKeyError(f"Failed to load private key: {str(e)}")


def validate_public_key_format(public_key) -> bool:
    """
    Validate that a public key matches the WireGuard base64 format.

    WireGuard public keys are:
    - 44 characters long (32 bytes base64 encoded)
    - Valid base64 encoding
    - End with '=' padding

    Args:
        public_key: Public key to validate (can be None)

    Returns:
        bool: True if valid, False otherwise
    """
    # Check for None or non-string
    if public_key is None or not isinstance(public_key, str):
        return False

    # Check length
    if len(public_key) != 44:
        return False

    # Try to decode as base64
    try:
        decoded = base64.b64decode(public_key)

        # X25519 public keys are 32 bytes
        if len(decoded) != 32:
            return False

        return True

    except Exception:
        return False


def validate_private_key_format(private_key) -> bool:
    """
    Validate that a private key matches the WireGuard base64 format.

    Args:
        private_key: Private key to validate (can be None)

    Returns:
        bool: True if valid, False otherwise
    """
    # Check for None or non-string
    if private_key is None or not isinstance(private_key, str):
        return False

    # Check length
    if len(private_key) != 44:
        return False

    # Try to decode and validate
    try:
        decoded = base64.b64decode(private_key)

        # X25519 private keys are 32 bytes
        if len(decoded) != 32:
            return False

        # Try to create a key object to fully validate
        X25519PrivateKey.from_private_bytes(decoded)

        return True

    except Exception:
        return False


# Convenience function for node initialization
def initialize_node_keys(key_storage_path: str) -> Tuple[str, str]:
    """
    Initialize WireGuard keys for a new node.

    This is a convenience function that:
    1. Generates a new keypair
    2. Stores the private key securely
    3. Returns both keys for registration

    Args:
        key_storage_path: Path where private key should be stored

    Returns:
        Tuple[str, str]: (private_key, public_key) in base64 format

    Raises:
        WireGuardKeyError: If key generation or storage fails
    """
    # Generate keypair
    private_key, public_key = generate_keypair()

    # Store private key securely
    store_private_key(private_key, key_storage_path)

    return private_key, public_key


def load_or_generate_keys(key_storage_path: str) -> Tuple[str, str]:
    """
    Load existing keys or generate new ones if they don't exist.

    This function is idempotent - it can be called multiple times safely.

    Args:
        key_storage_path: Path where private key is/should be stored

    Returns:
        Tuple[str, str]: (private_key, public_key) in base64 format

    Raises:
        WireGuardKeyError: If key operations fail
    """
    path = Path(key_storage_path)

    if path.exists():
        # Load existing keys
        private_key = load_private_key(key_storage_path)
        public_key = get_public_key_from_private(private_key)
        return private_key, public_key
    else:
        # Generate and store new keys
        return initialize_node_keys(key_storage_path)
