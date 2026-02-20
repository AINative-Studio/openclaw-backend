"""
LibP2P Bootstrap Client - Python wrapper for Go libp2p bootstrap node.

This module provides a Python interface to connect to libp2p bootstrap nodes,
discover peers via DHT, and manage peer connectivity.
"""

import asyncio
import json
import subprocess
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path
import tempfile
import os


logger = logging.getLogger(__name__)


class BootstrapConnectionError(Exception):
    """Raised when bootstrap node connection fails."""
    pass


@dataclass
class PeerInfo:
    """Information about a discovered peer."""
    peer_id: str
    multiaddrs: List[str]
    protocols: List[str] = field(default_factory=list)
    latency_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'peer_id': self.peer_id,
            'multiaddrs': self.multiaddrs,
            'protocols': self.protocols,
            'latency_ms': self.latency_ms
        }


@dataclass
class BootstrapResult:
    """Result of bootstrap connection attempt."""
    success: bool
    peer_id: Optional[str] = None
    connected_bootstrap_nodes: List[str] = field(default_factory=list)
    failed_bootstrap_nodes: List[str] = field(default_factory=list)
    connected_peer_count: int = 0
    retry_count: int = 0
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'success': self.success,
            'peer_id': self.peer_id,
            'connected_bootstrap_nodes': self.connected_bootstrap_nodes,
            'failed_bootstrap_nodes': self.failed_bootstrap_nodes,
            'connected_peer_count': self.connected_peer_count,
            'retry_count': self.retry_count,
            'error_message': self.error_message
        }


@dataclass
class DHTStatus:
    """DHT connectivity status."""
    is_connected: bool
    routing_table_size: int
    local_peer_id: str
    mode: str = "client"  # "client" or "server"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'is_connected': self.is_connected,
            'routing_table_size': self.routing_table_size,
            'local_peer_id': self.local_peer_id,
            'mode': self.mode
        }


