"""
WireGuard Configuration Schema Tests

Tests WireGuard configuration generation, validation, and IP assignment
for P2P agent swarm networking.

Follows TDD/BDD principles with comprehensive coverage.
"""

import pytest
from ipaddress import IPv4Address, IPv4Network
from pydantic import ValidationError
from typing import Set

from backend.networking.wireguard_config import (
    WireGuardConfig,
    WireGuardPeer,
    WireGuardInterface,
    IPAddressAllocator,
    generate_wireguard_keypair,
    generate_node_config,
)


class TestWireGuardKeypairGeneration:
    """Test WireGuard keypair generation"""

    def test_generate_keypair_returns_valid_keys(self):
        """
        GIVEN a request to generate WireGuard keys
        WHEN generating a keypair
        THEN it should return valid private and public keys
        """
        # Act
        private_key, public_key = generate_wireguard_keypair()

        # Assert
        assert private_key is not None
        assert public_key is not None
        assert len(private_key) == 44  # Base64 encoded 32-byte key
        assert len(public_key) == 44
        assert private_key != public_key

    def test_generate_keypair_unique_keys(self):
        """
        GIVEN multiple keypair generation requests
        WHEN generating keypairs
        THEN each keypair should be unique
        """
        # Act
        key1_private, key1_public = generate_wireguard_keypair()
        key2_private, key2_public = generate_wireguard_keypair()

        # Assert
        assert key1_private != key2_private
        assert key1_public != key2_public


class TestWireGuardInterface:
    """Test WireGuard interface configuration"""

    def test_interface_creation_valid(self):
        """
        GIVEN valid interface parameters
        WHEN creating a WireGuard interface
        THEN it should create valid interface configuration
        """
        # Arrange
        private_key = "oK56DE9Ue9zK76rAc8pBl6opph+1v36lm7cXXsQKrQM="
        address = "10.0.0.2/24"
        listen_port = 51820

        # Act
        interface = WireGuardInterface(
            private_key=private_key,
            address=address,
            listen_port=listen_port,
        )

        # Assert
        assert interface.private_key == private_key
        assert interface.address == address
        assert interface.listen_port == listen_port

    def test_interface_validation_invalid_key_length(self):
        """
        GIVEN an invalid private key length
        WHEN creating a WireGuard interface
        THEN it should raise ValidationError
        """
        # Arrange
        invalid_key = "short_key"

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            WireGuardInterface(
                private_key=invalid_key,
                address="10.0.0.2/24",
                listen_port=51820,
            )

        assert "private_key" in str(exc_info.value)

    def test_interface_validation_invalid_port(self):
        """
        GIVEN an invalid port number
        WHEN creating a WireGuard interface
        THEN it should raise ValidationError
        """
        # Arrange
        private_key = "oK56DE9Ue9zK76rAc8pBl6opph+1v36lm7cXXsQKrQM="

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            WireGuardInterface(
                private_key=private_key,
                address="10.0.0.2/24",
                listen_port=70000,  # Invalid port
            )

        assert "listen_port" in str(exc_info.value)


