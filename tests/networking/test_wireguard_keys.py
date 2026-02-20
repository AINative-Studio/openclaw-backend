"""
Tests for WireGuard keypair generation and management.

This module tests the WireGuard keypair operations including:
- Ed25519 keypair generation
- Secure private key storage with 0600 permissions
- Public key format validation
"""

import os
import tempfile
import stat
from pathlib import Path
import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives import serialization

# Import will fail initially (TDD approach)
try:
    from backend.networking.wireguard_keys import (
        generate_keypair,
        store_private_key,
        load_private_key,
        get_public_key_from_private,
        validate_public_key_format,
        validate_private_key_format,
        initialize_node_keys,
        load_or_generate_keys,
        WireGuardKeyError,
    )
except ImportError:
    # Tests will fail until implementation is complete
    pass


class TestKeypairGeneration:
    """Test suite for WireGuard keypair generation."""

    def test_keypair_generation(self):
        """
        Given no existing keys
        When generating keypair
        Then should return valid X25519 private and public keys in base64 format
        """
        # When: Generate a new keypair
        private_key, public_key = generate_keypair()

        # Then: Both keys should be non-empty base64 strings
        assert private_key is not None
        assert public_key is not None
        assert isinstance(private_key, str)
        assert isinstance(public_key, str)

        # WireGuard keys are 44 characters in base64 (32 bytes encoded)
        assert len(private_key) == 44
        assert len(public_key) == 44

        # Should end with '=' padding for base64
        assert private_key.endswith('=')
        assert public_key.endswith('=')

    def test_keypair_generation_uniqueness(self):
        """
        Given multiple keypair generations
        When generating keypairs
        Then each keypair should be unique
        """
        # When: Generate multiple keypairs
        keypair1 = generate_keypair()
        keypair2 = generate_keypair()
        keypair3 = generate_keypair()

        # Then: All should be unique
        assert keypair1[0] != keypair2[0]
        assert keypair1[0] != keypair3[0]
        assert keypair2[0] != keypair3[0]
        assert keypair1[1] != keypair2[1]
        assert keypair1[1] != keypair3[1]
        assert keypair2[1] != keypair3[1]

    def test_public_key_derived_from_private(self):
        """
        Given a private key
        When deriving public key
        Then should always produce the same public key
        """
        # Given: Generate a keypair
        private_key, original_public_key = generate_keypair()

        # When: Derive public key from private key multiple times
        derived_public_key1 = get_public_key_from_private(private_key)
        derived_public_key2 = get_public_key_from_private(private_key)

        # Then: Derived keys should match original and be consistent
        assert derived_public_key1 == original_public_key
        assert derived_public_key2 == original_public_key


class TestPrivateKeyStorage:
    """Test suite for secure private key storage."""

    def test_private_key_storage_secure(self, tmp_path):
        """
        Given generated private key
        When storing to file
        Then should be encrypted/protected with proper permissions (0600)
        """
        # Given: A generated private key
        private_key, _ = generate_keypair()
        key_file_path = tmp_path / "test_private.key"

        # When: Store the private key
        store_private_key(private_key, str(key_file_path))

        # Then: File should exist with correct permissions
        assert key_file_path.exists()

        # Check file permissions are 0600 (owner read/write only)
        file_stats = os.stat(key_file_path)
        file_mode = stat.filemode(file_stats.st_mode)
        # On Unix: -rw------- (0600)
        assert file_stats.st_mode & 0o777 == 0o600, f"Expected 0600, got {oct(file_stats.st_mode & 0o777)}"

    def test_private_key_storage_and_retrieval(self, tmp_path):
        """
        Given stored private key
        When loading from file
        Then should retrieve the same key
        """
        # Given: A private key stored to file
        original_private_key, _ = generate_keypair()
        key_file_path = tmp_path / "test_private.key"
        store_private_key(original_private_key, str(key_file_path))

        # When: Load the private key from file
        loaded_private_key = load_private_key(str(key_file_path))

        # Then: Loaded key should match original
        assert loaded_private_key == original_private_key

    def test_private_key_storage_directory_creation(self, tmp_path):
        """
        Given non-existent directory path
        When storing private key
        Then should create parent directories automatically
        """
        # Given: A path with non-existent parent directories
        private_key, _ = generate_keypair()
        nested_path = tmp_path / "subdir1" / "subdir2" / "private.key"

        # When: Store the key (should create directories)
        store_private_key(private_key, str(nested_path))

        # Then: File should exist
        assert nested_path.exists()
        assert nested_path.is_file()

    def test_load_private_key_missing_file(self, tmp_path):
        """
        Given non-existent key file
        When attempting to load
        Then should raise WireGuardKeyError
        """
        # Given: A path to non-existent file
        missing_file = tmp_path / "missing.key"

        # When/Then: Should raise error
        with pytest.raises(WireGuardKeyError, match="not found"):
            load_private_key(str(missing_file))

    def test_store_private_key_overwrites_existing(self, tmp_path):
        """
        Given existing key file
        When storing new key
        Then should overwrite with new key
        """
        # Given: An existing key file
        old_key, _ = generate_keypair()
        key_file_path = tmp_path / "test_private.key"
        store_private_key(old_key, str(key_file_path))

        # When: Store a new key to same path
        new_key, _ = generate_keypair()
        store_private_key(new_key, str(key_file_path))

        # Then: Loaded key should be the new key
        loaded_key = load_private_key(str(key_file_path))
        assert loaded_key == new_key
        assert loaded_key != old_key


