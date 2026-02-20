"""
WireGuard Peer Provisioning Service - Usage Example

This example demonstrates how to use the WireGuard provisioning service
to provision new peers in the OpenCLAW P2P swarm.

Part of E1-S3: WireGuard Peer Provisioning Service
"""

from backend.services.wireguard_provisioning_service import (
    WireGuardProvisioningService,
    DuplicatePeerError,
    IPPoolExhaustedError
)


def main():
    """
    Example usage of WireGuard provisioning service
    """

    # Initialize provisioning service
    service = WireGuardProvisioningService(
        ip_pool_network="10.0.0.0/24",
        hub_public_key="YOUR_HUB_WIREGUARD_PUBLIC_KEY_HERE",
        hub_endpoint="hub.example.com:51820",
        hub_ip="10.0.0.1",
        config_path="/etc/wireguard/wg0.conf",
        enable_dbos=False  # Set to True when E4-S1 is ready
    )

    # Provision a new peer
    try:
        config = service.provision_peer(
            node_id="swarm-node-001",
            public_key="peer_libp2p_public_key",
            wireguard_public_key="jKlMnOpQrStUvWxYzAbCdEfGhIjKlMnO=",
            capabilities={
                "gpu_count": 1,
                "gpu_memory_mb": 16384,
                "cpu_cores": 8,
                "models": ["llama-2-7b", "gpt-3.5-turbo"]
            },
            version="1.0.0",
            metadata={
                "location": "us-west-2",
                "owner": "team-ai"
            }
        )

        print(f"Peer provisioned successfully!")
        print(f"Node ID: {config['node_id']}")
        print(f"Assigned IP: {config['assigned_ip']}")
        print(f"Hub Endpoint: {config['hub_endpoint']}")
        print(f"Configuration:")
        print(f"  - Hub Public Key: {config['hub_public_key']}")
        print(f"  - Allowed IPs: {config['allowed_ips']}")
        print(f"  - DNS Servers: {config['dns_servers']}")
        print(f"  - Persistent Keepalive: {config['persistent_keepalive']}s")

    except DuplicatePeerError as e:
        print(f"Error: Peer already provisioned - {e}")
        print(f"Existing config: {e.existing_config}")

    except IPPoolExhaustedError as e:
        print(f"Error: IP pool exhausted - {e}")
        print(f"Pool range: {e.pool_range}")
        print(f"Allocated: {e.allocated_count} addresses")

    except Exception as e:
        print(f"Error provisioning peer: {e}")

    # Get pool statistics
    stats = service.get_pool_stats()
    print(f"\nIP Pool Statistics:")
    print(f"  Total addresses: {stats['total_addresses']}")
    print(f"  Reserved: {stats['reserved_addresses']}")
    print(f"  Allocated: {stats['allocated_addresses']}")
    print(f"  Available: {stats['available_addresses']}")
    print(f"  Utilization: {stats['utilization_percent']}%")

    # List all provisioned peers
    peers = service.list_provisioned_peers()
    print(f"\nProvisioned Peers: {len(peers)}")
    for peer_id, peer_config in peers.items():
        print(f"  - {peer_id}: {peer_config['assigned_ip']}")

    # Get specific peer config
    peer_config = service.get_peer_config("swarm-node-001")
    if peer_config:
        print(f"\nPeer 'swarm-node-001' configuration:")
        print(f"  IP: {peer_config['assigned_ip']}")
        print(f"  Provisioned: {peer_config['provisioned_at']}")


def fastapi_integration_example():
    """
    Example of integrating with FastAPI
    """
    from fastapi import FastAPI
    from backend.api.v1.endpoints.wireguard_provisioning import router

    # Create FastAPI app
    app = FastAPI(
        title="OpenCLAW Swarm API",
        version="1.0.0",
        description="WireGuard peer provisioning for OpenCLAW P2P swarm"
    )

    # Include WireGuard provisioning router
    app.include_router(router, prefix="/api/v1")

    # Run with: uvicorn script:app --reload
    return app


def client_provisioning_example():
    """
    Example of client requesting provisioning via HTTP
    """
    import httpx

    # Client makes HTTP request to provision
    response = httpx.post(
        "http://localhost:8000/api/v1/wireguard/provision",
        json={
            "node_id": "client-node-001",
            "public_key": "client_libp2p_key",
            "wireguard_public_key": "client_wg_key_base64",
            "capabilities": {
                "gpu_count": 0,
                "cpu_cores": 4,
                "memory_mb": 8192,
                "models": []
            },
            "version": "1.0.0"
        }
    )

    if response.status_code == 200:
        data = response.json()
        config = data["config"]

        # Save configuration to file
        wireguard_config = f"""
[Interface]
PrivateKey = YOUR_PRIVATE_KEY_HERE
Address = {config['assigned_ip']}/{config['subnet_mask']}
DNS = {', '.join(config['dns_servers'])}

[Peer]
PublicKey = {config['hub_public_key']}
Endpoint = {config['hub_endpoint']}
AllowedIPs = {config['allowed_ips']}
PersistentKeepalive = {config['persistent_keepalive']}
"""

        with open("/etc/wireguard/wg0.conf", "w") as f:
            f.write(wireguard_config)

        print("WireGuard configuration saved!")
        print("Start connection with: sudo wg-quick up wg0")

    elif response.status_code == 409:
        print("Error: Peer already provisioned")

    elif response.status_code == 503:
        print("Error: IP pool exhausted")

    else:
        print(f"Error: {response.json()['detail']}")


if __name__ == "__main__":
    main()
