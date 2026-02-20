"""
Tests for libp2p Peer Identity Management (E2-S1)

Following TDD and BDD principles with Given/When/Then structure.
"""

import pytest
from pathlib import Path
import tempfile
import os


class TestLibp2pIdentity:
    """Test suite for libp2p peer identity management"""

    def test_generate_peer_identity(self):
        """Given no existing identity, when generating,
        then should create Ed25519 key and derive peer_id"""
        from backend.p2p.libp2p_identity import LibP2PIdentity

        # Given: No existing identity
        identity = LibP2PIdentity()

        # When: Generating identity
        identity.generate()

        # Then: Should have Ed25519 keypair and peer_id
        assert identity.private_key is not None
        assert identity.public_key is not None
        assert identity.peer_id is not None
        assert len(identity.peer_id) > 0
        assert identity.peer_id.startswith("12D3KooW")  # libp2p peer ID prefix

    def test_peer_id_deterministic(self):
        """Given same private key, when deriving peer_id,
        then should always produce same ID"""
        from backend.p2p.libp2p_identity import LibP2PIdentity

        # Given: First identity
        identity1 = LibP2PIdentity()
        identity1.generate()
        private_key_bytes = identity1.get_private_key_bytes()
        peer_id1 = identity1.peer_id

        # When: Creating second identity from same private key
        identity2 = LibP2PIdentity()
        identity2.load_from_private_key(private_key_bytes)
        peer_id2 = identity2.peer_id

        # Then: Peer IDs should be identical
        assert peer_id1 == peer_id2

    def test_export_public_key(self):
        """Given peer identity, when exporting public key,
        then should return valid protobuf encoding"""
        from backend.p2p.libp2p_identity import LibP2PIdentity

        # Given: Generated identity
        identity = LibP2PIdentity()
        identity.generate()

        # When: Exporting public key
        public_key_bytes = identity.export_public_key()

        # Then: Should be valid bytes
        assert isinstance(public_key_bytes, bytes)
        assert len(public_key_bytes) > 0

    def test_save_and_load_identity(self):
        """Given generated identity, when saving and loading,
        then should restore same peer_id"""
        from backend.p2p.libp2p_identity import LibP2PIdentity

        with tempfile.TemporaryDirectory() as tmpdir:
            # Given: Generated identity
            identity1 = LibP2PIdentity()
            identity1.generate()
            peer_id1 = identity1.peer_id
            key_path = Path(tmpdir) / "identity.key"

            # When: Saving identity
            identity1.save(key_path)

            # And: Loading identity
            identity2 = LibP2PIdentity()
            identity2.load(key_path)

            # Then: Should restore same peer_id
            assert identity2.peer_id == peer_id1

    def test_identity_file_permissions(self):
        """Given saved identity, when checking permissions,
        then should have secure permissions (0600)"""
        from backend.p2p.libp2p_identity import LibP2PIdentity

        with tempfile.TemporaryDirectory() as tmpdir:
            # Given: Generated and saved identity
            identity = LibP2PIdentity()
            identity.generate()
            key_path = Path(tmpdir) / "identity.key"
            identity.save(key_path)

            # When: Checking file permissions
            stat_info = os.stat(key_path)
            permissions = oct(stat_info.st_mode)[-3:]

            # Then: Should be 600 (owner read/write only)
            assert permissions == "600", f"Expected 600 but got {permissions}"

    def test_validate_peer_id_format(self):
        """Given generated peer_id, when validating,
        then should match libp2p base58 format"""
        from backend.p2p.libp2p_identity import LibP2PIdentity

        # Given: Generated identity
        identity = LibP2PIdentity()
        identity.generate()

        # When: Validating peer_id format
        is_valid = identity.validate_peer_id_format(identity.peer_id)

        # Then: Should be valid
        assert is_valid is True

    def test_load_nonexistent_identity_raises_error(self):
        """Given nonexistent identity file, when loading,
        then should raise FileNotFoundError"""
        from backend.p2p.libp2p_identity import LibP2PIdentity

        # Given: Nonexistent path
        identity = LibP2PIdentity()

        # When/Then: Loading should raise error
        with pytest.raises(FileNotFoundError):
            identity.load(Path("/nonexistent/path/identity.key"))

    def test_export_identity_as_dict(self):
        """Given generated identity, when exporting as dict,
        then should contain peer_id and public_key"""
        from backend.p2p.libp2p_identity import LibP2PIdentity

        # Given: Generated identity
        identity = LibP2PIdentity()
        identity.generate()

        # When: Exporting as dict
        identity_dict = identity.to_dict()

        # Then: Should contain required fields
        assert "peer_id" in identity_dict
        assert "public_key" in identity_dict
        assert identity_dict["peer_id"] == identity.peer_id
        assert len(identity_dict["public_key"]) > 0


@pytest.fixture
def temp_identity_path():
    """Fixture providing temporary path for identity storage"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_identity.key"
