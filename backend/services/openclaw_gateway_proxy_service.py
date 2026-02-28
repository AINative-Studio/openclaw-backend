"""
OpenClaw Gateway Proxy Service

Provides HTTP/WebSocket communication with OpenClaw Gateway for channel management.
Handles reading and updating the ~/.openclaw/openclaw.json configuration file.

Part of Issue #81 - Create Global Channel Management API Endpoints
"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)


class OpenClawGatewayProxyServiceError(Exception):
    """Base exception for OpenClaw Gateway proxy errors"""
    pass


class ChannelNotFoundError(OpenClawGatewayProxyServiceError):
    """Raised when a requested channel does not exist"""
    pass


class ConfigurationError(OpenClawGatewayProxyServiceError):
    """Raised when configuration file operations fail"""
    pass


class OpenClawGatewayProxyService:
    """
    Service to interact with OpenClaw Gateway for channel management.

    This service provides:
    - Channel listing from Gateway's built-in plugins
    - Channel enable/disable via configuration updates
    - Channel status queries via Gateway HTTP API
    - Configuration updates in ~/.openclaw/openclaw.json
    """

    # Default OpenClaw Gateway configuration
    DEFAULT_GATEWAY_URL = "http://localhost:18789"
    DEFAULT_CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"

    # Built-in OpenClaw Gateway channels (30 total)
    AVAILABLE_CHANNELS = {
        "whatsapp": {
            "id": "whatsapp",
            "name": "WhatsApp",
            "description": "WhatsApp Business API integration",
            "capabilities": ["text", "image", "audio", "video", "document"],
            "version": "1.0.0"
        },
        "telegram": {
            "id": "telegram",
            "name": "Telegram",
            "description": "Telegram Bot API integration",
            "capabilities": ["text", "image", "audio", "video", "document", "sticker"],
            "version": "1.0.0"
        },
        "discord": {
            "id": "discord",
            "name": "Discord",
            "description": "Discord Bot integration",
            "capabilities": ["text", "image", "embed", "reaction"],
            "version": "1.0.0"
        },
        "slack": {
            "id": "slack",
            "name": "Slack",
            "description": "Slack Bot API integration",
            "capabilities": ["text", "image", "attachment", "thread"],
            "version": "1.0.0"
        },
        "email": {
            "id": "email",
            "name": "Email",
            "description": "SMTP/IMAP email integration",
            "capabilities": ["text", "html", "attachment"],
            "version": "1.0.0"
        },
        "sms": {
            "id": "sms",
            "name": "SMS",
            "description": "SMS messaging via Twilio",
            "capabilities": ["text"],
            "version": "1.0.0"
        }
    }

    def __init__(
        self,
        gateway_url: Optional[str] = None,
        config_path: Optional[Path] = None,
        timeout: float = 30.0
    ):
        """
        Initialize OpenClaw Gateway proxy service.

        Args:
            gateway_url: Gateway HTTP endpoint (default: http://localhost:18789)
            config_path: Path to openclaw.json config file (default: ~/.openclaw/openclaw.json)
            timeout: HTTP request timeout in seconds (default: 30.0)
        """
        self.gateway_url = gateway_url or os.getenv("OPENCLAW_GATEWAY_URL", self.DEFAULT_GATEWAY_URL)
        # Remove ws:// prefix if present and replace with http://
        if self.gateway_url.startswith("ws://"):
            self.gateway_url = self.gateway_url.replace("ws://", "http://")
        elif self.gateway_url.startswith("wss://"):
            self.gateway_url = self.gateway_url.replace("wss://", "https://")

        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self.timeout = timeout
        self._http_client: Optional[httpx.AsyncClient] = None

        logger.info(
            f"OpenClawGatewayProxyService initialized: "
            f"gateway_url={self.gateway_url}, config_path={self.config_path}"
        )

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self.timeout)
        return self._http_client

    async def close(self):
        """Close HTTP client"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def _load_config(self) -> Dict[str, Any]:
        """
        Load OpenClaw configuration from file.

        Returns:
            Configuration dictionary

        Raises:
            ConfigurationError: If configuration file cannot be read
        """
        try:
            if not self.config_path.exists():
                logger.warning(f"Configuration file not found: {self.config_path}")
                return {"channels": {}, "gateway": {}}

            with open(self.config_path, 'r') as f:
                config = json.load(f)
                logger.debug(f"Loaded configuration from {self.config_path}")
                return config

        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in configuration file: {e}")
        except IOError as e:
            raise ConfigurationError(f"Failed to read configuration file: {e}")

    def _save_config(self, config: Dict[str, Any]) -> None:
        """
        Save OpenClaw configuration to file.

        Args:
            config: Configuration dictionary to save

        Raises:
            ConfigurationError: If configuration file cannot be written
        """
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Write with atomic rename for safety
            temp_path = self.config_path.with_suffix('.tmp')
            with open(temp_path, 'w') as f:
                json.dump(config, f, indent=2)

            # Atomic rename
            temp_path.replace(self.config_path)
            logger.info(f"Configuration saved to {self.config_path}")

        except IOError as e:
            raise ConfigurationError(f"Failed to write configuration file: {e}")

    async def list_channels(self, enabled_only: bool = False) -> Dict[str, Any]:
        """
        List all available communication channels.

        Args:
            enabled_only: If True, only return enabled channels

        Returns:
            Dictionary with 'channels' list and 'total' count
        """
        try:
            config = self._load_config()
            enabled_channels = config.get("channels", {})

            channels = []
            for channel_id, channel_info in self.AVAILABLE_CHANNELS.items():
                # Check if channel is enabled in config
                is_enabled = enabled_channels.get(channel_id, {}).get("enabled", False)

                if enabled_only and not is_enabled:
                    continue

                # Query connection status from Gateway if enabled
                connected = False
                if is_enabled:
                    connected = await self._check_channel_connection(channel_id)

                channel_data = {
                    **channel_info,
                    "enabled": is_enabled,
                    "connected": connected
                }
                channels.append(channel_data)

            logger.info(f"Listed {len(channels)} channels (enabled_only={enabled_only})")
            return {
                "channels": channels,
                "total": len(channels)
            }

        except Exception as e:
            logger.error(f"Failed to list channels: {e}", exc_info=True)
            raise OpenClawGatewayProxyServiceError(f"Failed to list channels: {e}")

    async def enable_channel(self, channel_id: str) -> Dict[str, Any]:
        """
        Enable a communication channel globally.

        Args:
            channel_id: Channel identifier (e.g., 'whatsapp', 'telegram')

        Returns:
            Dictionary with channel_id, enabled status, and message

        Raises:
            ChannelNotFoundError: If channel does not exist
            ConfigurationError: If configuration update fails
        """
        # Validate channel exists
        if channel_id not in self.AVAILABLE_CHANNELS:
            raise ChannelNotFoundError(f"Channel '{channel_id}' not found")

        try:
            config = self._load_config()

            # Initialize channels section if missing
            if "channels" not in config:
                config["channels"] = {}

            # Check if already enabled
            is_already_enabled = config["channels"].get(channel_id, {}).get("enabled", False)

            # Enable channel in config
            if channel_id not in config["channels"]:
                config["channels"][channel_id] = {}

            config["channels"][channel_id]["enabled"] = True

            # Save updated configuration
            self._save_config(config)

            message = "Channel already enabled" if is_already_enabled else "Channel enabled successfully"
            logger.info(f"Channel '{channel_id}' enabled: {message}")

            return {
                "channel_id": channel_id,
                "enabled": True,
                "message": message
            }

        except ChannelNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to enable channel '{channel_id}': {e}", exc_info=True)
            raise ConfigurationError(f"Failed to enable channel: {e}")

    async def disable_channel(self, channel_id: str) -> Dict[str, Any]:
        """
        Disable a communication channel globally.

        Args:
            channel_id: Channel identifier

        Returns:
            Dictionary with channel_id, enabled status, and message

        Raises:
            ChannelNotFoundError: If channel does not exist
            ConfigurationError: If configuration update fails
        """
        # Validate channel exists
        if channel_id not in self.AVAILABLE_CHANNELS:
            raise ChannelNotFoundError(f"Channel '{channel_id}' not found")

        try:
            config = self._load_config()

            # Initialize channels section if missing
            if "channels" not in config:
                config["channels"] = {}

            # Check if already disabled
            is_already_disabled = not config["channels"].get(channel_id, {}).get("enabled", False)

            # Disable channel in config
            if channel_id not in config["channels"]:
                config["channels"][channel_id] = {}

            config["channels"][channel_id]["enabled"] = False

            # Save updated configuration
            self._save_config(config)

            message = "Channel already disabled" if is_already_disabled else "Channel disabled successfully"
            logger.info(f"Channel '{channel_id}' disabled: {message}")

            return {
                "channel_id": channel_id,
                "enabled": False,
                "message": message
            }

        except ChannelNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to disable channel '{channel_id}': {e}", exc_info=True)
            raise ConfigurationError(f"Failed to disable channel: {e}")

    async def get_channel_status(self, channel_id: str) -> Dict[str, Any]:
        """
        Get detailed status of a communication channel.

        Args:
            channel_id: Channel identifier

        Returns:
            Dictionary with channel_id, enabled, connected, status, and connection_details

        Raises:
            ChannelNotFoundError: If channel does not exist
        """
        # Validate channel exists
        if channel_id not in self.AVAILABLE_CHANNELS:
            raise ChannelNotFoundError(f"Channel '{channel_id}' not found")

        try:
            config = self._load_config()
            is_enabled = config.get("channels", {}).get(channel_id, {}).get("enabled", False)

            # If disabled, return disabled status immediately
            if not is_enabled:
                return {
                    "channel_id": channel_id,
                    "enabled": False,
                    "connected": False,
                    "status": "disabled",
                    "last_activity": None,
                    "connection_details": None
                }

            # Check connection status from Gateway
            connected = await self._check_channel_connection(channel_id)

            # Query detailed connection info from Gateway
            connection_details = await self._get_connection_details(channel_id)

            status = "active" if connected else "disconnected"
            last_activity = connection_details.get("last_activity") if connected else None

            return {
                "channel_id": channel_id,
                "enabled": is_enabled,
                "connected": connected,
                "status": status,
                "last_activity": last_activity,
                "connection_details": connection_details if connected else {"error": "Not connected"}
            }

        except ChannelNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to get channel status for '{channel_id}': {e}", exc_info=True)
            raise OpenClawGatewayProxyServiceError(f"Failed to get channel status: {e}")

    async def update_channel_config(
        self,
        channel_id: str,
        config_update: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update channel configuration.

        Args:
            channel_id: Channel identifier
            config_update: Configuration values to update

        Returns:
            Dictionary with channel_id, updated status, message, and new config

        Raises:
            ChannelNotFoundError: If channel does not exist
            ConfigurationError: If configuration update fails
        """
        # Validate channel exists
        if channel_id not in self.AVAILABLE_CHANNELS:
            raise ChannelNotFoundError(f"Channel '{channel_id}' not found")

        try:
            config = self._load_config()

            # Initialize channels section if missing
            if "channels" not in config:
                config["channels"] = {}

            # Initialize channel config if missing
            if channel_id not in config["channels"]:
                config["channels"][channel_id] = {"enabled": False}

            # Update configuration values
            for key, value in config_update.items():
                config["channels"][channel_id][key] = value

            # Save updated configuration
            self._save_config(config)

            logger.info(f"Updated configuration for channel '{channel_id}': {list(config_update.keys())}")

            return {
                "channel_id": channel_id,
                "updated": True,
                "message": "Configuration updated successfully",
                "config": config["channels"][channel_id]
            }

        except ChannelNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to update config for '{channel_id}': {e}", exc_info=True)
            raise ConfigurationError(f"Failed to update channel configuration: {e}")

    async def _check_channel_connection(self, channel_id: str) -> bool:
        """
        Check if a channel is currently connected via Gateway health check.

        Args:
            channel_id: Channel identifier

        Returns:
            True if channel is connected, False otherwise
        """
        try:
            client = await self._get_http_client()
            response = await client.get(f"{self.gateway_url}/health")

            if response.status_code == 200:
                health_data = response.json()
                # For now, assume healthy gateway means channels can connect
                # In real implementation, Gateway would expose per-channel status
                return health_data.get("status") == "healthy"

            return False

        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning(f"Failed to check connection for '{channel_id}': {e}")
            return False

    async def _get_connection_details(self, channel_id: str) -> Dict[str, Any]:
        """
        Get detailed connection information from Gateway.

        Args:
            channel_id: Channel identifier

        Returns:
            Dictionary with connection details
        """
        try:
            # For now, return mock connection details
            # In real implementation, Gateway would expose channel-specific endpoints
            return {
                "session_id": f"{channel_id}:session:main",
                "qr_code_required": False,
                "authenticated": True,
                "last_activity": "2026-02-27T10:30:00Z"
            }

        except Exception as e:
            logger.warning(f"Failed to get connection details for '{channel_id}': {e}")
            return {"error": str(e)}

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