class TestPublicKeyValidation:
    """Test suite for public key format validation."""

    def test_public_key_format_valid(self):
        """
        Given generated public key
        When validating format
        Then should match WireGuard base64 format
        """
        # Given: A generated public key
        _, public_key = generate_keypair()

        # When/Then: Validation should pass
        assert validate_public_key_format(public_key) is True

    def test_public_key_format_invalid_length(self):
        """
        Given public key with invalid length
        When validating
        Then should return False
        """
        # Given: Invalid length keys
        too_short = "ABC123"
        too_long = "A" * 100

        # When/Then: Validation should fail
        assert validate_public_key_format(too_short) is False
        assert validate_public_key_format(too_long) is False

    def test_public_key_format_invalid_base64(self):
        """
        Given string that is not valid base64
        When validating
        Then should return False
        """
        # Given: Invalid base64 strings (44 chars but invalid base64)
        invalid_base64 = "!" * 44

        # When/Then: Validation should fail
        assert validate_public_key_format(invalid_base64) is False

    def test_public_key_format_empty_string(self):
        """
        Given empty string
        When validating
        Then should return False
        """
        # Given: Empty string
        empty = ""

        # When/Then: Validation should fail
        assert validate_public_key_format(empty) is False

    def test_public_key_format_none(self):
        """
        Given None value
        When validating
        Then should return False
        """
        # Given: None
        none_value = None

        # When/Then: Validation should fail
        assert validate_public_key_format(none_value) is False


class TestErrorHandling:
    """Test suite for error handling scenarios."""

    def test_get_public_key_from_invalid_private_key(self):
        """
        Given invalid private key
        When deriving public key
        Then should raise WireGuardKeyError
        """
        # Given: Invalid private key formats
        invalid_keys = [
            "invalid_base64",
            "tooshort",
            "",
            "A" * 100,
        ]

        # When/Then: Should raise error for each
        for invalid_key in invalid_keys:
            with pytest.raises(WireGuardKeyError, match="Invalid private key"):
                get_public_key_from_private(invalid_key)

    def test_store_private_key_invalid_key(self, tmp_path):
        """
        Given invalid private key
        When storing
        Then should raise WireGuardKeyError
        """
        # Given: Invalid private key
        invalid_key = "not_a_valid_key"
        key_file_path = tmp_path / "test.key"

        # When/Then: Should raise error
        with pytest.raises(WireGuardKeyError, match="Invalid private key"):
            store_private_key(invalid_key, str(key_file_path))