class TestWireGuardPeer:
    """Test WireGuard peer configuration"""

    def test_peer_creation_valid(self):
        """
        GIVEN valid peer parameters
        WHEN creating a WireGuard peer
        THEN it should create valid peer configuration
        """
        # Arrange
        public_key = "HIgo9xNzJMWLKASShiTqIybxZ0U3wGLiUeJ1PKf8ykw="
        allowed_ips = ["10.0.0.0/24"]
        endpoint = "203.0.113.1:51820"
        persistent_keepalive = 25

        # Act
        peer = WireGuardPeer(
            public_key=public_key,
            allowed_ips=allowed_ips,
            endpoint=endpoint,
            persistent_keepalive=persistent_keepalive,
        )

        # Assert
        assert peer.public_key == public_key
        assert peer.allowed_ips == allowed_ips
        assert peer.endpoint == endpoint
        assert peer.persistent_keepalive == persistent_keepalive

    def test_peer_validation_invalid_public_key(self):
        """
        GIVEN an invalid public key
        WHEN creating a WireGuard peer
        THEN it should raise ValidationError
        """
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            WireGuardPeer(
                public_key="invalid_key",
                allowed_ips=["10.0.0.0/24"],
                endpoint="203.0.113.1:51820",
            )

        assert "public_key" in str(exc_info.value)

    def test_peer_validation_invalid_keepalive(self):
        """
        GIVEN an invalid persistent keepalive value
        WHEN creating a WireGuard peer
        THEN it should raise ValidationError
        """
        # Arrange
        public_key = "HIgo9xNzJMWLKASShiTqIybxZ0U3wGLiUeJ1PKf8ykw="

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            WireGuardPeer(
                public_key=public_key,
                allowed_ips=["10.0.0.0/24"],
                endpoint="203.0.113.1:51820",
                persistent_keepalive=-1,  # Invalid keepalive
            )

        assert "persistent_keepalive" in str(exc_info.value)

    def test_peer_optional_endpoint(self):
        """
        GIVEN peer parameters without endpoint
        WHEN creating a WireGuard peer
        THEN it should create peer with None endpoint
        """
        # Arrange
        public_key = "HIgo9xNzJMWLKASShiTqIybxZ0U3wGLiUeJ1PKf8ykw="

        # Act
        peer = WireGuardPeer(
            public_key=public_key,
            allowed_ips=["10.0.0.0/24"],
        )

        # Assert
        assert peer.endpoint is None
        assert peer.persistent_keepalive == 25  # Default value


class TestWireGuardConfig:
    """Test complete WireGuard configuration"""

    def test_config_creation_valid(self):
        """
        GIVEN valid node ID, when generating config,
        THEN should return valid WireGuard config with unique IP
        """
        # Arrange
        node_private_key = "oK56DE9Ue9zK76rAc8pBl6opph+1v36lm7cXXsQKrQM="
        hub_public_key = "HIgo9xNzJMWLKASShiTqIybxZ0U3wGLiUeJ1PKf8ykw="

        interface = WireGuardInterface(
            private_key=node_private_key,
            address="10.0.0.2/24",
            listen_port=51820,
        )

        peers = [
            WireGuardPeer(
                public_key=hub_public_key,
                allowed_ips=["10.0.0.0/24"],
                endpoint="203.0.113.1:51820",
                persistent_keepalive=25,
            )
        ]

        # Act
        config = WireGuardConfig(
            interface=interface,
            peers=peers,
        )

        # Assert
        assert config.interface.private_key == node_private_key
        assert config.interface.address == "10.0.0.2/24"
        assert len(config.peers) == 1
        assert config.peers[0].public_key == hub_public_key
        assert config.peers[0].persistent_keepalive == 25

    def test_config_validation_empty_peers(self):
        """
        GIVEN configuration without peers
        WHEN creating a WireGuard config
        THEN it should raise ValidationError
        """
        # Arrange
        interface = WireGuardInterface(
            private_key="oK56DE9Ue9zK76rAc8pBl6opph+1v36lm7cXXsQKrQM=",
            address="10.0.0.2/24",
            listen_port=51820,
        )

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            WireGuardConfig(
                interface=interface,
                peers=[],  # Empty peers list
            )

        assert "peers" in str(exc_info.value)

    def test_config_to_file_format(self):
        """
        GIVEN a valid WireGuard configuration
        WHEN converting to file format
        THEN it should generate proper WireGuard config file content
        """
        # Arrange
        interface = WireGuardInterface(
            private_key="oK56DE9Ue9zK76rAc8pBl6opph+1v36lm7cXXsQKrQM=",
            address="10.0.0.2/24",
            listen_port=51820,
        )

        peer = WireGuardPeer(
            public_key="HIgo9xNzJMWLKASShiTqIybxZ0U3wGLiUeJ1PKf8ykw=",
            allowed_ips=["10.0.0.0/24"],
            endpoint="203.0.113.1:51820",
            persistent_keepalive=25,
        )

        config = WireGuardConfig(
            interface=interface,
            peers=[peer],
        )

        # Act
        config_text = config.to_config_file()

        # Assert
        assert "[Interface]" in config_text
        assert "PrivateKey = oK56DE9Ue9zK76rAc8pBl6opph+1v36lm7cXXsQKrQM=" in config_text
        assert "Address = 10.0.0.2/24" in config_text
        assert "ListenPort = 51820" in config_text
        assert "[Peer]" in config_text
        assert "PublicKey = HIgo9xNzJMWLKASShiTqIybxZ0U3wGLiUeJ1PKf8ykw=" in config_text
        assert "AllowedIPs = 10.0.0.0/24" in config_text
        assert "Endpoint = 203.0.113.1:51820" in config_text
        assert "PersistentKeepalive = 25" in config_text


