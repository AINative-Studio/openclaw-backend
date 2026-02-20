"""
WireGuard Hub Configuration Management Tests

Tests for E1-S4: Hub WireGuard Configuration Management
Implements BDD-style tests (Given/When/Then) for:
- Adding peers to hub configuration
- Removing peers from hub configuration
- Zero-downtime configuration reload
- Peer connectivity verification

Story Points: 3
Coverage Target: >= 80%
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.networking.wireguard_hub_manager import (
    WireGuardHubManager,
    PeerConfig,
    ConfigReloadError,
    PeerNotFoundError,
    ConnectivityCheckError,
)


@pytest.fixture
def temp_config_dir():
    """Create temporary directory for WireGuard configuration files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_peer_config():
    """Sample peer configuration for testing."""
    return PeerConfig(
        public_key="xTIBA5rboUvnH4htodjb6e697QjLERt1NAB4mZqp8Dg=",
        allowed_ips=["10.0.0.2/32"],
        endpoint=Optional[None],
        persistent_keepalive=25,
    )


@pytest.fixture
async def hub_manager(temp_config_dir):
    """Create WireGuard hub manager instance for testing."""
    config_path = temp_config_dir / "wg0.conf"
    manager = WireGuardHubManager(
        interface_name="wg0",
        config_path=str(config_path),
        listen_port=51820,
        private_key="yAnz5TF+lXXJte14tji3zlMNq+hd2rYUIgJBgB3fBmk=",
        address="10.0.0.1/24",
    )
    yield manager
    # Cleanup
    await manager.shutdown()


class TestAddPeerToConfig:
    """Tests for adding peer to WireGuard hub configuration."""

    @pytest.mark.asyncio
    async def test_add_peer_to_config_success(self, hub_manager, sample_peer_config):
        """
        Given new peer config
        When adding to hub
        Then should update config file and reload
        """
        # Given: New peer configuration
        peer_id = "peer-001"

        # When: Adding peer to hub
        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")

            result = await hub_manager.add_peer(peer_id, sample_peer_config)

        # Then: Should succeed and return True
        assert result is True

        # Then: Configuration should be updated
        assert peer_id in hub_manager.peers
        assert hub_manager.peers[peer_id] == sample_peer_config

        # Then: wg syncconf should be called
        mock_wg.assert_called_once()
        call_args = mock_wg.call_args[0]
        assert 'syncconf' in call_args

    @pytest.mark.asyncio
    async def test_add_peer_writes_config_file(self, hub_manager, sample_peer_config):
        """
        Given new peer config
        When adding to hub
        Then should write updated configuration to file
        """
        # Given: New peer configuration
        peer_id = "peer-002"

        # When: Adding peer to hub
        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")

            await hub_manager.add_peer(peer_id, sample_peer_config)

        # Then: Config file should exist
        assert Path(hub_manager.config_path).exists()

        # Then: Config file should contain peer public key
        config_content = Path(hub_manager.config_path).read_text()
        assert sample_peer_config.public_key in config_content
        assert "[Peer]" in config_content

    @pytest.mark.asyncio
    async def test_add_duplicate_peer_updates_existing(self, hub_manager, sample_peer_config):
        """
        Given existing peer
        When adding same peer again with updated config
        Then should update existing peer configuration
        """
        # Given: Existing peer
        peer_id = "peer-003"

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")
            await hub_manager.add_peer(peer_id, sample_peer_config)

            # When: Adding same peer with updated allowed IPs
            updated_config = PeerConfig(
                public_key=sample_peer_config.public_key,
                allowed_ips=["10.0.0.2/32", "10.0.0.3/32"],
                endpoint=None,
                persistent_keepalive=25,
            )

            result = await hub_manager.add_peer(peer_id, updated_config)

        # Then: Should update successfully
        assert result is True
        assert hub_manager.peers[peer_id].allowed_ips == updated_config.allowed_ips

    @pytest.mark.asyncio
    async def test_add_peer_logs_configuration_change(self, hub_manager, sample_peer_config, caplog):
        """
        Given new peer config
        When adding to hub
        Then should log configuration change
        """
        # Given: New peer configuration
        peer_id = "peer-004"

        # When: Adding peer to hub
        import logging
        caplog.set_level(logging.INFO)

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")

            await hub_manager.add_peer(peer_id, sample_peer_config)

        # Then: Should log the addition
        log_messages = [record.message for record in caplog.records]
        assert any("Added peer" in msg or "peer-004" in msg for msg in log_messages)


