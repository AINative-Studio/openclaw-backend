"""
Unit tests for OpenClawGatewayProxyService

Tests the service layer for channel management independently of the API endpoints.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from backend.services.openclaw_gateway_proxy_service import (
    OpenClawGatewayProxyService,
    ChannelNotFoundError,
    ConfigurationError,
    OpenClawGatewayProxyServiceError
)


@pytest.fixture
def temp_config_file():
    """Create a temporary configuration file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config = {
            "channels": {
                "whatsapp": {
                    "enabled": True,
                    "timeout": 30
                },
                "telegram": {
                    "enabled": False
                }
            },
            "gateway": {
                "url": "http://localhost:18789"
            }
        }
        json.dump(config, f)
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def service(temp_config_file):
    """Create service instance with temporary config"""
    return OpenClawGatewayProxyService(
        gateway_url="http://localhost:18789",
        config_path=temp_config_file
    )


class TestServiceInitialization:
    """Test service initialization"""

    def test_default_initialization(self):
        """Should initialize with default values"""
        service = OpenClawGatewayProxyService()
        assert service.gateway_url == "http://localhost:18789"
        assert service.config_path == Path.home() / ".openclaw" / "openclaw.json"
        assert service.timeout == 30.0

    def test_custom_initialization(self, temp_config_file):
        """Should initialize with custom values"""
        service = OpenClawGatewayProxyService(
            gateway_url="http://custom:8080",
            config_path=temp_config_file,
            timeout=60.0
        )
        assert service.gateway_url == "http://custom:8080"
        assert service.config_path == temp_config_file
        assert service.timeout == 60.0

    def test_ws_url_conversion(self):
        """Should convert ws:// to http://"""
        service = OpenClawGatewayProxyService(gateway_url="ws://localhost:18789")
        assert service.gateway_url == "http://localhost:18789"

    def test_wss_url_conversion(self):
        """Should convert wss:// to https://"""
        service = OpenClawGatewayProxyService(gateway_url="wss://secure:18789")
        assert service.gateway_url == "https://secure:18789"


