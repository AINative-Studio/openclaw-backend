"""
Unit tests for libp2p bootstrap module components.

This module contains unit tests for data classes and utility functions.
"""

import pytest
from backend.p2p.libp2p_bootstrap import (
    PeerInfo,
    BootstrapResult,
    DHTStatus,
    LibP2PBootstrap,
)


def test_peer_info_creation():
    """
    Given peer information
    When creating PeerInfo instance
    Then should store all attributes correctly
    """
    # Given
    peer_id = "12D3KooWTest123"
    multiaddrs = ["/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWTest123"]
    protocols = ["/ipfs/id/1.0.0"]

    # When
    peer = PeerInfo(
        peer_id=peer_id,
        multiaddrs=multiaddrs,
        protocols=protocols,
        latency_ms=45.2
    )

    # Then
    assert peer.peer_id == peer_id
    assert peer.multiaddrs == multiaddrs
    assert peer.protocols == protocols
    assert peer.latency_ms == 45.2


def test_peer_info_to_dict():
    """
    Given PeerInfo instance
    When converting to dict
    Then should return correct dictionary representation
    """
    # Given
    peer = PeerInfo(
        peer_id="12D3KooWTest123",
        multiaddrs=["/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWTest123"],
        protocols=["/ipfs/id/1.0.0"],
        latency_ms=45.2
    )

    # When
    result = peer.to_dict()

    # Then
    assert result['peer_id'] == peer.peer_id
    assert result['multiaddrs'] == peer.multiaddrs
    assert result['protocols'] == peer.protocols
    assert result['latency_ms'] == peer.latency_ms


def test_bootstrap_result_success():
    """
    Given successful bootstrap connection
    When creating BootstrapResult
    Then should indicate success with peer info
    """
    # Given/When
    result = BootstrapResult(
        success=True,
        peer_id="12D3KooWMyPeer",
        connected_bootstrap_nodes=["/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWBoot"],
        connected_peer_count=5,
        retry_count=0
    )

    # Then
    assert result.success is True
    assert result.peer_id == "12D3KooWMyPeer"
    assert len(result.connected_bootstrap_nodes) == 1
    assert result.connected_peer_count == 5
    assert result.retry_count == 0
    assert result.error_message is None


def test_bootstrap_result_failure():
    """
    Given failed bootstrap connection
    When creating BootstrapResult
    Then should indicate failure with error message
    """
    # Given/When
    result = BootstrapResult(
        success=False,
        failed_bootstrap_nodes=[
            "/ip4/192.0.2.1/tcp/4001/p2p/12D3KooWUnreachable"
        ],
        retry_count=3,
        error_message="Connection timeout"
    )

    # Then
    assert result.success is False
    assert result.peer_id is None
    assert len(result.failed_bootstrap_nodes) == 1
    assert result.retry_count == 3
    assert result.error_message == "Connection timeout"


def test_bootstrap_result_to_dict():
    """
    Given BootstrapResult instance
    When converting to dict
    Then should return correct dictionary representation
    """
    # Given
    result = BootstrapResult(
        success=True,
        peer_id="12D3KooWTest",
        connected_bootstrap_nodes=["/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWBoot"],
        connected_peer_count=3,
        retry_count=1
    )

    # When
    result_dict = result.to_dict()

    # Then
    assert result_dict['success'] is True
    assert result_dict['peer_id'] == "12D3KooWTest"
    assert len(result_dict['connected_bootstrap_nodes']) == 1
    assert result_dict['connected_peer_count'] == 3
    assert result_dict['retry_count'] == 1


def test_dht_status_connected():
    """
    Given DHT connected
    When creating DHTStatus
    Then should indicate connected status
    """
    # Given/When
    status = DHTStatus(
        is_connected=True,
        routing_table_size=25,
        local_peer_id="12D3KooWMyPeer",
        mode="client"
    )

    # Then
    assert status.is_connected is True
    assert status.routing_table_size == 25
    assert status.local_peer_id == "12D3KooWMyPeer"
    assert status.mode == "client"