class TestRemovePeerFromConfig:
    """Tests for removing peer from WireGuard hub configuration."""

    @pytest.mark.asyncio
    async def test_remove_peer_from_config_success(self, hub_manager, sample_peer_config):
        """
        Given existing peer
        When removing from hub
        Then should update config and drop connections
        """
        # Given: Existing peer
        peer_id = "peer-005"

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")
            await hub_manager.add_peer(peer_id, sample_peer_config)

            # Reset mock to track removal calls
            mock_wg.reset_mock()

            # When: Removing peer
            result = await hub_manager.remove_peer(peer_id)

        # Then: Should succeed
        assert result is True

        # Then: Peer should be removed from internal state
        assert peer_id not in hub_manager.peers

        # Then: wg syncconf should be called
        mock_wg.assert_called()

    @pytest.mark.asyncio
    async def test_remove_peer_updates_config_file(self, hub_manager, sample_peer_config):
        """
        Given existing peer
        When removing from hub
        Then config file should not contain peer anymore
        """
        # Given: Existing peer
        peer_id = "peer-006"

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")
            await hub_manager.add_peer(peer_id, sample_peer_config)

            # When: Removing peer
            await hub_manager.remove_peer(peer_id)

        # Then: Config file should not contain peer's public key
        config_content = Path(hub_manager.config_path).read_text()

        # Config should still exist but peer section removed
        assert "[Interface]" in config_content
        # If no peers left, no [Peer] sections should exist
        if not hub_manager.peers:
            assert sample_peer_config.public_key not in config_content

    @pytest.mark.asyncio
    async def test_remove_nonexistent_peer_raises_error(self, hub_manager):
        """
        Given nonexistent peer ID
        When attempting to remove
        Then should raise PeerNotFoundError
        """
        # Given: Nonexistent peer ID
        peer_id = "nonexistent-peer"

        # When/Then: Should raise error
        with pytest.raises(PeerNotFoundError) as exc_info:
            await hub_manager.remove_peer(peer_id)

        assert peer_id in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_remove_peer_logs_configuration_change(self, hub_manager, sample_peer_config, caplog):
        """
        Given existing peer
        When removing from hub
        Then should log configuration change
        """
        # Given: Existing peer
        peer_id = "peer-007"

        import logging
        caplog.set_level(logging.INFO)

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")
            await hub_manager.add_peer(peer_id, sample_peer_config)

            # When: Removing peer
            await hub_manager.remove_peer(peer_id)

        # Then: Should log the removal
        log_messages = [record.message for record in caplog.records]
        assert any("Removed peer" in msg or peer_id in msg for msg in log_messages)


