"""
OpenClaw Channels Service

Wraps OpenClaw CLI channel management commands to provide a clean API
for managing messaging platform integrations (WhatsApp, Slack, Discord, etc.)
"""

import json
import logging
import subprocess
from typing import Dict, Any, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ChannelType(str, Enum):
    """Supported channel types"""
    WHATSAPP = "whatsapp"
    SLACK = "slack"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    SIGNAL = "signal"
    IMESSAGE = "imessage"
    MSTEAMS = "msteams"
    GOOGLECHAT = "googlechat"
    MATTERMOST = "mattermost"
    NEXTCLOUD_TALK = "nextcloud-talk"
    MATRIX = "matrix"
    BLUEBUBBLES = "bluebubbles"
    LINE = "line"
    ZALO = "zalo"
    NOSTR = "nostr"
    TLON = "tlon"


class ChannelAuthType(str, Enum):
    """Channel authentication types"""
    BOT_TOKEN = "bot_token"  # Telegram, Discord
    OAUTH = "oauth"  # Slack, Google Chat
    QR_CODE = "qr_code"  # WhatsApp
    CLI_TOOL = "cli_tool"  # Signal, iMessage
    WEBHOOK = "webhook"  # Google Chat, BlueBubbles
    HOMESERVER = "homeserver"  # Matrix
    SHIP_LOGIN = "ship_login"  # Tlon
    NONE = "none"  # Some channels don't need auth


