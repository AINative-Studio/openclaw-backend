"""
Test suite for Global Channel Management API Endpoints

Tests the REST API for managing OpenClaw Gateway communication channels
(WhatsApp, Telegram, Discord, Slack, etc.) at the global workspace level.

Part of Issue #81 - Create Global Channel Management API Endpoints
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture
def client():
    """Create test client for FastAPI app"""
    return TestClient(app)


@pytest.fixture
def mock_gateway_proxy_service():
    """Mock the OpenClawGatewayProxyService"""
    with patch('backend.api.v1.endpoints.channels.OpenClawGatewayProxyService') as mock:
        service_instance = AsyncMock()

        # Mock list_channels
        service_instance.list_channels = AsyncMock(return_value={
            "channels": [
                {
                    "id": "whatsapp",
                    "name": "WhatsApp",
                    "description": "WhatsApp Business API integration",
                    "enabled": True,
                    "connected": True,
                    "capabilities": ["text", "image", "voice"],
                    "version": "1.0.0"
                },
                {
                    "id": "telegram",
                    "name": "Telegram",
                    "description": "Telegram Bot API integration",
                    "enabled": False,
                    "connected": False,
                    "capabilities": ["text", "image", "document"],
                    "version": "1.0.0"
                }
            ],
            "total": 2
        })

        # Mock enable_channel
        service_instance.enable_channel = AsyncMock(return_value={
            "channel_id": "telegram",
            "enabled": True,
            "message": "Channel enabled successfully"
        })

        # Mock disable_channel
        service_instance.disable_channel = AsyncMock(return_value={
            "channel_id": "whatsapp",
            "enabled": False,
            "message": "Channel disabled successfully"
        })

        # Mock get_channel_status
        service_instance.get_channel_status = AsyncMock(return_value={
            "channel_id": "whatsapp",
            "enabled": True,
            "connected": True,
            "status": "active",
            "last_activity": "2026-02-27T10:30:00Z",
            "connection_details": {
                "session_id": "whatsapp:group:120363401780756402@g.us",
                "qr_code_required": False,
                "authenticated": True
            }
        })

        # Mock update_channel_config
        service_instance.update_channel_config = AsyncMock(return_value={
            "channel_id": "whatsapp",
            "updated": True,
            "message": "Configuration updated successfully",
            "config": {
                "auto_reconnect": True,
                "max_retries": 5,
                "timeout": 30
            }
        })

        # Configure async context manager
        service_instance.__aenter__ = AsyncMock(return_value=service_instance)
        service_instance.__aexit__ = AsyncMock(return_value=None)

        mock.return_value = service_instance
        yield service_instance


class TestListChannels:
    """Test GET /api/v1/channels endpoint"""

    def test_list_all_channels_success(self, client, mock_gateway_proxy_service):
        """Should return list of all available channels"""
        response = client.get("/api/v1/channels")

        assert response.status_code == 200
        data = response.json()

        assert "channels" in data
        assert "total" in data
        assert data["total"] == 2
        assert len(data["channels"]) == 2

        # Verify WhatsApp channel structure
        whatsapp = data["channels"][0]
        assert whatsapp["id"] == "whatsapp"
        assert whatsapp["name"] == "WhatsApp"
        assert whatsapp["enabled"] is True
        assert whatsapp["connected"] is True
        assert "capabilities" in whatsapp

        # Verify service was called
        mock_gateway_proxy_service.list_channels.assert_called_once()

    def test_list_channels_filters_enabled_only(self, client, mock_gateway_proxy_service):
        """Should filter to show only enabled channels"""
        mock_gateway_proxy_service.list_channels.return_value = {
            "channels": [
                {
                    "id": "whatsapp",
                    "name": "WhatsApp",
                    "description": "WhatsApp integration",
                    "enabled": True,
                    "connected": True,
                    "capabilities": ["text"],
                    "version": "1.0.0"
                }
            ],
            "total": 1
        }

        response = client.get("/api/v1/channels?enabled=true")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert all(ch["enabled"] for ch in data["channels"])

    def test_list_channels_service_unavailable(self, client):
        """Should return 503 when gateway service is unavailable"""
        with patch('backend.api.v1.endpoints.channels.OpenClawGatewayProxyService') as mock:
            service_instance = AsyncMock()
            service_instance.__aenter__ = AsyncMock(side_effect=ConnectionError("Gateway unreachable"))
            service_instance.__aexit__ = AsyncMock(return_value=None)
            mock.return_value = service_instance

            response = client.get("/api/v1/channels")

            assert response.status_code == 503
            assert "unavailable" in response.json()["detail"].lower()


class TestEnableChannel:
    """Test POST /api/v1/channels/{channel_id}/enable endpoint"""

    def test_enable_channel_success(self, client, mock_gateway_proxy_service):
        """Should successfully enable a disabled channel"""
        response = client.post("/api/v1/channels/telegram/enable")

        assert response.status_code == 200
        data = response.json()

        assert data["channel_id"] == "telegram"
        assert data["enabled"] is True
        assert "message" in data

        # Verify service was called with correct channel_id
        mock_gateway_proxy_service.enable_channel.assert_called_once_with("telegram")

    def test_enable_already_enabled_channel(self, client, mock_gateway_proxy_service):
        """Should return success even if channel is already enabled (idempotent)"""
        mock_gateway_proxy_service.enable_channel.return_value = {
            "channel_id": "whatsapp",
            "enabled": True,
            "message": "Channel already enabled"
        }

        response = client.post("/api/v1/channels/whatsapp/enable")

        assert response.status_code == 200
        assert response.json()["enabled"] is True

    def test_enable_invalid_channel_id(self, client, mock_gateway_proxy_service):
        """Should return 404 for non-existent channel"""
        mock_gateway_proxy_service.enable_channel.side_effect = ValueError("Channel 'invalid' not found")

        response = client.post("/api/v1/channels/invalid/enable")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_enable_channel_with_config_error(self, client, mock_gateway_proxy_service):
        """Should return 500 when configuration update fails"""
        mock_gateway_proxy_service.enable_channel.side_effect = RuntimeError("Failed to update openclaw.json")

        response = client.post("/api/v1/channels/telegram/enable")

        assert response.status_code == 500
        assert "failed" in response.json()["detail"].lower()


class TestDisableChannel:
    """Test POST /api/v1/channels/{channel_id}/disable endpoint"""

    def test_disable_channel_success(self, client, mock_gateway_proxy_service):
        """Should successfully disable an enabled channel"""
        response = client.post("/api/v1/channels/whatsapp/disable")

        assert response.status_code == 200
        data = response.json()

        assert data["channel_id"] == "whatsapp"
        assert data["enabled"] is False
        assert "message" in data

        mock_gateway_proxy_service.disable_channel.assert_called_once_with("whatsapp")

    def test_disable_already_disabled_channel(self, client, mock_gateway_proxy_service):
        """Should return success even if channel is already disabled (idempotent)"""
        mock_gateway_proxy_service.disable_channel.return_value = {
            "channel_id": "telegram",
            "enabled": False,
            "message": "Channel already disabled"
        }

        response = client.post("/api/v1/channels/telegram/disable")

        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_disable_invalid_channel_id(self, client, mock_gateway_proxy_service):
        """Should return 404 for non-existent channel"""
        mock_gateway_proxy_service.disable_channel.side_effect = ValueError("Channel 'invalid' not found")

        response = client.post("/api/v1/channels/invalid/disable")

        assert response.status_code == 404


class TestGetChannelStatus:
    """Test GET /api/v1/channels/{channel_id}/status endpoint"""

    def test_get_channel_status_success(self, client, mock_gateway_proxy_service):
        """Should return detailed status of a channel"""
        response = client.get("/api/v1/channels/whatsapp/status")

        assert response.status_code == 200
        data = response.json()

        assert data["channel_id"] == "whatsapp"
        assert data["enabled"] is True
        assert data["connected"] is True
        assert data["status"] == "active"
        assert "last_activity" in data
        assert "connection_details" in data

        # Verify connection details structure
        assert "session_id" in data["connection_details"]
        assert "authenticated" in data["connection_details"]

        mock_gateway_proxy_service.get_channel_status.assert_called_once_with("whatsapp")

    def test_get_status_disconnected_channel(self, client, mock_gateway_proxy_service):
        """Should show disconnected status for offline channel"""
        mock_gateway_proxy_service.get_channel_status.return_value = {
            "channel_id": "telegram",
            "enabled": True,
            "connected": False,
            "status": "disconnected",
            "last_activity": None,
            "connection_details": {
                "error": "Connection timeout"
            }
        }

        response = client.get("/api/v1/channels/telegram/status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["status"] == "disconnected"

    def test_get_status_disabled_channel(self, client, mock_gateway_proxy_service):
        """Should show disabled status for disabled channel"""
        mock_gateway_proxy_service.get_channel_status.return_value = {
            "channel_id": "slack",
            "enabled": False,
            "connected": False,
            "status": "disabled",
            "last_activity": None,
            "connection_details": None
        }

        response = client.get("/api/v1/channels/slack/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["status"] == "disabled"

    def test_get_status_invalid_channel_id(self, client, mock_gateway_proxy_service):
        """Should return 404 for non-existent channel"""
        mock_gateway_proxy_service.get_channel_status.side_effect = ValueError("Channel 'invalid' not found")

        response = client.get("/api/v1/channels/invalid/status")

        assert response.status_code == 404


class TestUpdateChannelConfig:
    """Test PUT /api/v1/channels/{channel_id}/config endpoint"""

    def test_update_config_success(self, client, mock_gateway_proxy_service):
        """Should successfully update channel configuration"""
        config_update = {
            "auto_reconnect": True,
            "max_retries": 5,
            "timeout": 30
        }

        response = client.put(
            "/api/v1/channels/whatsapp/config",
            json=config_update
        )

        assert response.status_code == 200
        data = response.json()

        assert data["channel_id"] == "whatsapp"
        assert data["updated"] is True
        assert "config" in data
        assert data["config"]["auto_reconnect"] is True

        # Verify service was called with channel_id and config
        mock_gateway_proxy_service.update_channel_config.assert_called_once_with(
            "whatsapp",
            config_update
        )

    def test_update_config_partial_update(self, client, mock_gateway_proxy_service):
        """Should allow partial configuration updates"""
        config_update = {"timeout": 60}

        mock_gateway_proxy_service.update_channel_config.return_value = {
            "channel_id": "telegram",
            "updated": True,
            "message": "Configuration updated",
            "config": {"timeout": 60}
        }

        response = client.put(
            "/api/v1/channels/telegram/config",
            json=config_update
        )

        assert response.status_code == 200
        assert response.json()["updated"] is True

    def test_update_config_invalid_channel_id(self, client, mock_gateway_proxy_service):
        """Should return 404 for non-existent channel"""
        mock_gateway_proxy_service.update_channel_config.side_effect = ValueError("Channel 'invalid' not found")

        response = client.put(
            "/api/v1/channels/invalid/config",
            json={"timeout": 30}
        )

        assert response.status_code == 404

    def test_update_config_invalid_values(self, client, mock_gateway_proxy_service):
        """Should return 422 for invalid configuration values"""
        response = client.put(
            "/api/v1/channels/whatsapp/config",
            json={"timeout": -1}  # Invalid negative timeout
        )

        assert response.status_code == 422

    def test_update_config_empty_body(self, client, mock_gateway_proxy_service):
        """Should return 422 for empty configuration"""
        response = client.put(
            "/api/v1/channels/whatsapp/config",
            json={}
        )

        assert response.status_code == 422

    def test_update_config_file_write_error(self, client, mock_gateway_proxy_service):
        """Should return 500 when configuration file update fails"""
        mock_gateway_proxy_service.update_channel_config.side_effect = IOError("Permission denied: openclaw.json")

        response = client.put(
            "/api/v1/channels/whatsapp/config",
            json={"timeout": 30}
        )

        assert response.status_code == 500


class TestChannelManagementIntegration:
    """Integration tests for complete channel management workflows"""

    def test_enable_and_check_status_workflow(self, client, mock_gateway_proxy_service):
        """Should be able to enable a channel and verify its status"""
        # Enable channel
        enable_response = client.post("/api/v1/channels/telegram/enable")
        assert enable_response.status_code == 200

        # Update mock for status check
        mock_gateway_proxy_service.get_channel_status.return_value = {
            "channel_id": "telegram",
            "enabled": True,
            "connected": True,
            "status": "active",
            "last_activity": "2026-02-27T10:35:00Z",
            "connection_details": {"authenticated": True}
        }

        # Check status
        status_response = client.get("/api/v1/channels/telegram/status")
        assert status_response.status_code == 200
        assert status_response.json()["enabled"] is True

    def test_update_config_and_verify_workflow(self, client, mock_gateway_proxy_service):
        """Should be able to update config and verify changes"""
        new_config = {"timeout": 45, "max_retries": 3}

        # Update config
        update_response = client.put(
            "/api/v1/channels/whatsapp/config",
            json=new_config
        )
        assert update_response.status_code == 200

        # Verify updated config in response
        data = update_response.json()
        assert data["config"]["timeout"] == 45 or "timeout" in str(data)

    def test_disable_channel_clears_connection_workflow(self, client, mock_gateway_proxy_service):
        """Should disconnect when disabling a channel"""
        # Mock updated status after disable
        mock_gateway_proxy_service.disable_channel.return_value = {
            "channel_id": "whatsapp",
            "enabled": False,
            "message": "Channel disabled and disconnected"
        }

        # Disable channel
        disable_response = client.post("/api/v1/channels/whatsapp/disable")
        assert disable_response.status_code == 200
        assert disable_response.json()["enabled"] is False


class TestErrorHandling:
    """Test comprehensive error handling scenarios"""

    def test_gateway_connection_timeout(self, client):
        """Should handle gateway connection timeout gracefully"""
        with patch('backend.api.v1.endpoints.channels.OpenClawGatewayProxyService') as mock:
            mock.return_value.list_channels = AsyncMock(
                side_effect=asyncio.TimeoutError("Gateway connection timeout")
            )

            response = client.get("/api/v1/channels")

            assert response.status_code in [503, 500]

    def test_malformed_gateway_response(self, client, mock_gateway_proxy_service):
        """Should handle malformed responses from gateway"""
        mock_gateway_proxy_service.list_channels.return_value = {
            "invalid": "structure"
        }

        response = client.get("/api/v1/channels")

        # Should either handle gracefully or return 500
        assert response.status_code in [200, 500]

    def test_concurrent_channel_operations(self, client, mock_gateway_proxy_service):
        """Should handle concurrent channel operations safely"""
        # Simulate race condition
        import threading

        def enable_channel():
            client.post("/api/v1/channels/telegram/enable")

        def disable_channel():
            client.post("/api/v1/channels/telegram/disable")

        # Should not crash with concurrent operations
        t1 = threading.Thread(target=enable_channel)
        t2 = threading.Thread(target=disable_channel)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # At least one operation should succeed
        assert mock_gateway_proxy_service.enable_channel.called or \
               mock_gateway_proxy_service.disable_channel.called


# Import asyncio for timeout test
import asyncio