class TestConfigReloadNoDowntime:
    """Tests for zero-downtime configuration reload."""

    @pytest.mark.asyncio
    async def test_config_reload_uses_syncconf(self, hub_manager, sample_peer_config):
        """
        Given active connections
        When reloading config
        Then should use 'wg syncconf' for zero-downtime reload
        """
        # Given: Active peer
        peer_id = "peer-008"

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")

            # When: Adding peer (which triggers reload)
            await hub_manager.add_peer(peer_id, sample_peer_config)

        # Then: Should use syncconf command
        call_args = str(mock_wg.call_args_list)
        assert 'syncconf' in call_args

    @pytest.mark.asyncio
    async def test_config_reload_preserves_existing_connections(self, hub_manager, sample_peer_config):
        """
        Given active connections
        When reloading config
        Then existing connections should remain active
        """
        # Given: Multiple active peers
        peer_ids = ["peer-009", "peer-010", "peer-011"]

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")

            for peer_id in peer_ids:
                await hub_manager.add_peer(peer_id, sample_peer_config)

            # When: Adding another peer (triggers reload)
            new_peer_config = PeerConfig(
                public_key="aBCDefGhIjKlMnOpQrStUvWxYz0123456789ABCDEF=",
                allowed_ips=["10.0.0.5/32"],
                endpoint=None,
                persistent_keepalive=25,
            )

            await hub_manager.add_peer("peer-012", new_peer_config)

        # Then: All peers should still be in configuration
        assert len(hub_manager.peers) == 4
        for peer_id in peer_ids:
            assert peer_id in hub_manager.peers

    @pytest.mark.asyncio
    async def test_config_reload_handles_failure_gracefully(self, hub_manager, sample_peer_config):
        """
        Given configuration change
        When wg syncconf fails
        Then should raise ConfigReloadError and maintain consistent state
        """
        # Given: Existing state
        peer_id = "peer-013"

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            # First call succeeds (adding initial peer)
            mock_wg.side_effect = [
                (0, "", ""),  # Initial peer add succeeds
                (1, "", "Failed to reload configuration"),  # Reload fails
            ]

            await hub_manager.add_peer(peer_id, sample_peer_config)

            # When: Reload fails on next add
            new_peer_config = PeerConfig(
                public_key="xYZ123ABC456DEF789GHI012JKL345MNO678PQR901=",
                allowed_ips=["10.0.0.6/32"],
                endpoint=None,
                persistent_keepalive=25,
            )

            # Then: Should raise ConfigReloadError
            with pytest.raises(ConfigReloadError):
                await hub_manager.add_peer("peer-014", new_peer_config)

    @pytest.mark.asyncio
    async def test_reload_config_applies_changes_atomically(self, hub_manager, sample_peer_config):
        """
        Given multiple configuration changes
        When reloading
        Then all changes should be applied atomically
        """
        # Given: Multiple peers to add
        peers = {
            "peer-015": sample_peer_config,
            "peer-016": PeerConfig(
                public_key="aAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa=",
                allowed_ips=["10.0.0.7/32"],
                endpoint=None,
                persistent_keepalive=25,
            ),
        }

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")

            # When: Adding peers
            for peer_id, config in peers.items():
                await hub_manager.add_peer(peer_id, config)

        # Then: All peers should be present
        assert len(hub_manager.peers) == len(peers)
        for peer_id in peers:
            assert peer_id in hub_manager.peers


