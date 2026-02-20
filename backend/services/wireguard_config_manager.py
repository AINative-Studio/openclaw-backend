"""
WireGuard Configuration Manager

Manages WireGuard configuration file updates for peer provisioning.
Implements safe config updates without connection loss.

Part of E1-S3: WireGuard Peer Provisioning Service

Security considerations:
- Config file permissions: 0600 (owner read/write only)
- Atomic config updates to prevent corruption
- Validation before applying changes
"""

import os
import tempfile
import shutil
import threading
from typing import List, Dict, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class WireGuardPeer:
    """Represents a WireGuard peer configuration"""

    def __init__(
        self,
        public_key: str,
        allowed_ips: List[str],
        persistent_keepalive: Optional[int] = None,
        endpoint: Optional[str] = None,
        preshared_key: Optional[str] = None
    ):
        """
        Initialize peer configuration

        Args:
            public_key: Peer's WireGuard public key
            allowed_ips: List of allowed IP ranges (CIDR notation)
            persistent_keepalive: Keepalive interval in seconds
            endpoint: Peer endpoint (hostname:port)
            preshared_key: Optional preshared key for additional security
        """
        self.public_key = public_key
        self.allowed_ips = allowed_ips
        self.persistent_keepalive = persistent_keepalive
        self.endpoint = endpoint
        self.preshared_key = preshared_key

    def to_config_section(self) -> str:
        """
        Convert peer to WireGuard config section

        Returns:
            Formatted config section string
        """
        lines = [
            "[Peer]",
            f"PublicKey = {self.public_key}",
            f"AllowedIPs = {', '.join(self.allowed_ips)}"
        ]

        if self.endpoint:
            lines.append(f"Endpoint = {self.endpoint}")

        if self.persistent_keepalive is not None:
            lines.append(f"PersistentKeepalive = {self.persistent_keepalive}")

        if self.preshared_key:
            lines.append(f"PresharedKey = {self.preshared_key}")

        return "\n".join(lines)