def get_available_channels() -> Dict[str, Any]:
    """
    Get all available channel types with their capabilities.

    Returns:
        Dict with channel capabilities and support information

    Raises:
        RuntimeError: If OpenClaw CLI is not available or command fails
    """
    try:
        result = subprocess.run(
            ["openclaw", "channels", "capabilities", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )

        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get channel capabilities: {e.stderr}")
        raise RuntimeError(f"OpenClaw channels command failed: {e.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("OpenClaw channels command timed out")
        raise RuntimeError("OpenClaw channels command timed out")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenClaw channels output: {e}")
        raise RuntimeError("Invalid JSON response from OpenClaw")
    except FileNotFoundError:
        logger.error("OpenClaw CLI not found in PATH")
        raise RuntimeError("OpenClaw CLI is not installed or not in PATH")


def get_configured_channels() -> Dict[str, Any]:
    """
    Get all currently configured channels from OpenClaw.

    Returns:
        Dict with configured channels and their status

    Raises:
        RuntimeError: If OpenClaw CLI command fails
    """
    try:
        result = subprocess.run(
            ["openclaw", "channels", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )

        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to list channels: {e.stderr}")
        raise RuntimeError(f"OpenClaw channels list failed: {e.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("OpenClaw channels list timed out")
        raise RuntimeError("OpenClaw channels list timed out")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenClaw channels list: {e}")
        raise RuntimeError("Invalid JSON response from OpenClaw")
    except FileNotFoundError:
        logger.error("OpenClaw CLI not found in PATH")
        raise RuntimeError("OpenClaw CLI is not installed or not in PATH")


def get_channel_status(channel: str, account_id: str = "default") -> Dict[str, Any]:
    """
    Get detailed status for a specific channel.

    Args:
        channel: Channel type (e.g., "whatsapp", "slack")
        account_id: Account identifier (default: "default")

    Returns:
        Dict with channel status and configuration

    Raises:
        RuntimeError: If OpenClaw CLI command fails
    """
    try:
        # Get all channels and filter for the requested one
        all_channels = get_configured_channels()

        # Check if channel exists in chat section
        if channel in all_channels.get("chat", {}):
            accounts = all_channels["chat"][channel]
            if account_id in accounts:
                # Get detailed capabilities
                capabilities = get_available_channels()
                channel_caps = next(
                    (c for c in capabilities.get("channels", []) if c.get("channel") == channel),
                    None
                )

                return {
                    "channel": channel,
                    "account_id": account_id,
                    "configured": True,
                    "capabilities": channel_caps,
                }

        # Channel not configured
        return {
            "channel": channel,
            "account_id": account_id,
            "configured": False,
        }

    except Exception as e:
        logger.error(f"Failed to get channel status for {channel}: {e}")
        raise RuntimeError(f"Failed to get channel status: {str(e)}")


def add_channel_bot_token(
    channel: str,
    token: str,
    account_id: str = "default",
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Add a channel using bot token authentication (Telegram, Discord).

    Args:
        channel: Channel type
        token: Bot token
        account_id: Account identifier
        name: Display name for this account

    Returns:
        Dict with operation result

    Raises:
        RuntimeError: If OpenClaw CLI command fails
    """
    try:
        cmd = [
            "openclaw", "channels", "add",
            "--channel", channel,
            "--account", account_id,
            "--token", token,
        ]

        if name:
            cmd.extend(["--name", name])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        return {
            "success": True,
            "channel": channel,
            "account_id": account_id,
            "message": f"Successfully added {channel} channel",
        }

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to add {channel} channel: {e.stderr}")
        raise RuntimeError(f"Failed to add channel: {e.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Add channel command timed out")


def add_channel_slack(
    bot_token: str,
    app_token: str,
    account_id: str = "default",
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Add Slack channel with bot and app tokens.

    Args:
        bot_token: Slack bot token (xoxb-...)
        app_token: Slack app token (xapp-...)
        account_id: Account identifier
        name: Display name for this account

    Returns:
        Dict with operation result

    Raises:
        RuntimeError: If OpenClaw CLI command fails
    """
    try:
        cmd = [
            "openclaw", "channels", "add",
            "--channel", "slack",
            "--account", account_id,
            "--bot-token", bot_token,
            "--app-token", app_token,
        ]

        if name:
            cmd.extend(["--name", name])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        return {
            "success": True,
            "channel": "slack",
            "account_id": account_id,
            "message": "Successfully added Slack channel",
        }

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to add Slack channel: {e.stderr}")
        raise RuntimeError(f"Failed to add Slack channel: {e.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Add Slack channel command timed out")


def login_channel(
    channel: str,
    account_id: str = "default",
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Initiate login flow for a channel (WhatsApp QR code, OAuth, etc.).

    Args:
        channel: Channel type
        account_id: Account identifier
        verbose: Enable verbose logging

    Returns:
        Dict with login instructions and status

    Raises:
        RuntimeError: If OpenClaw CLI command fails
    """
    try:
        cmd = [
            "openclaw", "channels", "login",
            "--channel", channel,
            "--account", account_id,
        ]

        if verbose:
            cmd.append("--verbose")

        # Note: This command may be interactive (QR code display)
        # For WhatsApp, it will show a QR code to scan
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # Longer timeout for interactive auth
        )

        if result.returncode == 0:
            return {
                "success": True,
                "channel": channel,
                "account_id": account_id,
                "message": f"Login initiated for {channel}",
                "output": result.stdout,
            }
        else:
            raise RuntimeError(f"Login failed: {result.stderr}")

    except subprocess.TimeoutExpired:
        raise RuntimeError("Login command timed out - user may need to complete authentication")
    except Exception as e:
        logger.error(f"Failed to login to {channel}: {e}")
        raise RuntimeError(f"Failed to login: {str(e)}")


def logout_channel(
    channel: str,
    account_id: str = "default",
) -> Dict[str, Any]:
    """
    Logout from a channel session.

    Args:
        channel: Channel type
        account_id: Account identifier

    Returns:
        Dict with operation result

    Raises:
        RuntimeError: If OpenClaw CLI command fails
    """
    try:
        result = subprocess.run(
            [
                "openclaw", "channels", "logout",
                "--channel", channel,
                "--account", account_id,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        return {
            "success": True,
            "channel": channel,
            "account_id": account_id,
            "message": f"Successfully logged out from {channel}",
        }

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to logout from {channel}: {e.stderr}")
        raise RuntimeError(f"Failed to logout: {e.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Logout command timed out")


def remove_channel(
    channel: str,
    account_id: str = "default",
) -> Dict[str, Any]:
    """
    Remove/disable a channel account.

    Args:
        channel: Channel type
        account_id: Account identifier

    Returns:
        Dict with operation result

    Raises:
        RuntimeError: If OpenClaw CLI command fails
    """
    try:
        result = subprocess.run(
            [
                "openclaw", "channels", "remove",
                "--channel", channel,
                "--account", account_id,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        return {
            "success": True,
            "channel": channel,
            "account_id": account_id,
            "message": f"Successfully removed {channel} channel",
        }

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to remove {channel} channel: {e.stderr}")
        raise RuntimeError(f"Failed to remove channel: {e.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Remove channel command timed out")


def get_channel_auth_instructions(channel: str) -> Dict[str, Any]:
    """
    Get authentication instructions for a specific channel type.

    Args:
        channel: Channel type

    Returns:
        Dict with authentication instructions and requirements
    """
    # Map channels to their authentication requirements
    auth_instructions = {
        "telegram": {
            "auth_type": ChannelAuthType.BOT_TOKEN,
            "instructions": [
                "1. Open Telegram and search for @BotFather",
                "2. Send /newbot and follow the prompts",
                "3. Copy the bot token provided",
                "4. Enter the token below to connect",
            ],
            "docs_url": "https://core.telegram.org/bots#how-do-i-create-a-bot",
            "required_fields": ["token"],
        },
        "discord": {
            "auth_type": ChannelAuthType.BOT_TOKEN,
            "instructions": [
                "1. Go to Discord Developer Portal",
                "2. Create a new application",
                "3. Add a bot to your application",
                "4. Copy the bot token",
                "5. Invite the bot to your server",
            ],
            "docs_url": "https://discord.com/developers/docs/intro",
            "required_fields": ["token"],
        },
        "slack": {
            "auth_type": ChannelAuthType.OAUTH,
            "instructions": [
                "1. Go to api.slack.com/apps",
                "2. Create a new Slack app",
                "3. Enable Socket Mode and get app token (xapp-...)",
                "4. Add OAuth scopes and install to workspace",
                "5. Copy bot token (xoxb-...) and app token",
            ],
            "docs_url": "https://api.slack.com/start/quickstart",
            "required_fields": ["bot_token", "app_token"],
        },
        "whatsapp": {
            "auth_type": ChannelAuthType.QR_CODE,
            "instructions": [
                "1. Click 'Connect' to generate QR code",
                "2. Open WhatsApp on your phone",
                "3. Go to Settings > Linked Devices",
                "4. Tap 'Link a Device'",
                "5. Scan the QR code displayed",
            ],
            "docs_url": "https://docs.openclaw.ai/channels/whatsapp",
            "required_fields": [],
        },
        "signal": {
            "auth_type": ChannelAuthType.CLI_TOOL,
            "instructions": [
                "1. Install signal-cli",
                "2. Register your phone number",
                "3. Verify with the code sent to your phone",
                "4. Configure OpenClaw with signal-cli path",
            ],
            "docs_url": "https://github.com/AsamK/signal-cli",
            "required_fields": ["signal_number", "cli_path"],
        },
        "imessage": {
            "auth_type": ChannelAuthType.CLI_TOOL,
            "instructions": [
                "1. This only works on macOS",
                "2. Install imsg CLI tool",
                "3. Grant necessary permissions",
                "4. Configure database path",
            ],
            "docs_url": "https://docs.openclaw.ai/channels/imessage",
            "required_fields": ["cli_path", "db_path"],
        },
        "matrix": {
            "auth_type": ChannelAuthType.HOMESERVER,
            "instructions": [
                "1. Choose a Matrix homeserver (e.g., matrix.org)",
                "2. Create an account if you don't have one",
                "3. Get your access token from account settings",
                "4. Enter homeserver URL and credentials",
            ],
            "docs_url": "https://matrix.org/docs/guides/",
            "required_fields": ["homeserver", "user_id", "access_token"],
        },
    }

    return auth_instructions.get(
        channel,
        {
            "auth_type": ChannelAuthType.NONE,
            "instructions": ["No specific instructions available for this channel"],
            "required_fields": [],
        }
    )