class TestIPAddressAllocator:
    """Test IP address allocation logic"""

    def test_allocator_initialization(self):
        """
        GIVEN a network CIDR
        WHEN initializing an IP allocator
        THEN it should set up correct network range
        """
        # Arrange
        network_cidr = "10.0.0.0/24"

        # Act
        allocator = IPAddressAllocator(network_cidr)

        # Assert
        assert allocator.network == IPv4Network(network_cidr)
        assert len(allocator.allocated_ips) == 0

    def test_allocate_ip_first_allocation(self):
        """
        GIVEN an empty allocator
        WHEN allocating first IP
        THEN it should return 10.0.0.2 (skip .0 and .1 for network/gateway)
        """
        # Arrange
        allocator = IPAddressAllocator("10.0.0.0/24")

        # Act
        ip = allocator.allocate_ip()

        # Assert
        assert ip == IPv4Address("10.0.0.2")
        assert len(allocator.allocated_ips) == 1

    def test_allocate_ip_sequential_allocation(self):
        """
        GIVEN an allocator with some IPs allocated
        WHEN allocating new IPs
        THEN it should return sequential unique IPs
        """
        # Arrange
        allocator = IPAddressAllocator("10.0.0.0/24")

        # Act
        ip1 = allocator.allocate_ip()
        ip2 = allocator.allocate_ip()
        ip3 = allocator.allocate_ip()

        # Assert
        assert ip1 == IPv4Address("10.0.0.2")
        assert ip2 == IPv4Address("10.0.0.3")
        assert ip3 == IPv4Address("10.0.0.4")
        assert len(allocator.allocated_ips) == 3

    def test_ip_assignment_no_collisions(self):
        """
        GIVEN 100 nodes, when assigning IPs,
        THEN should have no duplicate addresses
        """
        # Arrange
        allocator = IPAddressAllocator("10.0.0.0/24")
        allocated_ips: Set[IPv4Address] = set()

        # Act
        for _ in range(100):
            ip = allocator.allocate_ip()
            allocated_ips.add(ip)

        # Assert
        assert len(allocated_ips) == 100
        assert len(allocator.allocated_ips) == 100
        # Verify no duplicates
        assert len(allocated_ips) == len(allocator.allocated_ips)

    def test_allocate_ip_exhaustion(self):
        """
        GIVEN a small network (/30 - only 1 usable IP after reservations)
        WHEN allocating more IPs than available
        THEN it should raise ValueError
        """
        # Arrange
        # /30 network has: .0 (network), .1 (gateway reserved), .2 (usable), .3 (broadcast)
        allocator = IPAddressAllocator("10.0.0.0/30")

        # Act
        ip1 = allocator.allocate_ip()

        # Assert first allocation works
        assert ip1 == IPv4Address("10.0.0.2")

        # Assert exhaustion raises error on second allocation
        with pytest.raises(ValueError) as exc_info:
            allocator.allocate_ip()

        assert "No available IP addresses" in str(exc_info.value)

    def test_allocate_specific_ip_success(self):
        """
        GIVEN an allocator
        WHEN allocating a specific available IP
        THEN it should reserve that IP
        """
        # Arrange
        allocator = IPAddressAllocator("10.0.0.0/24")

        # Act
        ip = allocator.allocate_specific_ip("10.0.0.50")

        # Assert
        assert ip == IPv4Address("10.0.0.50")
        assert ip in allocator.allocated_ips

    def test_allocate_specific_ip_already_allocated(self):
        """
        GIVEN an IP already allocated
        WHEN trying to allocate same IP again
        THEN it should raise ValueError
        """
        # Arrange
        allocator = IPAddressAllocator("10.0.0.0/24")
        allocator.allocate_specific_ip("10.0.0.50")

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            allocator.allocate_specific_ip("10.0.0.50")

        assert "already allocated" in str(exc_info.value)

    def test_allocate_specific_ip_out_of_network(self):
        """
        GIVEN an IP outside the network range
        WHEN allocating that IP
        THEN it should raise ValueError
        """
        # Arrange
        allocator = IPAddressAllocator("10.0.0.0/24")

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            allocator.allocate_specific_ip("10.0.1.50")

        assert "not in network" in str(exc_info.value)

    def test_release_ip_success(self):
        """
        GIVEN an allocated IP
        WHEN releasing that IP
        THEN it should become available again
        """
        # Arrange
        allocator = IPAddressAllocator("10.0.0.0/24")
        ip = allocator.allocate_ip()

        # Act
        allocator.release_ip(ip)

        # Assert
        assert ip not in allocator.allocated_ips

    def test_get_available_ips_count(self):
        """
        GIVEN an allocator with some IPs allocated
        WHEN checking available count
        THEN it should return correct number
        """
        # Arrange
        allocator = IPAddressAllocator("10.0.0.0/24")
        allocator.allocate_ip()
        allocator.allocate_ip()

        # Act
        available = allocator.get_available_count()

        # Assert
        # /24 network has 254 usable IPs (256 - 2 for network/broadcast)
        # We reserve .1 for gateway, so 253 usable
        # After allocating 2, should have 251 available
        assert available == 251