class WireGuardConfigManager:
    """
    WireGuard configuration file manager

    Provides thread-safe operations for managing WireGuard peer configurations.
    Supports atomic config updates and safe reloading.

    Attributes:
        config_path: Path to WireGuard configuration file
        _lock: Thread lock for concurrent access safety
    """

    def __init__(self, config_path: str = "/etc/wireguard/wg0.conf"):
        """
        Initialize config manager

        Args:
            config_path: Path to WireGuard config file
        """
        self.config_path = Path(config_path)
        self._lock = threading.Lock()

        # Ensure config directory exists (for testing)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize empty config if doesn't exist
        if not self.config_path.exists():
            self._write_config("")
            logger.info(f"Created new WireGuard config at {config_path}")

    def _read_config(self) -> str:
        """
        Read configuration file

        Returns:
            Config file contents as string
        """
        try:
            return self.config_path.read_text()
        except FileNotFoundError:
            return ""
        except PermissionError as e:
            logger.error(f"Permission denied reading config: {e}")
            raise

    def _write_config(self, content: str) -> None:
        """
        Write configuration file atomically

        Uses atomic write (write to temp, then rename) to prevent corruption.

        Args:
            content: Config file contents
        """
        # Create temporary file in same directory
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self.config_path.parent,
            prefix=".wg_",
            suffix=".conf.tmp"
        )

        try:
            # Write content to temp file
            with os.fdopen(temp_fd, 'w') as f:
                f.write(content)

            # Set proper permissions (owner read/write only)
            os.chmod(temp_path, 0o600)

            # Atomic rename
            shutil.move(temp_path, self.config_path)

            logger.debug(f"Updated config file: {self.config_path}")

        except Exception as e:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except:
                pass
            raise e

    def add_peer(
        self,
        public_key: str,
        allowed_ips: List[str],
        persistent_keepalive: Optional[int] = None,
        endpoint: Optional[str] = None
    ) -> None:
        """
        Add a peer to the configuration

        Thread-safe operation that appends peer to config file.

        Args:
            public_key: Peer's WireGuard public key
            allowed_ips: List of allowed IP ranges
            persistent_keepalive: Keepalive interval in seconds
            endpoint: Peer endpoint (hostname:port)
        """
        with self._lock:
            # Read current config
            current_config = self._read_config()

            # Check if peer already exists
            if f"PublicKey = {public_key}" in current_config:
                logger.warning(
                    f"Peer with public key {public_key} already exists in config"
                )
                return

            # Create peer section
            peer = WireGuardPeer(
                public_key=public_key,
                allowed_ips=allowed_ips,
                persistent_keepalive=persistent_keepalive,
                endpoint=endpoint
            )

            # Append peer section
            if current_config and not current_config.endswith("\n\n"):
                separator = "\n\n" if current_config.endswith("\n") else "\n\n"
            else:
                separator = ""

            new_config = current_config + separator + peer.to_config_section() + "\n"

            # Write updated config
            self._write_config(new_config)

            logger.info(f"Added peer {public_key} to config")

    def remove_peer(self, public_key: str) -> bool:
        """
        Remove a peer from the configuration

        Args:
            public_key: Peer's WireGuard public key

        Returns:
            True if peer was removed, False if not found
        """
        with self._lock:
            # Read current config
            current_config = self._read_config()

            # Split into sections
            sections = current_config.split("\n\n")
            new_sections = []
            removed = False

            for section in sections:
                if f"PublicKey = {public_key}" in section:
                    # Skip this peer section
                    removed = True
                    logger.info(f"Removed peer {public_key} from config")
                else:
                    new_sections.append(section)

            if not removed:
                logger.warning(f"Peer {public_key} not found in config")
                return False

            # Reconstruct config
            new_config = "\n\n".join(new_sections)

            # Write updated config
            self._write_config(new_config)

            return True

    def get_config(self) -> str:
        """
        Get current configuration contents

        Returns:
            Config file contents as string
        """
        with self._lock:
            return self._read_config()

    def reload_config(self) -> bool:
        """
        Reload WireGuard configuration without disrupting existing connections

        Uses `wg syncconf` command for graceful reload.

        Returns:
            True if reload successful

        Note:
            Requires root privileges to execute wg command.
            In production, this should be called via sudo or systemd.
        """
        # Extract interface name from config path
        interface = self.config_path.stem  # e.g., "wg0" from "wg0.conf"

        try:
            import subprocess

            # Use wg syncconf for graceful reload (no connection loss)
            result = subprocess.run(
                ["wg", "syncconf", interface, str(self.config_path)],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                logger.info(f"Reloaded WireGuard config for interface {interface}")
                return True
            else:
                logger.error(
                    f"Failed to reload config: {result.stderr}"
                )
                return False

        except subprocess.TimeoutExpired:
            logger.error("WireGuard reload timed out")
            return False
        except FileNotFoundError:
            logger.warning(
                "wg command not found - skipping reload (development mode?)"
            )
            return False
        except Exception as e:
            logger.error(f"Error reloading WireGuard config: {e}")
            return False

    def validate_config(self) -> bool:
        """
        Validate configuration syntax

        Returns:
            True if config is valid

        Note:
            Currently performs basic validation.
            Could be extended to use `wg-quick` for full validation.
        """
        with self._lock:
            config = self._read_config()

            # Basic validation: check for required sections
            if "[Peer]" in config:
                # Check each peer has PublicKey and AllowedIPs
                sections = config.split("[Peer]")
                for section in sections[1:]:  # Skip first (before any [Peer])
                    if "PublicKey" not in section:
                        logger.error("Peer section missing PublicKey")
                        return False
                    if "AllowedIPs" not in section:
                        logger.error("Peer section missing AllowedIPs")
                        return False

            return True
