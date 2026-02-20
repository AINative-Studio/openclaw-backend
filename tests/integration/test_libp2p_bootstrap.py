"""
Integration tests for libp2p bootstrap node connectivity.

This module tests the bootstrap node connection, peer discovery,
and fallback mechanisms following TDD/BDD principles.
"""

import pytest
import asyncio
from typing import List, Optional
from unittest.mock import Mock, AsyncMock, patch


@pytest.mark.asyncio
async def test_connect_to_bootstrap_node():
    """
    Given bootstrap multiaddr
    When connecting
    Then should establish connection and sync peers
    """
    from backend.p2p.libp2p_bootstrap import LibP2PBootstrapClient

    # Given: A bootstrap node multiaddr
    bootstrap_multiaddr = "/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWEyopopk..."

    # When: Connecting to the bootstrap node (using mock binary path)
    client = LibP2PBootstrapClient(go_binary_path="/mock/path/bootstrap-node")
    result = await client.connect_to_bootstrap(bootstrap_multiaddr)

    # Then: Should establish connection successfully
    assert result.success is True
    assert result.peer_id is not None
    assert result.connected_peer_count >= 0
    assert bootstrap_multiaddr in result.connected_bootstrap_nodes


@pytest.mark.asyncio
async def test_connect_to_bootstrap_node_with_timeout():
    """
    Given bootstrap multiaddr
    When connecting with timeout
    Then should respect timeout and fail gracefully if exceeded
    """
    from backend.p2p.libp2p_bootstrap import LibP2PBootstrapClient

    # Given: A non-responsive bootstrap node
    unreachable_multiaddr = "/ip4/192.0.2.1/tcp/4001/p2p/12D3KooWUnreachable"

    # When: Connecting with short timeout
    client = LibP2PBootstrapClient(go_binary_path="/mock/path/bootstrap-node")
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            client.connect_to_bootstrap(unreachable_multiaddr),
            timeout=2.0
        )


@pytest.mark.asyncio
async def test_discover_peers_via_dht():
    """
    Given DHT bootstrap
    When querying
    Then should return list of active peers
    """
    from backend.p2p.libp2p_bootstrap import LibP2PBootstrapClient

    # Given: A client connected to bootstrap node
    bootstrap_multiaddr = "/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWBootstrap"
    client = LibP2PBootstrapClient(go_binary_path="/mock/path/bootstrap-node")
    await client.connect_to_bootstrap(bootstrap_multiaddr)

    # When: Querying DHT for peers
    peers = await client.discover_peers_via_dht()

    # Then: Should return list of active peers
    assert isinstance(peers, list)
    assert len(peers) >= 0

    # Each peer should have required attributes
    for peer in peers:
        assert hasattr(peer, 'peer_id')
        assert hasattr(peer, 'multiaddrs')
        assert len(peer.multiaddrs) > 0


@pytest.mark.asyncio
async def test_discover_peers_via_dht_empty_network():
    """
    Given DHT bootstrap in empty network
    When querying
    Then should return empty peer list
    """
    from backend.p2p.libp2p_bootstrap import LibP2PBootstrapClient

    # Given: A standalone bootstrap node with no other peers
    bootstrap_multiaddr = "/ip4/127.0.0.1/tcp/4002/p2p/12D3KooWStandalone"
    client = LibP2PBootstrapClient(go_binary_path="/mock/path/bootstrap-node")
    await client.connect_to_bootstrap(bootstrap_multiaddr)

    # When: Querying DHT for peers
    peers = await client.discover_peers_via_dht()

    # Then: Should return empty list or only bootstrap node
    assert isinstance(peers, list)


@pytest.mark.asyncio
async def test_bootstrap_fallback():
    """
    Given primary bootstrap unreachable
    When connecting
    Then should try secondary bootstrap nodes
    """
    from backend.p2p.libp2p_bootstrap import LibP2PBootstrapClient

    # Given: Multiple bootstrap nodes, first one unreachable
    bootstrap_nodes = [
        "/ip4/192.0.2.1/tcp/4001/p2p/12D3KooWUnreachable1",
        "/ip4/192.0.2.2/tcp/4001/p2p/12D3KooWUnreachable2",
        "/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWReachable"
    ]

    # When: Connecting with fallback
    client = LibP2PBootstrapClient(go_binary_path="/mock/path/bootstrap-node")
    result = await client.connect_with_fallback(bootstrap_nodes, timeout=2.0)

    # Then: Should connect to the reachable bootstrap node
    assert result.success is True
    assert result.connected_bootstrap_nodes[-1] == bootstrap_nodes[2]
    assert len(result.failed_bootstrap_nodes) == 2


