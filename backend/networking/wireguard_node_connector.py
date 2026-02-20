"""
WireGuard Node Connection Initialization

Implements E1-S5: Node WireGuard Connection Initialization
Provides automatic connection to WireGuard hub with health monitoring,
retry logic with exponential backoff, and DBOS registration.

Story Points: 3
Dependencies: E1-S2 (WireGuard Keypair Generation), E1-S3 (Peer Provisioning)

Security Considerations:
- Private keys stored securely (file permissions 0600)
- Connection verification before registration
- Secure cleanup on disconnect

Performance:
- Exponential backoff prevents aggressive retry storms
- Health checks use lightweight ping operations
- Async operations prevent blocking
"""

import asyncio
import subprocess
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from pathlib import Path
import logging


logger = logging.getLogger(__name__)


class WireGuardNodeConnectorError(Exception):
    """Base exception for WireGuard node connector errors"""
    pass


class ConfigValidationError(WireGuardNodeConnectorError):
    """Raised when configuration is invalid"""
    pass


class ConnectionError(WireGuardNodeConnectorError):
    """Raised when connection to hub fails"""
    pass


class ConnectionTimeout(WireGuardNodeConnectorError):
    """Raised when connection attempt times out"""
    pass


class WireGuardNodeConnector:
    """
    WireGuard Node Connection Manager

    Manages WireGuard interface lifecycle, connection to hub,
    health monitoring, and DBOS registration.

    Attributes:
        config: WireGuard configuration dictionary
        dbos_client: DBOS client for node registration
        max_retries: Maximum connection retry attempts
        initial_backoff: Initial backoff delay in seconds
        max_backoff: Maximum backoff delay in seconds
        connection_timeout: Connection timeout in seconds
    """

    def __init__(
        self,
        config: Dict[str, Any],
        dbos_client: Optional[Any] = None,
        max_retries: int = 5,
        initial_backoff: float = 2.0,
        max_backoff: float = 60.0,
        connection_timeout: float = 30.0
    ):
        """
        Initialize WireGuard node connector

        Args:
            config: WireGuard configuration with interface and hub details
            dbos_client: Optional DBOS client for registration
            max_retries: Maximum retry attempts on connection failure
            initial_backoff: Initial exponential backoff delay
            max_backoff: Maximum backoff delay cap
            connection_timeout: Connection timeout in seconds

        Raises:
            ConfigValidationError: If configuration is invalid
        """
        self.config = config
        self.dbos_client = dbos_client
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.connection_timeout = connection_timeout

        # Connection state
        self._connected = False
        self._connection_time: Optional[datetime] = None
        self._node_id: Optional[str] = None

        # Validate configuration
        self._validate_config()

        logger.info(
            f"Initialized WireGuardNodeConnector for interface {config.get('interface_name')}"
        )

    def _validate_config(self) -> None:
        """
        Validate WireGuard configuration

        Raises:
            ConfigValidationError: If required fields are missing or invalid
        """
        required_fields = ['interface_name', 'private_key', 'address', 'hub']
        missing_fields = [field for field in required_fields if field not in self.config]

        if missing_fields:
            raise ConfigValidationError(
                f"Missing required configuration fields: {', '.join(missing_fields)}"
            )

        # Validate hub configuration
        hub_config = self.config.get('hub', {})
        required_hub_fields = ['public_key', 'endpoint', 'allowed_ips']
        missing_hub_fields = [
            field for field in required_hub_fields if field not in hub_config
        ]

        if missing_hub_fields:
            raise ConfigValidationError(
                f"Missing required hub configuration fields: {', '.join(missing_hub_fields)}"
            )

        logger.debug("Configuration validation passed")

    async def connect_to_hub(self) -> Dict[str, Any]:
        """
        Connect to WireGuard hub with retry logic

        Implements exponential backoff retry strategy:
        1. Apply WireGuard configuration
        2. Verify connectivity to hub
        3. Register with DBOS

        Returns:
            Dictionary with connection status and metadata

        Raises:
            ConnectionError: If max retries exceeded
            ConnectionTimeout: If connection times out
        """
        logger.info(f"Connecting to WireGuard hub at {self.config['hub']['endpoint']}")

        attempt = 0
        last_error = None

        while attempt <= self.max_retries:
            try:
                # Apply WireGuard configuration
                await self._apply_wireguard_config()

                # Verify connectivity with timeout
                connected = await asyncio.wait_for(
                    self._verify_connectivity(),
                    timeout=self.connection_timeout
                )

                if connected:
                    self._connected = True
                    self._connection_time = datetime.now(timezone.utc)

                    # Register with DBOS
                    if self.dbos_client:
                        registration = await self._register_with_dbos()
                        self._node_id = registration.get('node_id')

                    logger.info(
                        f"Successfully connected to hub (attempt {attempt + 1}/{self.max_retries + 1})"
                    )

                    return {
                        "success": True,
                        "interface": self.config['interface_name'],
                        "connected_at": self._connection_time.isoformat(),
                        "node_id": self._node_id,
                        "attempts": attempt + 1
                    }

                # Connection verification failed
                last_error = "Connectivity verification failed"

            except asyncio.TimeoutError:
                last_error = f"Connection timeout after {self.connection_timeout}s"
                logger.warning(f"Connection attempt {attempt + 1} timed out")
                raise ConnectionTimeout(last_error)

            except Exception as e:
                last_error = str(e)
                logger.error(f"Connection attempt {attempt + 1} failed: {e}")

            # Retry with exponential backoff
            if attempt < self.max_retries:
                backoff = self._calculate_backoff(attempt)
                logger.info(f"Retrying in {backoff}s (attempt {attempt + 2}/{self.max_retries + 1})")
                await asyncio.sleep(backoff)

            attempt += 1

        # Max retries exceeded
        error_msg = f"Max retries exceeded ({self.max_retries + 1} attempts). Last error: {last_error}"
        logger.error(error_msg)
        raise ConnectionError(error_msg)

    async def _apply_wireguard_config(self) -> None:
        """
        Apply WireGuard configuration to create and configure interface

        Steps:
        1. Create WireGuard interface
        2. Set private key
        3. Configure peer (hub)
        4. Set IP address
        5. Bring interface up

        Raises:
            ConnectionError: If configuration application fails
        """
        interface = self.config['interface_name']

        try:
            # Create WireGuard interface
            logger.debug(f"Creating WireGuard interface {interface}")
            subprocess.run(
                ['ip', 'link', 'add', 'dev', interface, 'type', 'wireguard'],
                check=True,
                capture_output=True,
                text=True
            )

            # Set private key
            logger.debug(f"Setting private key for {interface}")
            subprocess.run(
                ['wg', 'set', interface, 'private-key', '/dev/stdin'],
                input=self.config['private_key'],
                check=True,
                capture_output=True,
                text=True
            )

            # Configure peer (hub)
            hub = self.config['hub']
            logger.debug(f"Configuring peer for {interface}")
            cmd = [
                'wg', 'set', interface,
                'peer', hub['public_key'],
                'endpoint', hub['endpoint'],
                'allowed-ips', hub['allowed_ips']
            ]

            if 'persistent_keepalive' in hub:
                cmd.extend(['persistent-keepalive', str(hub['persistent_keepalive'])])

            subprocess.run(cmd, check=True, capture_output=True, text=True)

            # Set IP address
            logger.debug(f"Setting IP address {self.config['address']} for {interface}")
            subprocess.run(
                ['ip', 'address', 'add', self.config['address'], 'dev', interface],
                check=True,
                capture_output=True,
                text=True
            )

            # Bring interface up
            logger.debug(f"Bringing interface {interface} up")
            subprocess.run(
                ['ip', 'link', 'set', interface, 'up'],
                check=True,
                capture_output=True,
                text=True
            )

            logger.info(f"WireGuard configuration applied successfully for {interface}")

        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to apply WireGuard configuration: {e.stderr}"
            logger.error(error_msg)
            raise ConnectionError(error_msg)

    async def _verify_connectivity(self) -> bool:
        """
        Verify connectivity to WireGuard hub

        Returns:
            True if hub is reachable, False otherwise
        """
        # Extract hub IP from endpoint
        hub_endpoint = self.config['hub']['endpoint']
        hub_ip = hub_endpoint.split(':')[0]

        logger.debug(f"Verifying connectivity to hub at {hub_ip}")

        # Use helper function to ping hub
        return await ping_host(hub_ip, count=3, timeout=5)

    async def check_health(self) -> Dict[str, Any]:
        """
        Check connection health status

        Performs:
        1. Connectivity check (ping to hub)
        2. WireGuard handshake age check
        3. Uptime calculation

        Returns:
            Dictionary with health status and metrics
        """
        if not self._connected:
            return {
                "status": "disconnected",
                "connected": False
            }

        # Check connectivity
        hub_endpoint = self.config['hub']['endpoint']
        hub_ip = hub_endpoint.split(':')[0]
        can_ping = await ping_host(hub_ip, count=1, timeout=2)

        # Get WireGuard handshake information
        interface = self.config['interface_name']
        try:
            result = subprocess.run(
                ['wg', 'show', interface],
                check=True,
                capture_output=True,
                text=True
            )

            # Parse handshake age from output
            handshake_age = self._parse_handshake_age(result.stdout)

        except subprocess.CalledProcessError:
            handshake_age = None

        # Calculate uptime
        uptime = None
        if self._connection_time:
            uptime = (datetime.now(timezone.utc) - self._connection_time).total_seconds()

        # Determine health status
        status = "healthy"
        if not can_ping:
            status = "unhealthy"
        elif handshake_age and handshake_age > 180:  # > 3 minutes
            status = "degraded"

        return {
            "status": status,
            "connected": True,
            "can_ping_hub": can_ping,
            "handshake_age": handshake_age,
            "uptime_seconds": uptime,
            "node_id": self._node_id
        }

    def _parse_handshake_age(self, wg_output: str) -> Optional[int]:
        """
        Parse handshake age from wg show output

        Args:
            wg_output: Output from 'wg show' command

        Returns:
            Handshake age in seconds, or None if not found
        """
        # Look for "latest handshake: X seconds/minutes ago"
        pattern = r'latest handshake:\s+(\d+)\s+(second|minute)s?\s+ago'
        match = re.search(pattern, wg_output)

        if match:
            value = int(match.group(1))
            unit = match.group(2)

            if unit == 'minute':
                return value * 60
            return value

        return None

    async def disconnect(self) -> None:
        """
        Disconnect from WireGuard hub and cleanup interface

        Steps:
        1. Bring interface down
        2. Delete interface
        3. Reset connection state
        """
        if not self._connected:
            logger.warning("Not connected, nothing to disconnect")
            return

        interface = self.config['interface_name']

        try:
            # Bring interface down
            logger.debug(f"Bringing interface {interface} down")
            subprocess.run(
                ['ip', 'link', 'set', interface, 'down'],
                check=True,
                capture_output=True,
                text=True
            )

            # Delete interface
            logger.debug(f"Deleting interface {interface}")
            subprocess.run(
                ['ip', 'link', 'delete', interface],
                check=True,
                capture_output=True,
                text=True
            )

            logger.info(f"Disconnected from WireGuard hub and cleaned up {interface}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Error during disconnect: {e.stderr}")

        finally:
            # Reset state
            self._connected = False
            self._connection_time = None

    async def _register_with_dbos(self) -> Dict[str, Any]:
        """
        Register node with DBOS control plane

        Returns:
            Registration result with node_id
        """
        if not self.dbos_client:
            logger.warning("No DBOS client provided, skipping registration")
            return {}

        logger.info("Registering node with DBOS")

        registration_data = {
            "wireguard_address": self.config['address'],
            "wireguard_public_key": self.config.get('public_key'),
            "interface_name": self.config['interface_name'],
            "hub_endpoint": self.config['hub']['endpoint'],
            "registered_at": datetime.now(timezone.utc).isoformat()
        }

        result = await self.dbos_client.register_node(**registration_data)
        logger.info(f"Node registered with DBOS: {result.get('node_id')}")

        return result

    def _calculate_backoff(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay

        Formula: min(initial_backoff * 2^attempt, max_backoff)

        Args:
            attempt: Current retry attempt number (0-indexed)

        Returns:
            Backoff delay in seconds
        """
        backoff = self.initial_backoff * (2 ** attempt)
        return min(backoff, self.max_backoff)


async def ping_host(host: str, count: int = 3, timeout: int = 5) -> bool:
    """
    Ping a host to verify connectivity

    Args:
        host: Hostname or IP address to ping
        count: Number of ping packets to send
        timeout: Timeout in seconds

    Returns:
        True if host is reachable, False otherwise
    """
    try:
        result = subprocess.run(
            ['ping', '-c', str(count), '-W', str(timeout), host],
            capture_output=True,
            text=True,
            timeout=timeout + 2
        )

        return result.returncode == 0

    except (subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"Ping to {host} failed: {e}")
        return False