class TestIntegrationScenarios:
    """Integration tests for complete workflows."""

    def test_full_keypair_lifecycle(self, tmp_path):
        """
        Given a new node initialization
        When generating, storing, and loading keys
        Then complete lifecycle should work correctly
        """
        # Given: Fresh node needs keys
        key_storage_path = tmp_path / "node_keys" / "private.key"

        # When: Generate and store keypair
        original_private, original_public = generate_keypair()
        store_private_key(original_private, str(key_storage_path))

        # Then: Should be able to load and derive same public key
        loaded_private = load_private_key(str(key_storage_path))
        derived_public = get_public_key_from_private(loaded_private)

        assert loaded_private == original_private
        assert derived_public == original_public
        assert validate_public_key_format(derived_public) is True

    def test_multiple_nodes_unique_keys(self, tmp_path):
        """
        Given multiple nodes initializing
        When each generates keys
        Then all should have unique keypairs
        """
        # Simulate 5 nodes generating keys
        node_keys = []
        for i in range(5):
            node_dir = tmp_path / f"node_{i}"
            node_dir.mkdir()

            # Generate and store
            private_key, public_key = generate_keypair()
            key_path = node_dir / "private.key"
            store_private_key(private_key, str(key_path))

            node_keys.append((private_key, public_key))

        # Then: All keys should be unique
        private_keys = [k[0] for k in node_keys]
        public_keys = [k[1] for k in node_keys]

        assert len(set(private_keys)) == 5
        assert len(set(public_keys)) == 5


class TestUtilityFunctions:
    """Test suite for utility and convenience functions."""

    def test_validate_private_key_format_valid(self):
        """
        Given valid private key
        When validating format
        Then should return True
        """
        # Given: A valid private key
        private_key, _ = generate_keypair()

        # When/Then: Validation should pass
        assert validate_private_key_format(private_key) is True

    def test_validate_private_key_format_invalid(self):
        """
        Given invalid private key formats
        When validating
        Then should return False
        """
        # Given: Various invalid formats
        invalid_keys = [
            None,
            "",
            "too_short",
            "A" * 100,
            "!" * 44,  # Invalid base64
        ]

        # When/Then: All should fail validation
        for invalid_key in invalid_keys:
            assert validate_private_key_format(invalid_key) is False

    def test_initialize_node_keys(self, tmp_path):
        """
        Given a key storage path
        When initializing node keys
        Then should generate and store keys, returning both
        """
        # Given: A storage path
        key_path = tmp_path / "node.key"

        # When: Initialize node keys
        private_key, public_key = initialize_node_keys(str(key_path))

        # Then: Should have generated and stored keys
        assert key_path.exists()
        assert validate_private_key_format(private_key) is True
        assert validate_public_key_format(public_key) is True

        # Verify stored key matches
        loaded_key = load_private_key(str(key_path))
        assert loaded_key == private_key

    def test_load_or_generate_keys_new(self, tmp_path):
        """
        Given non-existent key file
        When calling load_or_generate_keys
        Then should generate and store new keys
        """
        # Given: Non-existent key path
        key_path = tmp_path / "new_node.key"
        assert not key_path.exists()

        # When: Load or generate
        private_key, public_key = load_or_generate_keys(str(key_path))

        # Then: Should have created new keys
        assert key_path.exists()
        assert validate_private_key_format(private_key) is True
        assert validate_public_key_format(public_key) is True

    def test_load_or_generate_keys_existing(self, tmp_path):
        """
        Given existing key file
        When calling load_or_generate_keys
        Then should load existing keys (idempotent)
        """
        # Given: Existing key file
        key_path = tmp_path / "existing_node.key"
        original_private, original_public = initialize_node_keys(str(key_path))

        # When: Load or generate (should load existing)
        loaded_private, loaded_public = load_or_generate_keys(str(key_path))

        # Then: Should return same keys
        assert loaded_private == original_private
        assert loaded_public == original_public

    def test_load_or_generate_keys_idempotent(self, tmp_path):
        """
        Given load_or_generate_keys called multiple times
        When checking results
        Then should always return same keys (idempotent)
        """
        # Given: A key path
        key_path = tmp_path / "idempotent.key"

        # When: Call multiple times
        keys1 = load_or_generate_keys(str(key_path))
        keys2 = load_or_generate_keys(str(key_path))
        keys3 = load_or_generate_keys(str(key_path))

        # Then: All should be identical
        assert keys1 == keys2
        assert keys2 == keys3

    def test_load_private_key_not_a_file(self, tmp_path):
        """
        Given path that is a directory
        When attempting to load
        Then should raise WireGuardKeyError
        """
        # Given: A directory path (not a file)
        dir_path = tmp_path / "directory"
        dir_path.mkdir()

        # When/Then: Should raise error
        with pytest.raises(WireGuardKeyError, match="not a file"):
            load_private_key(str(dir_path))
