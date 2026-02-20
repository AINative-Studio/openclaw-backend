"""
Test WireGuard Node Connection Initialization

Tests for E1-S5: Node WireGuard Connection Initialization
BDD-style tests following Given/When/Then pattern

Story Points: 3
Acceptance Criteria:
- Apply WireGuard configuration
- Establish connection to hub
- Verify connectivity
- Register with DBOS
- Retry logic with exponential backoff
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta, timezone
from pathlib import Path


class TestWireGuardNodeConnector:
    """Test suite for WireGuard node connection initialization"""

    @pytest.fixture
    def mock_config(self):
        """Given a valid WireGuard configuration"""
        return {
            "interface_name": "wg0",
            "private_key": "cGVlckEtcHJpdmF0ZS1rZXktdGVzdA==",
            "address": "10.0.0.10/24",
            "listen_port": 51820,
            "hub": {
                "public_key": "aHViLXB1YmxpYy1rZXktdGVzdA==",
                "endpoint": "203.0.113.1:51820",
                "allowed_ips": "10.0.0.0/24",
                "persistent_keepalive": 25
            }
        }

    @pytest.fixture
    def mock_dbos_client(self):
        """Given a mock DBOS client for registration"""
        client = AsyncMock()
        client.register_node = AsyncMock(return_value={
            "node_id": "test-node-123",
            "registered_at": datetime.now(timezone.utc).isoformat()
        })
        return client

    @pytest.mark.asyncio
    async def test_connect_to_hub_success(self, mock_config, mock_dbos_client):
        """
        Given valid config, when connecting to hub,
        then should establish tunnel and verify connectivity
        """
        from backend.networking.wireguard_node_connector import WireGuardNodeConnector

        connector = WireGuardNodeConnector(
            config=mock_config,
            dbos_client=mock_dbos_client
        )

        with patch('backend.networking.wireguard_node_connector.subprocess.run') as mock_run, \
             patch('backend.networking.wireguard_node_connector.ping_host', return_value=True) as mock_ping:

            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            # When: connecting to hub
            result = await connector.connect_to_hub()

            # Then: should establish tunnel successfully
            assert result["success"] is True
            assert result["interface"] == "wg0"
            assert "connected_at" in result

            # Then: should apply WireGuard configuration
            mock_run.assert_called()
            wg_commands = [call for call in mock_run.call_args_list
                          if 'wg' in str(call) or 'ip' in str(call)]
            assert len(wg_commands) > 0

            # Then: should verify connectivity
            mock_ping.assert_called_once()

            # Then: should register with DBOS
            mock_dbos_client.register_node.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_to_hub_retry_on_failure(self, mock_config, mock_dbos_client):
        """
        Given hub unavailable, when connecting,
        then should retry with exponential backoff
        """
        from backend.networking.wireguard_node_connector import WireGuardNodeConnector

        connector = WireGuardNodeConnector(
            config=mock_config,
            dbos_client=mock_dbos_client,
            max_retries=3,
            initial_backoff=0.1
        )

        with patch('backend.networking.wireguard_node_connector.subprocess.run') as mock_run, \
             patch('backend.networking.wireguard_node_connector.ping_host') as mock_ping, \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:

            # Given: hub unavailable (ping fails initially)
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            mock_ping.side_effect = [False, False, True]  # Fail twice, succeed on third

            # When: connecting to hub
            result = await connector.connect_to_hub()

            # Then: should retry with exponential backoff
            assert result["success"] is True
            assert mock_ping.call_count == 3
            assert mock_sleep.call_count == 2  # Sleep after first two failures

            # Then: should use exponential backoff
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert sleep_calls[0] == 0.1  # Initial backoff
            assert sleep_calls[1] == 0.2  # 2x backoff

    @pytest.mark.asyncio
    async def test_connect_to_hub_max_retries_exceeded(self, mock_config, mock_dbos_client):
        """
        Given hub permanently unavailable, when max retries exceeded,
        then should raise connection error
        """
        from backend.networking.wireguard_node_connector import WireGuardNodeConnector, ConnectionError

        connector = WireGuardNodeConnector(
            config=mock_config,
            dbos_client=mock_dbos_client,
            max_retries=3,
            initial_backoff=0.1
        )

        with patch('backend.networking.wireguard_node_connector.subprocess.run') as mock_run, \
             patch('backend.networking.wireguard_node_connector.ping_host', return_value=False) as mock_ping, \
             patch('asyncio.sleep', new_callable=AsyncMock):

            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            # When: connecting fails repeatedly
            # Then: should raise ConnectionError after max retries
            with pytest.raises(ConnectionError) as exc_info:
                await connector.connect_to_hub()

            assert "Max retries exceeded" in str(exc_info.value)
            assert mock_ping.call_count == 4  # Initial + 3 retries

    @pytest.mark.asyncio
    async def test_connection_health_check(self, mock_config, mock_dbos_client):
        """
        Given established connection, when checking health,
        then should ping hub and verify response
        """
        from backend.networking.wireguard_node_connector import WireGuardNodeConnector

        connector = WireGuardNodeConnector(
            config=mock_config,
            dbos_client=mock_dbos_client
        )

        # Given: established connection
        connector._connected = True
        connector._connection_time = datetime.now(timezone.utc)

        with patch('backend.networking.wireguard_node_connector.ping_host') as mock_ping, \
             patch('backend.networking.wireguard_node_connector.subprocess.run') as mock_run:

            # Given: successful ping
            mock_ping.return_value = True
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="latest handshake: 1 second ago\n"
            )

            # When: checking health
            health = await connector.check_health()

            # Then: should verify connectivity
            assert health["status"] == "healthy"
            assert health["connected"] is True
            assert "handshake_age" in health
            assert "uptime_seconds" in health

            # Then: should ping hub
            mock_ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_health_check_stale_handshake(self, mock_config, mock_dbos_client):
        """
        Given stale WireGuard handshake, when checking health,
        then should report degraded status
        """
        from backend.networking.wireguard_node_connector import WireGuardNodeConnector

        connector = WireGuardNodeConnector(
            config=mock_config,
            dbos_client=mock_dbos_client
        )
        connector._connected = True

        with patch('backend.networking.wireguard_node_connector.ping_host', return_value=True), \
             patch('backend.networking.wireguard_node_connector.subprocess.run') as mock_run:

            # Given: stale handshake (>3 minutes old)
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="latest handshake: 4 minutes ago\n"
            )

            # When: checking health
            health = await connector.check_health()

            # Then: should report degraded status
            assert health["status"] == "degraded"
            assert health["connected"] is True
            assert "handshake_age" in health
            assert health["handshake_age"] > 180  # > 3 minutes

    @pytest.mark.asyncio
    async def test_apply_wireguard_configuration(self, mock_config, mock_dbos_client):
        """
        Given WireGuard config, when applying,
        then should configure interface correctly
        """
        from backend.networking.wireguard_node_connector import WireGuardNodeConnector

        connector = WireGuardNodeConnector(
            config=mock_config,
            dbos_client=mock_dbos_client
        )

        with patch('backend.networking.wireguard_node_connector.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            # When: applying configuration
            await connector._apply_wireguard_config()

            # Then: should create interface
            # Extract command arguments from mock calls
            commands = []
            for call in mock_run.call_args_list:
                args = call[0]
                if args and isinstance(args[0], list):
                    commands.append(' '.join(args[0]))

            assert any('ip link add' in cmd for cmd in commands)
            assert any('wg0' in cmd for cmd in commands)

            # Then: should set private key
            assert any('wg set' in cmd for cmd in commands)

            # Then: should configure peer (hub)
            assert any('peer' in cmd and mock_config['hub']['public_key'] in cmd
                      for cmd in commands)

            # Then: should bring interface up
            assert any('ip link set' in cmd and 'up' in cmd for cmd in commands)

    @pytest.mark.asyncio
    async def test_disconnect_cleanup(self, mock_config, mock_dbos_client):
        """
        Given active connection, when disconnecting,
        then should cleanup interface properly
        """
        from backend.networking.wireguard_node_connector import WireGuardNodeConnector

        connector = WireGuardNodeConnector(
            config=mock_config,
            dbos_client=mock_dbos_client
        )
        connector._connected = True

        with patch('backend.networking.wireguard_node_connector.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            # When: disconnecting
            await connector.disconnect()

            # Then: should bring interface down
            commands = []
            for call in mock_run.call_args_list:
                args = call[0]
                if args and isinstance(args[0], list):
                    commands.append(' '.join(args[0]))

            assert any('ip link set' in cmd and 'down' in cmd for cmd in commands)

            # Then: should delete interface
            assert any('ip link delete' in cmd and 'wg0' in cmd for cmd in commands)

            # Then: should reset connection state
            assert connector._connected is False

    @pytest.mark.asyncio
    async def test_register_with_dbos(self, mock_config, mock_dbos_client):
        """
        Given successful connection, when registering,
        then should register node with DBOS
        """
        from backend.networking.wireguard_node_connector import WireGuardNodeConnector

        connector = WireGuardNodeConnector(
            config=mock_config,
            dbos_client=mock_dbos_client
        )

        # When: registering with DBOS
        result = await connector._register_with_dbos()

        # Then: should call DBOS registration
        mock_dbos_client.register_node.assert_called_once()

        # Then: should include node metadata
        call_kwargs = mock_dbos_client.register_node.call_args[1]
        assert "wireguard_address" in call_kwargs
        assert call_kwargs["wireguard_address"] == "10.0.0.10/24"

        # Then: should return registration result
        assert result["node_id"] == "test-node-123"
        assert "registered_at" in result

    def test_exponential_backoff_calculation(self):
        """
        Given retry attempt number, when calculating backoff,
        then should use exponential backoff with jitter
        """
        from backend.networking.wireguard_node_connector import WireGuardNodeConnector

        # Minimal valid config for initialization
        minimal_config = {
            "interface_name": "wg0",
            "private_key": "test-key",
            "address": "10.0.0.10/24",
            "hub": {
                "public_key": "hub-key",
                "endpoint": "203.0.113.1:51820",
                "allowed_ips": "10.0.0.0/24"
            }
        }

        connector = WireGuardNodeConnector(
            config=minimal_config,
            dbos_client=None,
            initial_backoff=1.0,
            max_backoff=60.0
        )

        # When: calculating backoff for different attempts
        backoff_0 = connector._calculate_backoff(0)
        backoff_1 = connector._calculate_backoff(1)
        backoff_2 = connector._calculate_backoff(2)
        backoff_10 = connector._calculate_backoff(10)

        # Then: should use exponential backoff
        assert backoff_0 == 1.0
        assert backoff_1 == 2.0
        assert backoff_2 == 4.0

        # Then: should cap at max_backoff
        assert backoff_10 == 60.0

    @pytest.mark.asyncio
    async def test_config_validation(self):
        """
        Given invalid config, when initializing connector,
        then should raise validation error
        """
        from backend.networking.wireguard_node_connector import WireGuardNodeConnector, ConfigValidationError

        # Given: invalid config (missing required fields)
        invalid_config = {
            "interface_name": "wg0"
            # Missing private_key, address, hub
        }

        # When/Then: should raise validation error
        with pytest.raises(ConfigValidationError) as exc_info:
            WireGuardNodeConnector(config=invalid_config, dbos_client=None)

        assert "private_key" in str(exc_info.value) or "hub" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_connection_timeout(self, mock_config, mock_dbos_client):
        """
        Given connection attempt, when timeout exceeded,
        then should raise timeout error
        """
        from backend.networking.wireguard_node_connector import WireGuardNodeConnector, ConnectionTimeout

        connector = WireGuardNodeConnector(
            config=mock_config,
            dbos_client=mock_dbos_client,
            connection_timeout=1.0
        )

        with patch('backend.networking.wireguard_node_connector.subprocess.run') as mock_run, \
             patch('backend.networking.wireguard_node_connector.ping_host') as mock_ping:

            # Given: very slow connection (simulated by sleep)
            async def slow_ping(*args, **kwargs):
                await asyncio.sleep(2.0)
                return True

            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            mock_ping.side_effect = slow_ping

            # When/Then: should raise timeout error
            with pytest.raises(ConnectionTimeout):
                await connector.connect_to_hub()
