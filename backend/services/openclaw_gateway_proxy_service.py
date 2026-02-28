"""
OpenClaw Gateway Proxy Service.

Handles communication with OpenClaw Gateway and manages global channel configuration.
Configuration stored in ~/.openclaw/openclaw.json (workspace-level, NOT per-agent).
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

import httpx

from backend.schemas.channel_schemas import ChannelInfo

logger = logging.getLogger(__name__)


class ChannelNotFoundError(Exception):
    """Raised when channel ID is not found."""
    pass


class ConfigurationError(Exception):
    """Raised when configuration is invalid or cannot be read/written."""
    pass


class OpenClawGatewayProxyService:
    """
    Service for interacting with OpenClaw Gateway and managing channel configuration.

    Channels are GLOBAL workspace-level settings. Configuration stored in:
    ~/.openclaw/openclaw.json

    Supported channels: whatsapp, telegram, discord, slack, email, sms, teams
    """

    SUPPORTED_CHANNELS = {
        "whatsapp": {
            "name": "WhatsApp",
            "required_config": ["phone_number", "api_key"]
        },
        "telegram": {
            "name": "Telegram",
            "required_config": ["bot_token"]
        },
        "discord": {
            "name": "Discord",
            "required_config": ["bot_token"]
        },
        "slack": {
            "name": "Slack",
            "required_config": ["webhook_url"]
        },
        "email": {
            "name": "Email",
            "required_config": []
        },
        "sms": {
            "name": "SMS",
            "required_config": ["account_sid", "auth_token"]
        },
        "teams": {
            "name": "Microsoft Teams",
            "required_config": ["webhook_url"]
        }
    }

    def __init__(self, gateway_url: Optional[str] = None, config_dir: Optional[Path] = None):
        """
        Initialize Gateway Proxy Service.

        Args:
            gateway_url: OpenClaw Gateway URL (default from env or ws://localhost:18789)
            config_dir: Configuration directory (default ~/.openclaw)
        """
        self.gateway_url = gateway_url or os.getenv("OPENCLAW_GATEWAY_URL", "ws://localhost:18789")
        self.http_gateway_url = self.gateway_url.replace("ws://", "http://").replace("wss://", "https://")

        # Configuration directory
        if config_dir:
            self.config_dir = config_dir
        else:
            self.config_dir = Path.home() / ".openclaw"

        self.config_file = self.config_dir / "openclaw.json"

        # Thread lock for atomic file operations
        self._lock = threading.Lock()

        # Ensure config directory exists
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        """Create .openclaw directory if it doesn't exist."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create config directory: {e}")
            raise ConfigurationError(f"Cannot create config directory: {e}")

    def _read_config(self) -> Dict[str, Any]:
        """
        Read configuration from openclaw.json.

        Returns:
            Configuration dictionary

        Raises:
            ConfigurationError: If config file is corrupted or cannot be read
        """
        with self._lock:
            if not self.config_file.exists():
                # Create default config
                default_config = {"channels": {}}
                self._write_config_unsafe(default_config)
                return default_config

            try:
                with open(self.config_file, "r") as f:
                    config = json.load(f)

                # Ensure channels key exists
                if "channels" not in config:
                    config["channels"] = {}

                return config

            except json.JSONDecodeError as e:
                logger.error(f"Corrupted config file: {e}")
                raise ConfigurationError(f"Invalid JSON in config file: {e}")
            except PermissionError as e:
                logger.error(f"Permission denied reading config: {e}")
                raise ConfigurationError(f"Permission denied: {e}")
            except Exception as e:
                logger.error(f"Failed to read config: {e}")
                raise ConfigurationError(f"Cannot read config file: {e}")

    def _write_config_unsafe(self, config: Dict[str, Any]):
        """
        Write configuration WITHOUT lock (internal use only).

        Args:
            config: Configuration dictionary to write
        """
        with open(self.config_file, "w") as f:
            json.dump(config, f, indent=2)

    def _write_config(self, config: Dict[str, Any]):
        """
        Atomically write configuration to openclaw.json.

        Uses temp file + rename pattern for crash-safe writes.

        Args:
            config: Configuration dictionary to write

        Raises:
            ConfigurationError: If write fails
        """
        with self._lock:
            try:
                # Write to temp file first
                temp_file = self.config_file.with_suffix(".tmp")

                with open(temp_file, "w") as f:
                    json.dump(config, f, indent=2)

                # Atomic rename
                temp_file.rename(self.config_file)

            except Exception as e:
                logger.error(f"Failed to write config: {e}")
                # Clean up temp file if it exists
                if temp_file.exists():
                    temp_file.unlink()
                raise ConfigurationError(f"Cannot write config file: {e}")

    def list_channels(self) -> List[ChannelInfo]:
        """
        List all available channels with their current status.

        Returns:
            List of ChannelInfo objects

        Raises:
            ConfigurationError: If config cannot be read
        """
        config = self._read_config()
        channels_config = config.get("channels", {})

        channel_list = []
        gateway_health = self._check_gateway_health()

        for channel_id, channel_meta in self.SUPPORTED_CHANNELS.items():
            channel_data = channels_config.get(channel_id, {})

            channel_info = ChannelInfo(
                id=channel_id,
                name=channel_meta["name"],
                enabled=channel_data.get("enabled", False),
                available=gateway_health,
                config=channel_data.get("config", {})
            )

            channel_list.append(channel_info)

        return channel_list

    def enable_channel(self, channel_id: str, config: Dict[str, Any]) -> ChannelInfo:
        """
        Enable a channel globally with provided configuration.

        Args:
            channel_id: Channel identifier
            config: Channel configuration parameters

        Returns:
            Updated ChannelInfo

        Raises:
            ChannelNotFoundError: If channel_id is not supported
            ConfigurationError: If required config fields are missing
        """
        if channel_id not in self.SUPPORTED_CHANNELS:
            raise ChannelNotFoundError(f"Channel '{channel_id}' not found")

        channel_meta = self.SUPPORTED_CHANNELS[channel_id]

        # Validate required config fields
        for required_field in channel_meta["required_config"]:
            if required_field not in config:
                raise ConfigurationError(
                    f"Missing required config field '{required_field}' for channel '{channel_id}'"
                )

        # Update configuration
        full_config = self._read_config()

        if "channels" not in full_config:
            full_config["channels"] = {}

        full_config["channels"][channel_id] = {
            "enabled": True,
            "config": config
        }

        self._write_config(full_config)

        gateway_health = self._check_gateway_health()

        return ChannelInfo(
            id=channel_id,
            name=channel_meta["name"],
            enabled=True,
            available=gateway_health,
            config=config
        )

    def disable_channel(self, channel_id: str) -> ChannelInfo:
        """
        Disable a channel globally (preserves configuration).

        Args:
            channel_id: Channel identifier

        Returns:
            Updated ChannelInfo

        Raises:
            ChannelNotFoundError: If channel_id is not supported
        """
        if channel_id not in self.SUPPORTED_CHANNELS:
            raise ChannelNotFoundError(f"Channel '{channel_id}' not found")

        channel_meta = self.SUPPORTED_CHANNELS[channel_id]

        # Update configuration
        full_config = self._read_config()

        if "channels" not in full_config:
            full_config["channels"] = {}

        # Preserve existing config
        existing_config = full_config["channels"].get(channel_id, {}).get("config", {})

        full_config["channels"][channel_id] = {
            "enabled": False,
            "config": existing_config
        }

        self._write_config(full_config)

        return ChannelInfo(
            id=channel_id,
            name=channel_meta["name"],
            enabled=False,
            available=False,
            config=existing_config
        )

    def get_channel_status(self, channel_id: str) -> Dict[str, Any]:
        """
        Get real-time channel status from Gateway.

        Args:
            channel_id: Channel identifier

        Returns:
            Status dictionary with connected, last_message_at, etc.

        Raises:
            ChannelNotFoundError: If channel_id is not supported
        """
        if channel_id not in self.SUPPORTED_CHANNELS:
            raise ChannelNotFoundError(f"Channel '{channel_id}' not found")

        channel_meta = self.SUPPORTED_CHANNELS[channel_id]
        config = self._read_config()
        channel_data = config.get("channels", {}).get(channel_id, {})

        # Build base status
        status = {
            "id": channel_id,
            "name": channel_meta["name"],
            "enabled": channel_data.get("enabled", False),
            "connected": False,
            "last_message_at": None
        }

        # Try to get live status from Gateway
        if status["enabled"]:
            try:
                gateway_status = self._get_gateway_channel_status(channel_id)
                status.update(gateway_status)
            except (TimeoutError, ConnectionError, Exception) as e:
                logger.warning(f"Failed to get Gateway status for {channel_id}: {e}")
                status["error"] = str(e)

        return status

    def update_channel_config(self, channel_id: str, config: Dict[str, Any]) -> ChannelInfo:
        """
        Update channel configuration (partial update supported).

        Args:
            channel_id: Channel identifier
            config: Configuration parameters to update

        Returns:
            Updated ChannelInfo

        Raises:
            ChannelNotFoundError: If channel_id is not supported
        """
        if channel_id not in self.SUPPORTED_CHANNELS:
            raise ChannelNotFoundError(f"Channel '{channel_id}' not found")

        channel_meta = self.SUPPORTED_CHANNELS[channel_id]

        # Read current config
        full_config = self._read_config()

        if "channels" not in full_config:
            full_config["channels"] = {}

        # Get existing channel data
        existing_channel = full_config["channels"].get(channel_id, {})
        existing_config = existing_channel.get("config", {})

        # Merge configs (partial update)
        updated_config = {**existing_config, **config}

        # Update
        full_config["channels"][channel_id] = {
            "enabled": existing_channel.get("enabled", False),
            "config": updated_config
        }

        self._write_config(full_config)

        return ChannelInfo(
            id=channel_id,
            name=channel_meta["name"],
            enabled=existing_channel.get("enabled", False),
            available=self._check_gateway_health(),
            config=updated_config
        )

    def _check_gateway_health(self) -> bool:
        """
        Check if OpenClaw Gateway is healthy.

        Returns:
            True if Gateway is reachable and healthy, False otherwise
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.http_gateway_url}/health")
                return response.status_code == 200
        except (httpx.TimeoutException, httpx.ConnectError, ConnectionError) as e:
            logger.debug(f"Gateway health check failed: {e}")
            return False
        except Exception as e:
            logger.debug(f"Gateway health check failed: {e}")
            return False

    def _get_gateway_channel_status(self, channel_id: str) -> Dict[str, Any]:
        """
        Get real-time channel status from Gateway via HTTP.

        Args:
            channel_id: Channel identifier

        Returns:
            Status dictionary from Gateway

        Raises:
            TimeoutError: If Gateway request times out
            ConnectionError: If Gateway is unreachable
        """
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{self.http_gateway_url}/channels/{channel_id}/status"
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    return {"connected": False}

        except httpx.TimeoutException:
            raise TimeoutError(f"Gateway timeout for channel {channel_id}")
        except httpx.ConnectError:
            raise ConnectionError(f"Cannot connect to Gateway")
        except Exception as e:
            logger.error(f"Gateway status request failed: {e}")
            return {"connected": False, "error": str(e)}


# Singleton instance
_service_instance: Optional[OpenClawGatewayProxyService] = None
_service_lock = threading.Lock()


def get_gateway_proxy_service() -> OpenClawGatewayProxyService:
    """
    Get singleton instance of OpenClawGatewayProxyService.

    Returns:
        Singleton service instance
    """
    global _service_instance

    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = OpenClawGatewayProxyService()

    return _service_instance
