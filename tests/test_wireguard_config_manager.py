"""
Unit tests for WireGuard Config Manager

Tests configuration file management and peer operations.
Part of E1-S3: WireGuard Peer Provisioning Service
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.wireguard_config_manager import WireGuardConfigManager


class TestWireGuardConfigManager:
    """Unit tests for WireGuardConfigManager"""

    def test_initialize_manager(self, tmp_path):
        """
        Given config path
        When initializing manager
        Then should create config file if not exists
        """
        config_path = tmp_path / "wg0.conf"
        manager = WireGuardConfigManager(config_path=str(config_path))

        assert config_path.exists()

    def test_add_peer_to_config(self, tmp_path):
        """
        Given empty config
        When adding peer
        Then should write peer section to config
        """
        config_path = tmp_path / "wg0.conf"
        manager = WireGuardConfigManager(config_path=str(config_path))

        manager.add_peer(
            public_key="test_public_key_123==",
            allowed_ips=["10.0.0.2/32"],
            persistent_keepalive=25
        )

        config = manager.get_config()
        assert "[Peer]" in config
        assert "PublicKey = test_public_key_123==" in config
        assert "AllowedIPs = 10.0.0.2/32" in config
        assert "PersistentKeepalive = 25" in config

    def test_add_multiple_peers(self, tmp_path):
        """
        Given config with one peer
        When adding another peer
        Then should append to config
        """
        config_path = tmp_path / "wg0.conf"
        manager = WireGuardConfigManager(config_path=str(config_path))

        manager.add_peer(
            public_key="peer1_key==",
            allowed_ips=["10.0.0.2/32"]
        )
        manager.add_peer(
            public_key="peer2_key==",
            allowed_ips=["10.0.0.3/32"]
        )

        config = manager.get_config()
        assert "peer1_key==" in config
        assert "peer2_key==" in config

    def test_remove_peer_from_config(self, tmp_path):
        """
        Given config with peer
        When removing peer
        Then should remove peer section
        """
        config_path = tmp_path / "wg0.conf"
        manager = WireGuardConfigManager(config_path=str(config_path))

        manager.add_peer(
            public_key="peer_to_remove==",
            allowed_ips=["10.0.0.2/32"]
        )

        result = manager.remove_peer(public_key="peer_to_remove==")

        assert result is True
        config = manager.get_config()
        assert "peer_to_remove==" not in config

    def test_remove_nonexistent_peer(self, tmp_path):
        """
        Given config without peer
        When removing peer
        Then should return False
        """
        config_path = tmp_path / "wg0.conf"
        manager = WireGuardConfigManager(config_path=str(config_path))

        result = manager.remove_peer(public_key="nonexistent_key==")

        assert result is False

    def test_add_duplicate_peer_ignored(self, tmp_path):
        """
        Given config with peer
        When adding same peer again
        Then should not duplicate
        """
        config_path = tmp_path / "wg0.conf"
        manager = WireGuardConfigManager(config_path=str(config_path))

        manager.add_peer(
            public_key="duplicate_key==",
            allowed_ips=["10.0.0.2/32"]
        )
        manager.add_peer(
            public_key="duplicate_key==",
            allowed_ips=["10.0.0.2/32"]
        )

        config = manager.get_config()
        # Count occurrences
        assert config.count("duplicate_key==") == 1

    def test_validate_config(self, tmp_path):
        """
        Given valid config
        When validating
        Then should return True
        """
        config_path = tmp_path / "wg0.conf"
        manager = WireGuardConfigManager(config_path=str(config_path))

        manager.add_peer(
            public_key="valid_key==",
            allowed_ips=["10.0.0.2/32"]
        )

        assert manager.validate_config() is True

    def test_config_file_permissions(self, tmp_path):
        """
        Given new config file
        When created
        Then should have secure permissions (0600)
        """
        config_path = tmp_path / "wg0.conf"
        manager = WireGuardConfigManager(config_path=str(config_path))

        manager.add_peer(
            public_key="test_key==",
            allowed_ips=["10.0.0.2/32"]
        )

        # Check file permissions (owner read/write only)
        import stat
        mode = config_path.stat().st_mode
        # Mask out file type bits, keep permission bits
        perms = stat.S_IMODE(mode)
        expected_perms = stat.S_IRUSR | stat.S_IWUSR  # 0600

        assert perms == expected_perms