def test_dht_status_to_dict():
    """
    Given DHTStatus instance
    When converting to dict
    Then should return correct dictionary representation
    """
    # Given
    status = DHTStatus(
        is_connected=True,
        routing_table_size=25,
        local_peer_id="12D3KooWMyPeer",
        mode="server"
    )

    # When
    status_dict = status.to_dict()

    # Then
    assert status_dict['is_connected'] is True
    assert status_dict['routing_table_size'] == 25
    assert status_dict['local_peer_id'] == "12D3KooWMyPeer"
    assert status_dict['mode'] == "server"


@pytest.mark.asyncio
async def test_libp2p_bootstrap_discover_peers():
    """
    Given LibP2PBootstrap instance
    When discovering peers
    Then should return empty list (placeholder)
    """
    # Given
    bootstrap = LibP2PBootstrap(
        bootstrap_addresses=["/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWBoot"],
        max_retries=3,
        retry_delay=1.0
    )

    # When
    peers = await bootstrap.discover_peers()

    # Then
    assert isinstance(peers, list)
    assert len(peers) == 0  # Placeholder implementation


def test_libp2p_bootstrap_parse_multiaddr():
    """
    Given multiaddr string
    When parsing
    Then should extract protocol, address, port, and peer_id
    """
    # Given
    bootstrap = LibP2PBootstrap(
        bootstrap_addresses=["/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWBoot"]
    )
    multiaddr = "/ip4/192.168.1.10/tcp/4001/p2p/12D3KooWTest123"

    # When
    parsed = bootstrap.parse_multiaddr(multiaddr)

    # Then
    assert parsed['protocol'] == 'ip4'
    assert parsed['address'] == '192.168.1.10'
    assert parsed['port'] == 4001
    assert parsed['peer_id'] == '12D3KooWTest123'


def test_libp2p_bootstrap_update_peer_store():
    """
    Given list of peers
    When updating peer store
    Then should add peers to internal store
    """
    # Given
    bootstrap = LibP2PBootstrap(
        bootstrap_addresses=["/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWBoot"]
    )
    peers = ["12D3KooWPeer1", "12D3KooWPeer2", "12D3KooWPeer3"]

    # When
    bootstrap.update_peer_store(peers)

    # Then
    assert bootstrap.get_peer_count() == 3
    assert all(peer in bootstrap.peer_store for peer in peers)


def test_libp2p_bootstrap_update_peer_store_no_duplicates():
    """
    Given duplicate peers
    When updating peer store
    Then should not add duplicates
    """
    # Given
    bootstrap = LibP2PBootstrap(
        bootstrap_addresses=["/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWBoot"]
    )

    # When
    bootstrap.update_peer_store(["12D3KooWPeer1", "12D3KooWPeer2"])
    bootstrap.update_peer_store(["12D3KooWPeer2", "12D3KooWPeer3"])

    # Then
    assert bootstrap.get_peer_count() == 3
    assert bootstrap.peer_store.count("12D3KooWPeer2") == 1


def test_libp2p_bootstrap_validate_address_valid():
    """
    Given valid multiaddr
    When validating
    Then should return True
    """
    # Given
    bootstrap = LibP2PBootstrap(
        bootstrap_addresses=["/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWBoot"]
    )
    valid_addr = "/ip4/192.168.1.10/tcp/4001/p2p/12D3KooWTest123"

    # When
    result = bootstrap.validate_address(valid_addr)

    # Then
    assert result is True


def test_libp2p_bootstrap_validate_address_invalid():
    """
    Given invalid multiaddr
    When validating
    Then should return False
    """
    # Given
    bootstrap = LibP2PBootstrap(
        bootstrap_addresses=["/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWBoot"]
    )

    # When/Then - various invalid addresses
    assert bootstrap.validate_address("") is False
    assert bootstrap.validate_address(None) is False
    assert bootstrap.validate_address("not-a-multiaddr") is False
    assert bootstrap.validate_address("/ip4/192.168.1.10") is False  # Missing peer_id


def test_libp2p_bootstrap_get_peer_count():
    """
    Given peer store with peers
    When getting count
    Then should return correct number
    """
    # Given
    bootstrap = LibP2PBootstrap(
        bootstrap_addresses=["/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWBoot"]
    )

    # When - initially empty
    assert bootstrap.get_peer_count() == 0

    # When - add peers
    bootstrap.update_peer_store(["Peer1", "Peer2", "Peer3"])
    assert bootstrap.get_peer_count() == 3