class TestConfigurationManagement:
    """Test configuration file operations"""

    @pytest.mark.asyncio
    async def test_load_config_success(self, service, temp_config_file):
        """Should load configuration from file"""
        config = service._load_config()
        assert "channels" in config
        assert "whatsapp" in config["channels"]
        assert config["channels"]["whatsapp"]["enabled"] is True

    def test_load_config_missing_file(self):
        """Should return default config when file missing"""
        service = OpenClawGatewayProxyService(
            config_path=Path("/nonexistent/path.json")
        )
        config = service._load_config()
        assert config == {"channels": {}, "gateway": {}}

    def test_load_config_invalid_json(self):
        """Should raise ConfigurationError for invalid JSON"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{invalid json")
            temp_path = Path(f.name)

        try:
            service = OpenClawGatewayProxyService(config_path=temp_path)
            with pytest.raises(ConfigurationError):
                service._load_config()
        finally:
            temp_path.unlink()

    @pytest.mark.asyncio
    async def test_save_config_success(self, service):
        """Should save configuration to file"""
        config = {
            "channels": {
                "discord": {"enabled": True}
            }
        }
        service._save_config(config)

        # Verify saved
        loaded = service._load_config()
        assert loaded["channels"]["discord"]["enabled"] is True


class TestListChannels:
    """Test list_channels method"""

    @pytest.mark.asyncio
    async def test_list_channels_all(self, service):
        """Should list all channels with status"""
        with patch.object(service, '_check_channel_connection', return_value=True):
            result = await service.list_channels()

            assert "channels" in result
            assert "total" in result
            assert result["total"] > 0

            # Verify WhatsApp is in the list
            whatsapp = next((ch for ch in result["channels"] if ch["id"] == "whatsapp"), None)
            assert whatsapp is not None
            assert whatsapp["name"] == "WhatsApp"
            assert whatsapp["enabled"] is True

    @pytest.mark.asyncio
    async def test_list_channels_enabled_only(self, service):
        """Should filter to enabled channels only"""
        with patch.object(service, '_check_channel_connection', return_value=True):
            result = await service.list_channels(enabled_only=True)

            # Should only include enabled channels
            assert all(ch["enabled"] for ch in result["channels"])

    @pytest.mark.asyncio
    async def test_list_channels_checks_connection(self, service):
        """Should check connection status for enabled channels"""
        connection_mock = AsyncMock(return_value=True)
        with patch.object(service, '_check_channel_connection', connection_mock):
            result = await service.list_channels()

            # Should have called connection check for enabled channel (whatsapp)
            assert connection_mock.called


class TestEnableChannel:
    """Test enable_channel method"""

    @pytest.mark.asyncio
    async def test_enable_channel_success(self, service):
        """Should enable a disabled channel"""
        result = await service.enable_channel("telegram")

        assert result["channel_id"] == "telegram"
        assert result["enabled"] is True
        assert "message" in result

        # Verify saved to config
        config = service._load_config()
        assert config["channels"]["telegram"]["enabled"] is True

    @pytest.mark.asyncio
    async def test_enable_already_enabled_channel(self, service):
        """Should succeed when enabling already enabled channel"""
        result = await service.enable_channel("whatsapp")

        assert result["channel_id"] == "whatsapp"
        assert result["enabled"] is True
        assert "already enabled" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_enable_invalid_channel(self, service):
        """Should raise ChannelNotFoundError for invalid channel"""
        with pytest.raises(ChannelNotFoundError):
            await service.enable_channel("invalid_channel")


class TestDisableChannel:
    """Test disable_channel method"""

    @pytest.mark.asyncio
    async def test_disable_channel_success(self, service):
        """Should disable an enabled channel"""
        result = await service.disable_channel("whatsapp")

        assert result["channel_id"] == "whatsapp"
        assert result["enabled"] is False
        assert "message" in result

        # Verify saved to config
        config = service._load_config()
        assert config["channels"]["whatsapp"]["enabled"] is False

    @pytest.mark.asyncio
    async def test_disable_already_disabled_channel(self, service):
        """Should succeed when disabling already disabled channel"""
        result = await service.disable_channel("telegram")

        assert result["channel_id"] == "telegram"
        assert result["enabled"] is False
        assert "already disabled" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_disable_invalid_channel(self, service):
        """Should raise ChannelNotFoundError for invalid channel"""
        with pytest.raises(ChannelNotFoundError):
            await service.disable_channel("invalid_channel")


class TestGetChannelStatus:
    """Test get_channel_status method"""

    @pytest.mark.asyncio
    async def test_get_status_enabled_connected(self, service):
        """Should return active status for enabled and connected channel"""
        with patch.object(service, '_check_channel_connection', return_value=True):
            with patch.object(service, '_get_connection_details', return_value={
                "session_id": "whatsapp:session:main",
                "authenticated": True
            }):
                result = await service.get_channel_status("whatsapp")

                assert result["channel_id"] == "whatsapp"
                assert result["enabled"] is True
                assert result["connected"] is True
                assert result["status"] == "active"
                assert result["connection_details"]["authenticated"] is True

    @pytest.mark.asyncio
    async def test_get_status_disabled(self, service):
        """Should return disabled status for disabled channel"""
        result = await service.get_channel_status("telegram")

        assert result["channel_id"] == "telegram"
        assert result["enabled"] is False
        assert result["connected"] is False
        assert result["status"] == "disabled"
        assert result["connection_details"] is None

    @pytest.mark.asyncio
    async def test_get_status_enabled_disconnected(self, service):
        """Should return disconnected status when connection check fails"""
        with patch.object(service, '_check_channel_connection', return_value=False):
            with patch.object(service, '_get_connection_details', return_value={"error": "Not connected"}):
                result = await service.get_channel_status("whatsapp")

                assert result["enabled"] is True
                assert result["connected"] is False
                assert result["status"] == "disconnected"

    @pytest.mark.asyncio
    async def test_get_status_invalid_channel(self, service):
        """Should raise ChannelNotFoundError for invalid channel"""
        with pytest.raises(ChannelNotFoundError):
            await service.get_channel_status("invalid_channel")


class TestUpdateChannelConfig:
    """Test update_channel_config method"""

    @pytest.mark.asyncio
    async def test_update_config_success(self, service):
        """Should update channel configuration"""
        config_update = {
            "timeout": 60,
            "max_retries": 5,
            "auto_reconnect": True
        }

        result = await service.update_channel_config("whatsapp", config_update)

        assert result["channel_id"] == "whatsapp"
        assert result["updated"] is True
        assert result["config"]["timeout"] == 60
        assert result["config"]["max_retries"] == 5

        # Verify saved to config
        config = service._load_config()
        assert config["channels"]["whatsapp"]["timeout"] == 60

    @pytest.mark.asyncio
    async def test_update_config_partial(self, service):
        """Should allow partial configuration updates"""
        result = await service.update_channel_config("telegram", {"timeout": 45})

        assert result["updated"] is True
        assert result["config"]["timeout"] == 45

    @pytest.mark.asyncio
    async def test_update_config_new_channel(self, service):
        """Should create config for channel that doesn't have one yet"""
        result = await service.update_channel_config("discord", {"timeout": 30})

        assert result["updated"] is True

        # Verify created in config
        config = service._load_config()
        assert "discord" in config["channels"]
        assert config["channels"]["discord"]["timeout"] == 30

    @pytest.mark.asyncio
    async def test_update_config_invalid_channel(self, service):
        """Should raise ChannelNotFoundError for invalid channel"""
        with pytest.raises(ChannelNotFoundError):
            await service.update_channel_config("invalid_channel", {"timeout": 30})


class TestAsyncContextManager:
    """Test async context manager support"""

    @pytest.mark.asyncio
    async def test_context_manager(self, temp_config_file):
        """Should work as async context manager"""
        async with OpenClawGatewayProxyService(config_path=temp_config_file) as service:
            # Mock the connection check to avoid real HTTP calls
            with patch.object(service, '_check_channel_connection', return_value=False):
                result = await service.list_channels()
                assert "channels" in result

        # HTTP client should be closed after exit
        assert service._http_client is None or service._http_client.is_closed