@pytest.mark.asyncio
async def test_bootstrap_fallback_all_unreachable():
    """
    Given all bootstrap nodes unreachable
    When connecting with fallback
    Then should fail with appropriate error
    """
    from backend.p2p.libp2p_bootstrap import LibP2PBootstrapClient, BootstrapConnectionError

    # Given: All bootstrap nodes unreachable
    bootstrap_nodes = [
        "/ip4/192.0.2.1/tcp/4001/p2p/12D3KooWUnreachable1",
        "/ip4/192.0.2.2/tcp/4001/p2p/12D3KooWUnreachable2"
    ]

    # When: Attempting to connect with fallback
    client = LibP2PBootstrapClient(go_binary_path="/mock/path/bootstrap-node")

    # Then: Should raise BootstrapConnectionError
    with pytest.raises(BootstrapConnectionError) as exc_info:
        await client.connect_with_fallback(bootstrap_nodes, timeout=2.0)

    assert "All bootstrap nodes unreachable" in str(exc_info.value)


@pytest.mark.asyncio
async def test_update_local_peer_store():
    """
    Given discovered peers
    When updating local peer store
    Then should persist peer information
    """
    from backend.p2p.libp2p_bootstrap import LibP2PBootstrapClient

    # Given: A client with discovered peers
    bootstrap_multiaddr = "/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWBootstrap"
    client = LibP2PBootstrapClient(go_binary_path="/mock/path/bootstrap-node")
    await client.connect_to_bootstrap(bootstrap_multiaddr)
    peers = await client.discover_peers_via_dht()

    # When: Updating local peer store
    await client.update_local_peer_store(peers)

    # Then: Should persist peer information
    stored_peers = await client.get_stored_peers()
    assert len(stored_peers) == len(peers)

    for stored_peer, original_peer in zip(stored_peers, peers):
        assert stored_peer.peer_id == original_peer.peer_id


@pytest.mark.asyncio
async def test_bootstrap_connection_retry():
    """
    Given temporary connection failure
    When retrying connection
    Then should retry with exponential backoff
    """
    from backend.p2p.libp2p_bootstrap import LibP2PBootstrapClient

    # Given: A bootstrap node that fails initially but succeeds on retry
    bootstrap_multiaddr = "/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWFlaky"

    # When: Connecting with retry enabled
    client = LibP2PBootstrapClient(go_binary_path="/mock/path/bootstrap-node")
    result = await client.connect_to_bootstrap(
        bootstrap_multiaddr,
        max_retries=3,
        initial_backoff=0.1
    )

    # Then: Should eventually succeed
    assert result.success is True
    assert result.retry_count >= 0


@pytest.mark.asyncio
async def test_establish_dht_connectivity():
    """
    Given bootstrap connection established
    When initializing DHT
    Then should establish DHT connectivity
    """
    from backend.p2p.libp2p_bootstrap import LibP2PBootstrapClient

    # Given: A connected client
    bootstrap_multiaddr = "/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWBootstrap"
    client = LibP2PBootstrapClient(go_binary_path="/mock/path/bootstrap-node")
    await client.connect_to_bootstrap(bootstrap_multiaddr)

    # When: Initializing DHT
    dht_status = await client.get_dht_status()

    # Then: Should have DHT connectivity
    assert dht_status.is_connected is True
    assert dht_status.routing_table_size >= 0


@pytest.mark.asyncio
async def test_concurrent_bootstrap_connections():
    """
    Given multiple bootstrap nodes
    When connecting concurrently
    Then should establish connections in parallel
    """
    from backend.p2p.libp2p_bootstrap import LibP2PBootstrapClient

    # Given: Multiple bootstrap nodes
    bootstrap_nodes = [
        "/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWBootstrap1",
        "/ip4/127.0.0.1/tcp/4002/p2p/12D3KooWBootstrap2",
        "/ip4/127.0.0.1/tcp/4003/p2p/12D3KooWBootstrap3"
    ]

    # When: Connecting concurrently
    client = LibP2PBootstrapClient(go_binary_path="/mock/path/bootstrap-node")
    results = await client.connect_to_multiple_bootstraps(bootstrap_nodes)

    # Then: Should establish multiple connections
    successful_connections = [r for r in results if r.success]
    assert len(successful_connections) >= 1
    assert len(results) == len(bootstrap_nodes)


# Fixtures for test setup
@pytest.fixture
async def mock_bootstrap_server():
    """
    Provides a mock bootstrap server for testing.
    """
    # This would start a real Go bootstrap node in a subprocess
    # For now, we'll mock it
    yield
    # Cleanup


@pytest.fixture
async def libp2p_client():
    """
    Provides a configured LibP2PBootstrapClient for testing.
    """
    from backend.p2p.libp2p_bootstrap import LibP2PBootstrapClient

    client = LibP2PBootstrapClient(go_binary_path="/mock/path/bootstrap-node")
    yield client

    # Cleanup
    await client.close()
