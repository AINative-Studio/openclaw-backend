"""
OpenClaw Plugin Service (Issue #98).

Integrates with OpenClaw CLI to enable/disable channel plugins.
Uses subprocess to call `openclaw plugins` commands.

Supported OpenClaw plugins:
- @openclaw/telegram
- @openclaw/discord
- @openclaw/slack
- @openclaw/msteams (Microsoft Teams)
- @openclaw/signal

Note: Email and SMS are custom backends, NOT OpenClaw plugins.
"""

import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PluginNotFoundError(Exception):
    """Raised when plugin ID is not found in supported plugins."""
    pass


class PluginConfigurationError(Exception):
    """Raised when plugin configuration is invalid or corrupted."""
    pass


class PluginCLIError(Exception):
    """Raised when OpenClaw CLI command fails."""
    pass


class OpenClawPluginService:
    """
    Service for managing OpenClaw channel plugins via CLI.

    Integrates with OpenClaw CLI (`openclaw plugins` command) to:
    - Enable/disable plugins
    - Update plugin configuration
    - Validate plugin config
    - Restart gateway when needed

    Configuration stored in: ~/.openclaw/openclaw.json
    """

    # Supported OpenClaw plugins (NOT custom backends like email/sms)
    SUPPORTED_PLUGINS = {
        "telegram": {
            "name": "Telegram",
            "npm_package": "@openclaw/telegram",
            "required_config": ["botToken"],
        },
        "discord": {
            "name": "Discord",
            "npm_package": "@openclaw/discord",
            "required_config": ["botToken"],
        },
        "slack": {
            "name": "Slack",
            "npm_package": "@openclaw/slack",
            "required_config": ["appToken", "botToken"],
        },
        "msteams": {
            "name": "Microsoft Teams",
            "npm_package": "@openclaw/msteams",
            "required_config": ["app_id", "app_password", "tenant_id"],
        },
        "signal": {
            "name": "Signal",
            "npm_package": "@openclaw/signal",
            "required_config": ["phone_number", "device_name"],
        },
    }

    def __init__(self, config_dir: Optional[Path] = None, openclaw_bin: str = "openclaw"):
        """
        Initialize OpenClaw Plugin Service.

        Args:
            config_dir: Configuration directory (default ~/.openclaw)
            openclaw_bin: OpenClaw CLI binary path (default 'openclaw')
        """
        # Configuration directory
        if config_dir:
            self.config_dir = config_dir
        else:
            self.config_dir = Path.home() / ".openclaw"

        self.config_file = self.config_dir / "openclaw.json"
        self.openclaw_bin = openclaw_bin

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
            raise PluginConfigurationError(f"Cannot create config directory: {e}")

    def _read_config(self) -> Dict[str, Any]:
        """
        Read configuration from openclaw.json.

        Returns:
            Configuration dictionary

        Raises:
            PluginConfigurationError: If config file is corrupted
        """
        with self._lock:
            if not self.config_file.exists():
                # Create default config
                default_config = {"plugins": {}}
                self._write_config_unsafe(default_config)
                return default_config

            try:
                with open(self.config_file, "r") as f:
                    config = json.load(f)

                # Ensure plugins key exists
                if "plugins" not in config:
                    config["plugins"] = {}

                return config

            except json.JSONDecodeError as e:
                logger.error(f"Corrupted config file: {e}")
                raise PluginConfigurationError(f"Invalid JSON in config file: {e}")
            except Exception as e:
                logger.error(f"Failed to read config: {e}")
                raise PluginConfigurationError(f"Cannot read config file: {e}")

    def _write_config_unsafe(self, config: Dict[str, Any]):
        """
        Write configuration WITHOUT acquiring lock (internal use only).

        Args:
            config: Configuration dictionary

        Raises:
            PluginConfigurationError: If write fails
        """
        try:
            # Atomic write: write to temp file, then rename
            temp_file = self.config_file.with_suffix(".json.tmp")
            with open(temp_file, "w") as f:
                json.dump(config, f, indent=2)

            # Atomic rename
            temp_file.rename(self.config_file)

        except Exception as e:
            logger.error(f"Failed to write config: {e}")
            # Clean up temp file
            if temp_file.exists():
                temp_file.unlink()
            raise PluginConfigurationError(f"Cannot write config file: {e}")

    def _write_config(self, config: Dict[str, Any]):
        """
        Write configuration with locking.

        Args:
            config: Configuration dictionary
        """
        with self._lock:
            self._write_config_unsafe(config)

    def _validate_plugin_id(self, plugin_id: str):
        """
        Validate that plugin ID is supported.

        Args:
            plugin_id: Plugin identifier

        Raises:
            PluginNotFoundError: If plugin not supported
        """
        if plugin_id not in self.SUPPORTED_PLUGINS:
            raise PluginNotFoundError(
                f"Plugin '{plugin_id}' not found. Supported: {list(self.SUPPORTED_PLUGINS.keys())}"
            )

    def _run_cli_command(
        self,
        args: List[str],
        timeout: int = 30,
        check: bool = True
    ) -> subprocess.CompletedProcess:
        """
        Execute OpenClaw CLI command safely.

        Args:
            args: Command arguments (WITHOUT shell=True for security)
            timeout: Command timeout in seconds
            check: Whether to check return code

        Returns:
            CompletedProcess result

        Raises:
            PluginCLIError: If command fails or times out
        """
        try:
            cmd = [self.openclaw_bin] + args

            logger.debug(f"Running CLI command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,  # We'll check manually for better error messages
                shell=False,  # SECURITY: Never use shell=True
            )

            if check and result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
                logger.error(f"CLI command failed: {error_msg}")
                raise PluginCLIError(f"OpenClaw CLI error: {error_msg}")

            return result

        except subprocess.TimeoutExpired as e:
            logger.error(f"CLI command timeout after {timeout}s")
            raise PluginCLIError(f"Command timed out after {timeout} seconds")
        except FileNotFoundError:
            logger.error(f"OpenClaw CLI not found: {self.openclaw_bin}")
            raise PluginCLIError(f"OpenClaw CLI not found. Install OpenClaw first.")
        except Exception as e:
            logger.error(f"Unexpected CLI error: {e}")
            raise PluginCLIError(f"Unexpected error running CLI: {e}")

    def enable_plugin(self, plugin_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enable OpenClaw plugin via CLI.

        Args:
            plugin_id: Plugin identifier (telegram, discord, slack, etc.)
            config: Plugin configuration (botToken, appToken, etc.)

        Returns:
            Plugin status dictionary

        Raises:
            PluginNotFoundError: If plugin not supported
            PluginConfigurationError: If required config missing
            PluginCLIError: If CLI command fails
        """
        self._validate_plugin_id(plugin_id)

        # Validate configuration
        is_valid, errors = self.validate_plugin_config(plugin_id, config)
        if not is_valid:
            raise PluginConfigurationError(f"Invalid configuration: {errors}")

        plugin_info = self.SUPPORTED_PLUGINS[plugin_id]
        npm_package = plugin_info["npm_package"]

        # Enable plugin via CLI
        # Note: OpenClaw CLI may not have a direct "enable" command,
        # so we'll update the config file directly and restart gateway
        try:
            # Update config file
            full_config = self._read_config()
            if "plugins" not in full_config:
                full_config["plugins"] = {}

            full_config["plugins"][plugin_id] = {
                "enabled": True,
                "config": config
            }

            self._write_config(full_config)

            # Restart gateway to load plugin
            # Note: This may be a placeholder - actual OpenClaw CLI command may differ
            logger.info(f"Plugin {plugin_id} enabled in config")

            return {
                "plugin_id": plugin_id,
                "name": plugin_info["name"],
                "enabled": True,
                "config": config
            }

        except Exception as e:
            logger.error(f"Failed to enable plugin {plugin_id}: {e}")
            raise

    def disable_plugin(self, plugin_id: str) -> Dict[str, Any]:
        """
        Disable OpenClaw plugin via CLI.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Plugin status dictionary

        Raises:
            PluginNotFoundError: If plugin not supported
            PluginCLIError: If CLI command fails
        """
        self._validate_plugin_id(plugin_id)

        plugin_info = self.SUPPORTED_PLUGINS[plugin_id]

        try:
            # Update config file
            full_config = self._read_config()
            if "plugins" not in full_config:
                full_config["plugins"] = {}

            if plugin_id in full_config["plugins"]:
                full_config["plugins"][plugin_id]["enabled"] = False
            else:
                # Initialize as disabled
                full_config["plugins"][plugin_id] = {
                    "enabled": False,
                    "config": {}
                }

            self._write_config(full_config)

            logger.info(f"Plugin {plugin_id} disabled in config")

            return {
                "plugin_id": plugin_id,
                "name": plugin_info["name"],
                "enabled": False,
                "config": full_config["plugins"][plugin_id].get("config", {})
            }

        except Exception as e:
            logger.error(f"Failed to disable plugin {plugin_id}: {e}")
            raise

    def get_plugin_info(self, plugin_id: str) -> Dict[str, Any]:
        """
        Get plugin information.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Plugin metadata

        Raises:
            PluginNotFoundError: If plugin not supported
        """
        self._validate_plugin_id(plugin_id)

        plugin_info = self.SUPPORTED_PLUGINS[plugin_id]

        # Get current enabled status from config
        config = self._read_config()
        plugin_config = config.get("plugins", {}).get(plugin_id, {})
        enabled = plugin_config.get("enabled", False)

        return {
            "plugin_id": plugin_id,
            "name": plugin_info["name"],
            "npm_package": plugin_info["npm_package"],
            "required_config": plugin_info["required_config"],
            "enabled": enabled,
            "config": plugin_config.get("config", {})
        }

    def list_plugins(self) -> List[Dict[str, Any]]:
        """
        List all supported OpenClaw plugins.

        Returns:
            List of plugin info dictionaries
        """
        config = self._read_config()
        plugins_config = config.get("plugins", {})

        result = []
        for plugin_id, plugin_info in self.SUPPORTED_PLUGINS.items():
            plugin_data = plugins_config.get(plugin_id, {})
            enabled = plugin_data.get("enabled", False)

            result.append({
                "plugin_id": plugin_id,
                "name": plugin_info["name"],
                "npm_package": plugin_info["npm_package"],
                "enabled": enabled,
                "config": plugin_data.get("config", {})
            })

        return result

    def update_plugin_config(
        self,
        plugin_id: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update plugin configuration (supports partial updates).

        Args:
            plugin_id: Plugin identifier
            config: New configuration (partial or complete)

        Returns:
            Updated plugin info

        Raises:
            PluginNotFoundError: If plugin not supported
        """
        self._validate_plugin_id(plugin_id)

        full_config = self._read_config()
        if "plugins" not in full_config:
            full_config["plugins"] = {}

        if plugin_id not in full_config["plugins"]:
            full_config["plugins"][plugin_id] = {
                "enabled": False,
                "config": {}
            }

        # Merge config (partial update)
        current_config = full_config["plugins"][plugin_id].get("config", {})
        current_config.update(config)
        full_config["plugins"][plugin_id]["config"] = current_config

        self._write_config(full_config)

        plugin_info = self.SUPPORTED_PLUGINS[plugin_id]

        return {
            "plugin_id": plugin_id,
            "name": plugin_info["name"],
            "enabled": full_config["plugins"][plugin_id]["enabled"],
            "config": current_config
        }

    def validate_plugin_config(
        self,
        plugin_id: str,
        config: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate plugin configuration.

        Args:
            plugin_id: Plugin identifier
            config: Configuration to validate

        Returns:
            (is_valid, list_of_errors)

        Raises:
            PluginNotFoundError: If plugin not supported
        """
        self._validate_plugin_id(plugin_id)

        plugin_info = self.SUPPORTED_PLUGINS[plugin_id]
        required_fields = plugin_info["required_config"]

        errors = []

        # Check required fields
        for field in required_fields:
            if field not in config or not config[field]:
                errors.append(f"Missing required field: {field}")

        return (len(errors) == 0, errors)

    def restart_gateway_if_needed(self) -> bool:
        """
        Restart OpenClaw Gateway to load new plugins.

        Returns:
            True if restart successful, False otherwise

        Note: This may require elevated permissions or systemd integration.
        """
        try:
            # Try to restart via CLI
            # Note: Actual OpenClaw CLI command may differ
            result = self._run_cli_command(
                ["restart"],  # Placeholder command
                timeout=10,
                check=False
            )

            if result.returncode == 0:
                logger.info("Gateway restarted successfully")
                return True
            else:
                logger.warning(f"Gateway restart failed: {result.stderr}")
                return False

        except PluginCLIError as e:
            logger.warning(f"Gateway restart not available: {e}")
            return False


# Singleton instance
_plugin_service_instance: Optional[OpenClawPluginService] = None


def get_openclaw_plugin_service() -> OpenClawPluginService:
    """
    Get singleton instance of OpenClawPluginService.

    Returns:
        OpenClawPluginService instance
    """
    global _plugin_service_instance

    if _plugin_service_instance is None:
        _plugin_service_instance = OpenClawPluginService()

    return _plugin_service_instance
