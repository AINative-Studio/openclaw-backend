"""
WireGuard Hub Configuration Manager

Manages peer configurations dynamically for WireGuard hub node.
Provides zero-downtime configuration reload using 'wg syncconf'.

Features:
- Add/remove peers without connection loss
- Safe configuration reload mechanism
- Peer connectivity verification
- Configuration change logging

Story: E1-S4 - Hub WireGuard Configuration Management
Story Points: 3
Coverage Target: >= 80%
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class WireGuardError(Exception):
    """Base exception for WireGuard operations."""
    pass


class ConfigReloadError(WireGuardError):
    """Raised when WireGuard configuration reload fails."""
    pass


class PeerNotFoundError(WireGuardError):
    """Raised when attempting to operate on nonexistent peer."""
    pass


class ConnectivityCheckError(WireGuardError):
    """Raised when peer connectivity check fails."""
    pass


@dataclass
class PeerConfig:
    """
    WireGuard peer configuration.

    Attributes:
        public_key: Peer's WireGuard public key (base64)
        allowed_ips: List of IP addresses/subnets allowed for this peer
        endpoint: Optional endpoint address (host:port)
        persistent_keepalive: Keepalive interval in seconds
    """
    public_key: str
    allowed_ips: List[str]
    endpoint: Optional[str] = None
    persistent_keepalive: int = 25


class WireGuardHubManager:
    """
    Manages WireGuard hub configuration with zero-downtime updates.

    Handles:
    - Dynamic peer addition/removal
    - Configuration file management
    - Zero-downtime reload using 'wg syncconf'
    - Peer connectivity verification
    """

    def __init__(
        self,
        interface_name: str,
        config_path: str,
        listen_port: int,
        private_key: str,
        address: str,
    ):
        """
        Initialize WireGuard hub manager.

        Args:
            interface_name: WireGuard interface name (e.g., "wg0")
            config_path: Path to WireGuard configuration file
            listen_port: UDP port to listen on
            private_key: Hub's WireGuard private key (base64)
            address: Hub's IP address and subnet (e.g., "10.0.0.1/24")
        """
        self.interface_name = interface_name
        self.config_path = config_path
        self.listen_port = listen_port
        self.private_key = private_key
        self.address = address

        # In-memory peer registry
        self.peers: Dict[str, PeerConfig] = {}

        # Lock for thread-safe configuration updates
        self._config_lock = asyncio.Lock()

        logger.info(
            f"Initialized WireGuard hub manager for interface {interface_name} "
            f"at {address}"
        )

    async def add_peer(self, peer_id: str, peer_config: PeerConfig) -> bool:
        """
        Add peer to WireGuard hub configuration.

        Updates configuration file and reloads WireGuard without connection loss.

        Args:
            peer_id: Unique identifier for the peer
            peer_config: Peer's WireGuard configuration

        Returns:
            True if peer was added successfully

        Raises:
            ConfigReloadError: If configuration reload fails
        """
        async with self._config_lock:
            # Update in-memory registry
            self.peers[peer_id] = peer_config

            logger.info(
                f"Adding peer {peer_id} with public key {peer_config.public_key[:16]}..."
            )

            # Write updated configuration to file
            await self._write_config_file()

            # Reload WireGuard configuration without downtime
            await self._reload_config()

            logger.info(
                f"Added peer {peer_id} to hub configuration. "
                f"Total peers: {len(self.peers)}"
            )

            return True

    async def remove_peer(self, peer_id: str) -> bool:
        """
        Remove peer from WireGuard hub configuration.

        Updates configuration file and reloads to drop connections.

        Args:
            peer_id: Unique identifier for the peer

        Returns:
            True if peer was removed successfully

        Raises:
            PeerNotFoundError: If peer does not exist
            ConfigReloadError: If configuration reload fails
        """
        async with self._config_lock:
            # Check if peer exists
            if peer_id not in self.peers:
                raise PeerNotFoundError(f"Peer {peer_id} not found in configuration")

            # Remove from in-memory registry
            peer_config = self.peers.pop(peer_id)

            logger.info(
                f"Removing peer {peer_id} with public key {peer_config.public_key[:16]}..."
            )

            # Write updated configuration to file
            await self._write_config_file()

            # Reload WireGuard configuration
            await self._reload_config()

            logger.info(
                f"Removed peer {peer_id} from hub configuration. "
                f"Remaining peers: {len(self.peers)}"
            )

            return True

    async def verify_peer_connectivity(
        self, peer_id: str, timeout: int = 5
    ) -> bool:
        """
        Verify connectivity to peer by pinging its allowed IP.

        Args:
            peer_id: Unique identifier for the peer
            timeout: Ping timeout in seconds

        Returns:
            True if peer is reachable, False otherwise

        Raises:
            PeerNotFoundError: If peer does not exist
        """
        if peer_id not in self.peers:
            raise PeerNotFoundError(f"Peer {peer_id} not found in configuration")

        peer_config = self.peers[peer_id]

        # Extract first IP from allowed_ips
        # Format: "10.0.0.2/32" -> "10.0.0.2"
        target_ip = peer_config.allowed_ips[0].split('/')[0]

        logger.debug(f"Verifying connectivity to peer {peer_id} at {target_ip}")

        # Ping peer
        is_reachable = await self._ping_peer(target_ip, timeout)

        if is_reachable:
            logger.info(f"Peer {peer_id} is reachable at {target_ip}")
        else:
            logger.warning(
                f"Peer {peer_id} is not reachable at {target_ip} "
                f"(timeout: {timeout}s)"
            )

        return is_reachable

    async def get_peer_status(self, peer_id: str) -> Optional[PeerConfig]:
        """
        Retrieve peer configuration.

        Args:
            peer_id: Unique identifier for the peer

        Returns:
            PeerConfig if peer exists, None otherwise
        """
        return self.peers.get(peer_id)

    async def list_peers(self) -> List[str]:
        """
        List all peer IDs.

        Returns:
            List of peer IDs
        """
        return list(self.peers.keys())

    async def _write_config_file(self) -> None:
        """
        Write current configuration to WireGuard config file.

        Generates configuration in WireGuard format:
        [Interface]
        PrivateKey = ...
        Address = ...
        ListenPort = ...

        [Peer]
        PublicKey = ...
        AllowedIPs = ...
        ...
        """
        config_lines = [
            "[Interface]",
            f"PrivateKey = {self.private_key}",
            f"Address = {self.address}",
            f"ListenPort = {self.listen_port}",
            "",
        ]

        # Add peer sections
        for peer_id, peer_config in self.peers.items():
            config_lines.append("[Peer]")
            config_lines.append(f"# Peer ID: {peer_id}")
            config_lines.append(f"PublicKey = {peer_config.public_key}")
            config_lines.append(f"AllowedIPs = {', '.join(peer_config.allowed_ips)}")

            if peer_config.endpoint:
                config_lines.append(f"Endpoint = {peer_config.endpoint}")

            if peer_config.persistent_keepalive:
                config_lines.append(
                    f"PersistentKeepalive = {peer_config.persistent_keepalive}"
                )

            config_lines.append("")

        # Write to file
        config_content = "\n".join(config_lines)
        Path(self.config_path).write_text(config_content)

        logger.debug(f"Wrote configuration file to {self.config_path}")

    async def _reload_config(self) -> None:
        """
        Reload WireGuard configuration using 'wg syncconf'.

        Uses 'wg syncconf' instead of 'wg-quick' for zero-downtime reload.
        Existing connections are preserved.

        Raises:
            ConfigReloadError: If reload fails
        """
        logger.debug(f"Reloading WireGuard configuration for {self.interface_name}")

        # Use 'wg syncconf' for zero-downtime reload
        returncode, stdout, stderr = await self._execute_wg_command(
            "syncconf", self.interface_name, self.config_path
        )

        if returncode != 0:
            error_msg = (
                f"Failed to reload WireGuard configuration: {stderr}\n"
                f"Return code: {returncode}"
            )
            logger.error(error_msg)
            raise ConfigReloadError(error_msg)

        logger.debug(f"Successfully reloaded configuration for {self.interface_name}")

    async def _execute_wg_command(self, *args: str) -> tuple:
        """
        Execute WireGuard command.

        Args:
            *args: Command arguments

        Returns:
            Tuple of (returncode, stdout, stderr)
        """
        cmd = ["wg", *args]

        logger.debug(f"Executing command: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        return (
            process.returncode,
            stdout.decode().strip(),
            stderr.decode().strip(),
        )

    async def _ping_peer(self, ip_address: str, timeout: int = 5) -> bool:
        """
        Ping peer to verify connectivity.

        Args:
            ip_address: Target IP address
            timeout: Ping timeout in seconds

        Returns:
            True if ping succeeds, False otherwise
        """
        try:
            # Use platform-specific ping command
            # macOS/Linux: ping -c 1 -W <timeout>
            process = await asyncio.create_subprocess_exec(
                "ping",
                "-c", "1",
                "-W", str(timeout),
                ip_address,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await asyncio.wait_for(process.communicate(), timeout=timeout + 1)

            return process.returncode == 0

        except asyncio.TimeoutError:
            logger.debug(f"Ping to {ip_address} timed out")
            return False
        except Exception as e:
            logger.warning(f"Error pinging {ip_address}: {e}")
            return False

    async def shutdown(self) -> None:
        """
        Cleanup resources on shutdown.
        """
        logger.info(f"Shutting down WireGuard hub manager for {self.interface_name}")
        # Any cleanup operations can be added here