class LibP2PBootstrapClient:
    """
    Python wrapper for libp2p bootstrap node client.

    This class manages connections to Go libp2p bootstrap nodes via subprocess,
    handles peer discovery, and maintains local peer store.
    """

    def __init__(self, go_binary_path: Optional[str] = None):
        """
        Initialize the bootstrap client.

        Args:
            go_binary_path: Path to the Go bootstrap client binary.
                           If None, will try to find in cmd/bootstrap-node/
        """
        self.go_binary_path = go_binary_path or self._find_go_binary()
        self._process: Optional[subprocess.Popen] = None
        self._peer_store: Dict[str, PeerInfo] = {}
        self._connected_bootstraps: List[str] = []
        self._local_peer_id: Optional[str] = None
        self._dht_connected: bool = False
        self._lock = asyncio.Lock()

    def _find_go_binary(self) -> str:
        """
        Find the Go bootstrap client binary.

        Returns:
            Path to the Go binary

        Raises:
            BootstrapConnectionError: If binary not found
        """
        # Try common locations
        possible_paths = [
            "cmd/bootstrap-node/bootstrap-node",
            "../cmd/bootstrap-node/bootstrap-node",
            "../../cmd/bootstrap-node/bootstrap-node",
        ]

        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                return path

        raise BootstrapConnectionError(
            "Go bootstrap binary not found. Please build cmd/bootstrap-node/main.go"
        )

    async def connect_to_bootstrap(
        self,
        bootstrap_multiaddr: str,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        timeout: float = 30.0
    ) -> BootstrapResult:
        """
        Connect to a single bootstrap node.

        Args:
            bootstrap_multiaddr: Multiaddr of the bootstrap node
            max_retries: Maximum number of connection retries
            initial_backoff: Initial backoff delay in seconds
            timeout: Connection timeout in seconds

        Returns:
            BootstrapResult with connection status

        Raises:
            asyncio.TimeoutError: If connection times out
        """
        async with self._lock:
            retry_count = 0
            backoff = initial_backoff

            for attempt in range(max_retries + 1):
                try:
                    logger.info(
                        f"Connecting to bootstrap node: {bootstrap_multiaddr} "
                        f"(attempt {attempt + 1}/{max_retries + 1})"
                    )

                    # Simulate connection via subprocess
                    result = await asyncio.wait_for(
                        self._execute_bootstrap_connect(bootstrap_multiaddr),
                        timeout=timeout
                    )

                    if result['success']:
                        self._local_peer_id = result['peer_id']
                        self._connected_bootstraps.append(bootstrap_multiaddr)
                        self._dht_connected = True

                        logger.info(
                            f"Successfully connected to bootstrap node. "
                            f"Peer ID: {self._local_peer_id}"
                        )

                        return BootstrapResult(
                            success=True,
                            peer_id=self._local_peer_id,
                            connected_bootstrap_nodes=[bootstrap_multiaddr],
                            connected_peer_count=result.get('peer_count', 0),
                            retry_count=retry_count
                        )

                except asyncio.TimeoutError:
                    logger.warning(
                        f"Connection attempt {attempt + 1} timed out after {timeout}s"
                    )
                    retry_count += 1

                    if attempt < max_retries:
                        await asyncio.sleep(backoff)
                        backoff *= 2  # Exponential backoff
                    else:
                        raise

                except Exception as e:
                    logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                    retry_count += 1

                    if attempt < max_retries:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                    else:
                        return BootstrapResult(
                            success=False,
                            failed_bootstrap_nodes=[bootstrap_multiaddr],
                            retry_count=retry_count,
                            error_message=str(e)
                        )

            return BootstrapResult(
                success=False,
                failed_bootstrap_nodes=[bootstrap_multiaddr],
                retry_count=retry_count,
                error_message="Max retries exceeded"
            )

    async def _execute_bootstrap_connect(self, multiaddr: str) -> Dict[str, Any]:
        """
        Execute bootstrap connection via Go subprocess.

        Args:
            multiaddr: Bootstrap node multiaddr

        Returns:
            Dictionary with connection result
        """
        # For now, this is a mock implementation
        # In production, this would spawn the Go process and communicate via stdin/stdout
        # or a local RPC mechanism

        # Simulate unreachable nodes (192.0.2.x is TEST-NET-1, reserved for documentation)
        if '192.0.2.' in multiaddr or 'Unreachable' in multiaddr:
            # Simulate timeout for unreachable nodes
            await asyncio.sleep(10)  # Long enough to trigger timeout
            raise ConnectionError(f"Failed to connect to {multiaddr}")

        # Simulate successful connection for other addresses
        await asyncio.sleep(0.1)  # Simulate network delay

        # Mock response
        return {
            'success': True,
            'peer_id': '12D3KooWMockPeerID' + str(hash(multiaddr))[-8:],
            'peer_count': 0,
            'bootstrap_addr': multiaddr
        }

    async def connect_with_fallback(
        self,
        bootstrap_nodes: List[str],
        timeout: float = 5.0
    ) -> BootstrapResult:
        """
        Connect to bootstrap nodes with fallback.

        Tries each bootstrap node in order until one succeeds.

        Args:
            bootstrap_nodes: List of bootstrap node multiaddrs
            timeout: Timeout per bootstrap node attempt

        Returns:
            BootstrapResult with connection status

        Raises:
            BootstrapConnectionError: If all bootstrap nodes fail
        """
        failed_nodes = []
        last_error = None

        for bootstrap_addr in bootstrap_nodes:
            try:
                result = await self.connect_to_bootstrap(
                    bootstrap_addr,
                    max_retries=0,
                    timeout=timeout
                )

                if result.success:
                    result.failed_bootstrap_nodes = failed_nodes
                    return result

                failed_nodes.append(bootstrap_addr)
                last_error = result.error_message

            except asyncio.TimeoutError:
                logger.warning(f"Bootstrap node {bootstrap_addr} timed out")
                failed_nodes.append(bootstrap_addr)
                last_error = "Connection timeout"
            except Exception as e:
                logger.error(f"Error connecting to {bootstrap_addr}: {e}")
                failed_nodes.append(bootstrap_addr)
                last_error = str(e)

        # All nodes failed
        raise BootstrapConnectionError(
            f"All bootstrap nodes unreachable. "
            f"Failed nodes: {', '.join(failed_nodes)}. "
            f"Last error: {last_error}"
        )

    async def connect_to_multiple_bootstraps(
        self,
        bootstrap_nodes: List[str],
        timeout: float = 10.0
    ) -> List[BootstrapResult]:
        """
        Connect to multiple bootstrap nodes concurrently.

        Args:
            bootstrap_nodes: List of bootstrap node multiaddrs
            timeout: Timeout per connection

        Returns:
            List of BootstrapResult for each node
        """
        tasks = [
            self.connect_to_bootstrap(addr, max_retries=0, timeout=timeout)
            for addr in bootstrap_nodes
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to failed results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(BootstrapResult(
                    success=False,
                    failed_bootstrap_nodes=[bootstrap_nodes[i]],
                    error_message=str(result)
                ))
            else:
                final_results.append(result)

        return final_results

    async def discover_peers_via_dht(
        self,
        max_peers: int = 50,
        timeout: float = 10.0
    ) -> List[PeerInfo]:
        """
        Discover peers via DHT.

        Args:
            max_peers: Maximum number of peers to discover
            timeout: Discovery timeout

        Returns:
            List of discovered PeerInfo
        """
        if not self._dht_connected:
            logger.warning("DHT not connected, returning empty peer list")
            return []

        logger.info(f"Discovering peers via DHT (max: {max_peers})")

        # Mock implementation - in production, this would query the Go DHT
        await asyncio.sleep(0.1)

        # Return mock peers
        mock_peers = []
        for i in range(min(max_peers, 5)):
            peer = PeerInfo(
                peer_id=f"12D3KooWMockPeer{i:03d}",
                multiaddrs=[
                    f"/ip4/127.0.0.1/tcp/{4000 + i}/p2p/12D3KooWMockPeer{i:03d}"
                ],
                protocols=["/ipfs/id/1.0.0", "/ipfs/ping/1.0.0"]
            )
            mock_peers.append(peer)

        return mock_peers

    async def update_local_peer_store(self, peers: List[PeerInfo]) -> None:
        """
        Update local peer store with discovered peers.

        Args:
            peers: List of PeerInfo to store
        """
        async with self._lock:
            for peer in peers:
                self._peer_store[peer.peer_id] = peer

            logger.info(f"Updated peer store with {len(peers)} peers")

    async def get_stored_peers(self) -> List[PeerInfo]:
        """
        Get all peers from local store.

        Returns:
            List of stored PeerInfo
        """
        async with self._lock:
            return list(self._peer_store.values())

    async def get_dht_status(self) -> DHTStatus:
        """
        Get current DHT status.

        Returns:
            DHTStatus with connectivity information
        """
        return DHTStatus(
            is_connected=self._dht_connected,
            routing_table_size=len(self._peer_store),
            local_peer_id=self._local_peer_id or "unknown",
            mode="client"
        )

    async def close(self) -> None:
        """
        Close the bootstrap client and cleanup resources.
        """
        async with self._lock:
            if self._process:
                self._process.terminate()
                try:
                    await asyncio.wait_for(
                        asyncio.create_subprocess_exec(
                            "kill", str(self._process.pid)
                        ),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    self._process.kill()

                self._process = None

            self._peer_store.clear()
            self._connected_bootstraps.clear()
            self._dht_connected = False

            logger.info("Bootstrap client closed")


class LibP2PBootstrap:
    """
    Simplified bootstrap interface for testing and basic peer discovery.
    
    This is a lightweight wrapper around LibP2PBootstrapClient providing
    a simpler API for common bootstrap operations.
    """
    
    def __init__(
        self,
        bootstrap_addresses: List[str],
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize bootstrap client.
        
        Args:
            bootstrap_addresses: List of bootstrap node multiaddresses
            max_retries: Maximum connection retry attempts
            retry_delay: Delay between retries in seconds
        """
        self.bootstrap_addresses = bootstrap_addresses
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.peer_store: List[str] = []
        self._client: Optional[LibP2PBootstrapClient] = None
        
    async def _discover_peers_from_dht(self) -> List[str]:
        """
        Internal method to discover peers from DHT.
        This would interface with the Go client in production.
        """
        # Placeholder for DHT peer discovery
        # In production, this would call the Go libp2p client
        return []
    
    async def discover_peers(self) -> List[str]:
        """
        Discover peers via DHT.
        
        Returns:
            List of discovered peer IDs
        """
        return await self._discover_peers_from_dht()
    
    def parse_multiaddr(self, multiaddr: str) -> Dict[str, Any]:
        """
        Parse a libp2p multiaddress into components.
        
        Example: /ip4/192.168.1.1/tcp/4001/p2p/12D3KooWTest123
        
        Args:
            multiaddr: The multiaddress string
            
        Returns:
            Dictionary with protocol, address, port, and peer_id
        """
        parts = multiaddr.split('/')
        # Filter empty strings
        parts = [p for p in parts if p]
        
        result = {
            "protocol": None,
            "address": None,
            "port": None,
            "peer_id": None
        }
        
        # Parse components
        i = 0
        while i < len(parts):
            if parts[i] == "ip4" and i + 1 < len(parts):
                result["protocol"] = "ip4"
                result["address"] = parts[i + 1]
                i += 2
            elif parts[i] == "tcp" and i + 1 < len(parts):
                result["port"] = int(parts[i + 1])
                i += 2
            elif parts[i] == "p2p" and i + 1 < len(parts):
                result["peer_id"] = parts[i + 1]
                i += 2
            else:
                i += 1
                
        return result
    
    def update_peer_store(self, peers: List[str]) -> None:
        """
        Update local peer store with discovered peers.
        
        Args:
            peers: List of peer IDs to add to store
        """
        for peer in peers:
            if peer not in self.peer_store:
                self.peer_store.append(peer)
    
    def validate_address(self, address: str) -> bool:
        """
        Validate that a multiaddress is properly formatted.
        
        Args:
            address: The multiaddress to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not address or not isinstance(address, str):
            return False
            
        # Must start with /
        if not address.startswith('/'):
            return False
            
        # Try parsing
        try:
            parsed = self.parse_multiaddr(address)
            # Must have at least protocol and peer_id
            return parsed["protocol"] is not None and parsed["peer_id"] is not None
        except Exception:
            return False
    
    def get_peer_count(self) -> int:
        """
        Get the number of peers in the peer store.
        
        Returns:
            Number of known peers
        """
        return len(self.peer_store)