class TestNodeConfigGeneration:
    """Test node configuration generation"""

    def test_generate_node_config_hub(self):
        """
        GIVEN a request to generate hub config
        WHEN generating configuration
        THEN it should create valid hub config
        """
        # Arrange
        node_id = "hub-1"
        hub_ip = "10.0.0.1"

        # Act
        config = generate_node_config(
            node_id=node_id,
            node_type="hub",
            hub_public_key=None,
            hub_endpoint=None,
            assigned_ip=hub_ip,
        )

        # Assert
        assert config.interface.address == f"{hub_ip}/24"
        assert config.interface.listen_port == 51820
        assert len(config.interface.private_key) == 44
        # Hub has no peers initially
        assert len(config.peers) == 0

    def test_generate_node_config_spoke(self):
        """
        GIVEN a request to generate spoke config
        WHEN generating configuration
        THEN it should create valid spoke config with hub peer
        """
        # Arrange
        node_id = "spoke-1"
        hub_public_key = "HIgo9xNzJMWLKASShiTqIybxZ0U3wGLiUeJ1PKf8ykw="
        hub_endpoint = "203.0.113.1:51820"
        spoke_ip = "10.0.0.2"

        # Act
        config = generate_node_config(
            node_id=node_id,
            node_type="spoke",
            hub_public_key=hub_public_key,
            hub_endpoint=hub_endpoint,
            assigned_ip=spoke_ip,
        )

        # Assert
        assert config.interface.address == f"{spoke_ip}/24"
        assert config.interface.listen_port == 51820
        assert len(config.peers) == 1
        assert config.peers[0].public_key == hub_public_key
        assert config.peers[0].endpoint == hub_endpoint
        assert config.peers[0].allowed_ips == ["10.0.0.0/24"]
        assert config.peers[0].persistent_keepalive == 25

    def test_config_validation_invalid_ip(self):
        """
        GIVEN invalid IP address, when validating config,
        THEN should raise ValidationError
        """
        # Arrange
        node_id = "test-node"

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            generate_node_config(
                node_id=node_id,
                node_type="spoke",
                hub_public_key="HIgo9xNzJMWLKASShiTqIybxZ0U3wGLiUeJ1PKf8ykw=",
                hub_endpoint="203.0.113.1:51820",
                assigned_ip="999.999.999.999",  # Invalid IP
            )

        assert "Invalid IP" in str(exc_info.value) or "does not appear to be an IPv4" in str(exc_info.value)

    def test_generate_node_config_spoke_missing_hub_info(self):
        """
        GIVEN a spoke node without hub information
        WHEN generating configuration
        THEN it should raise ValueError
        """
        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            generate_node_config(
                node_id="spoke-1",
                node_type="spoke",
                hub_public_key=None,  # Missing
                hub_endpoint=None,  # Missing
                assigned_ip="10.0.0.2",
            )

        assert "Hub information required" in str(exc_info.value)