class TestPeerConnectivityVerification:
    """Tests for peer connectivity verification."""

    @pytest.mark.asyncio
    async def test_verify_peer_connectivity_success(self, hub_manager, sample_peer_config):
        """
        Given added peer
        When verifying connectivity
        Then should ping peer and verify response
        """
        # Given: Added peer
        peer_id = "peer-017"

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")
            await hub_manager.add_peer(peer_id, sample_peer_config)

            # When: Verifying connectivity
            with patch.object(hub_manager, '_ping_peer', new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = True

                result = await hub_manager.verify_peer_connectivity(peer_id)

        # Then: Should return True
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_peer_connectivity_timeout(self, hub_manager, sample_peer_config):
        """
        Given added peer
        When peer is unreachable
        Then should timeout and return False
        """
        # Given: Added peer
        peer_id = "peer-018"

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")
            await hub_manager.add_peer(peer_id, sample_peer_config)

            # When: Verifying connectivity with unreachable peer
            with patch.object(hub_manager, '_ping_peer', new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = False

                result = await hub_manager.verify_peer_connectivity(peer_id, timeout=1)

        # Then: Should return False
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_nonexistent_peer_raises_error(self, hub_manager):
        """
        Given nonexistent peer ID
        When verifying connectivity
        Then should raise PeerNotFoundError
        """
        # Given: Nonexistent peer ID
        peer_id = "nonexistent-peer"

        # When/Then: Should raise error
        with pytest.raises(PeerNotFoundError):
            await hub_manager.verify_peer_connectivity(peer_id)

    @pytest.mark.asyncio
    async def test_verify_connectivity_uses_peer_allowed_ip(self, hub_manager, sample_peer_config):
        """
        Given added peer with allowed IPs
        When verifying connectivity
        Then should ping first allowed IP
        """
        # Given: Added peer
        peer_id = "peer-019"

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")
            await hub_manager.add_peer(peer_id, sample_peer_config)

            # When: Verifying connectivity
            with patch.object(hub_manager, '_ping_peer', new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = True

                await hub_manager.verify_peer_connectivity(peer_id)

        # Then: Should call ping with first allowed IP
        mock_ping.assert_called_once()
        # Extract IP from first allowed_ips entry (e.g., "10.0.0.2/32" -> "10.0.0.2")
        expected_ip = sample_peer_config.allowed_ips[0].split('/')[0]
        assert expected_ip in str(mock_ping.call_args)


class TestWireGuardHubManagerIntegration:
    """Integration tests for WireGuard hub manager."""

    @pytest.mark.asyncio
    async def test_full_peer_lifecycle(self, hub_manager, sample_peer_config):
        """
        Given hub manager
        When performing full peer lifecycle (add, verify, remove)
        Then all operations should succeed
        """
        # Given: Hub manager and peer config
        peer_id = "peer-020"

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")

            with patch.object(hub_manager, '_ping_peer', new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = True

                # When: Adding peer
                add_result = await hub_manager.add_peer(peer_id, sample_peer_config)
                assert add_result is True

                # When: Verifying connectivity
                verify_result = await hub_manager.verify_peer_connectivity(peer_id)
                assert verify_result is True

                # When: Removing peer
                remove_result = await hub_manager.remove_peer(peer_id)
                assert remove_result is True

        # Then: Peer should be completely removed
        assert peer_id not in hub_manager.peers

    @pytest.mark.asyncio
    async def test_concurrent_peer_operations(self, hub_manager, sample_peer_config):
        """
        Given hub manager
        When performing concurrent peer operations
        Then should handle them safely
        """
        # Given: Multiple peer configurations
        peer_configs = {
            f"peer-{i:03d}": PeerConfig(
                public_key=f"peer{i}key{'=' * 36}",
                allowed_ips=[f"10.0.0.{i+10}/32"],
                endpoint=None,
                persistent_keepalive=25,
            )
            for i in range(5)
        }

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")

            # When: Adding peers concurrently
            tasks = [
                hub_manager.add_peer(peer_id, config)
                for peer_id, config in peer_configs.items()
            ]

            results = await asyncio.gather(*tasks)

        # Then: All operations should succeed
        assert all(results)
        assert len(hub_manager.peers) == len(peer_configs)

    @pytest.mark.asyncio
    async def test_get_peer_status(self, hub_manager, sample_peer_config):
        """
        Given added peer
        When retrieving peer status
        Then should return current peer information
        """
        # Given: Added peer
        peer_id = "peer-021"

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")
            await hub_manager.add_peer(peer_id, sample_peer_config)

            # When: Getting peer status
            status = await hub_manager.get_peer_status(peer_id)

        # Then: Should return peer configuration
        assert status is not None
        assert status.public_key == sample_peer_config.public_key
        assert status.allowed_ips == sample_peer_config.allowed_ips

    @pytest.mark.asyncio
    async def test_list_all_peers(self, hub_manager, sample_peer_config):
        """
        Given multiple added peers
        When listing all peers
        Then should return all peer IDs
        """
        # Given: Multiple peers
        peer_ids = ["peer-022", "peer-023", "peer-024"]

        with patch.object(hub_manager, '_execute_wg_command', new_callable=AsyncMock) as mock_wg:
            mock_wg.return_value = (0, "", "")

            for peer_id in peer_ids:
                await hub_manager.add_peer(peer_id, sample_peer_config)

            # When: Listing all peers
            all_peers = await hub_manager.list_peers()

        # Then: Should return all peer IDs
        assert len(all_peers) == len(peer_ids)
        for peer_id in peer_ids:
            assert peer_id in all_peers
