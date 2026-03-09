"""
Tests for Zalo API Endpoints (Issue #121)

Tests the Zalo API endpoints including:
- OAuth URL generation
- OAuth callback handling
- OA connection/disconnection
- Webhook event processing
- Status checks
- Authentication and authorization

TDD RED Phase: These tests are written BEFORE implementation.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4
from fastapi import status
from httpx import AsyncClient

from backend.services.zalo_service import ZaloService, ZaloConfigurationError
from backend.integrations.zalo_client import ZaloAuthError


# Assuming the app is imported from main
@pytest.fixture
async def client():
    """Create test client"""
    from backend.main import app
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_zalo_service():
    """Mock Zalo service"""
    service = AsyncMock(spec=ZaloService)
    return service


@pytest.fixture
def auth_headers():
    """Mock authentication headers"""
    return {"Authorization": "Bearer test_token"}


class TestOAuthEndpoints:
    """Tests for OAuth endpoints"""

    @pytest.mark.asyncio
    async def test_get_oauth_authorize_url(self, client, auth_headers):
        """Test GET /api/v1/zalo/oauth/authorize returns OAuth URL"""
        with patch('backend.api.v1.endpoints.zalo.ZaloClient') as MockZaloClient:
            mock_client = Mock()
            mock_client.get_oauth_url = Mock(return_value="https://oauth.zaloapp.com/v4/oa/permission?app_id=123")
            MockZaloClient.return_value = mock_client

            response = await client.get(
                "/api/v1/zalo/oauth/authorize",
                headers=auth_headers,
                params={"redirect_uri": "https://example.com/callback"}
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "auth_url" in data
            assert "state" in data
            assert data["auth_url"].startswith("https://oauth.zaloapp.com")

    @pytest.mark.asyncio
    async def test_get_oauth_authorize_missing_redirect_uri(self, client, auth_headers):
        """Test OAuth authorize without redirect_uri returns 422"""
        response = await client.get(
            "/api/v1/zalo/oauth/authorize",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_get_oauth_authorize_unauthenticated(self, client):
        """Test OAuth authorize without authentication returns 401"""
        response = await client.get(
            "/api/v1/zalo/oauth/authorize",
            params={"redirect_uri": "https://example.com/callback"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_post_oauth_callback_success(self, client, auth_headers):
        """Test POST /api/v1/zalo/oauth/callback successfully exchanges code"""
        with patch('backend.api.v1.endpoints.zalo.ZaloClient') as MockZaloClient:
            mock_client = AsyncMock()
            mock_client.exchange_code_for_token = AsyncMock(return_value={
                "access_token": "access_token_abc",
                "refresh_token": "refresh_token_xyz",
                "expires_in": 7776000
            })
            MockZaloClient.return_value = mock_client

            response = await client.post(
                "/api/v1/zalo/oauth/callback",
                headers=auth_headers,
                json={
                    "code": "auth_code_123",
                    "state": "state_token"
                }
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["access_token"] == "access_token_abc"
            assert data["refresh_token"] == "refresh_token_xyz"

    @pytest.mark.asyncio
    async def test_post_oauth_callback_invalid_code(self, client, auth_headers):
        """Test OAuth callback with invalid code returns 400"""
        with patch('backend.api.v1.endpoints.zalo.ZaloClient') as MockZaloClient:
            mock_client = AsyncMock()
            mock_client.exchange_code_for_token = AsyncMock(side_effect=ZaloAuthError("Invalid code"))
            MockZaloClient.return_value = mock_client

            response = await client.post(
                "/api/v1/zalo/oauth/callback",
                headers=auth_headers,
                json={
                    "code": "invalid_code",
                    "state": "state_token"
                }
            )

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Invalid code" in response.json()["detail"]


class TestConnectionEndpoints:
    """Tests for OA connection endpoints"""

    @pytest.mark.asyncio
    async def test_post_connect_oa_success(self, client, auth_headers, mock_zalo_service):
        """Test POST /api/v1/zalo/connect successfully connects OA"""
        workspace_id = uuid4()

        mock_zalo_service.connect_oa = AsyncMock(return_value={
            "status": "connected",
            "oa_id": "1234567890",
            "oa_info": {"name": "My OA"}
        })

        with patch('backend.api.v1.endpoints.zalo.get_zalo_service', return_value=mock_zalo_service):
            response = await client.post(
                "/api/v1/zalo/connect",
                headers=auth_headers,
                json={
                    "workspace_id": str(workspace_id),
                    "oa_id": "1234567890",
                    "app_id": "app_123",
                    "app_secret": "secret_456",
                    "access_token": "token_abc",
                    "refresh_token": "refresh_xyz"
                }
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "connected"
            assert data["oa_id"] == "1234567890"

    @pytest.mark.asyncio
    async def test_post_connect_oa_missing_fields(self, client, auth_headers):
        """Test connecting OA with missing fields returns 422"""
        response = await client.post(
            "/api/v1/zalo/connect",
            headers=auth_headers,
            json={
                "workspace_id": str(uuid4()),
                "oa_id": "123"
                # Missing app_id, app_secret, etc.
            }
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_post_connect_oa_configuration_error(self, client, auth_headers, mock_zalo_service):
        """Test connecting OA with configuration error returns 400"""
        mock_zalo_service.connect_oa = AsyncMock(side_effect=ZaloConfigurationError("Invalid config"))

        with patch('backend.api.v1.endpoints.zalo.get_zalo_service', return_value=mock_zalo_service):
            response = await client.post(
                "/api/v1/zalo/connect",
                headers=auth_headers,
                json={
                    "workspace_id": str(uuid4()),
                    "oa_id": "123",
                    "app_id": "app",
                    "app_secret": "secret",
                    "access_token": "token",
                    "refresh_token": "refresh"
                }
            )

            assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_delete_disconnect_oa_success(self, client, auth_headers, mock_zalo_service):
        """Test DELETE /api/v1/zalo/disconnect successfully disconnects OA"""
        workspace_id = uuid4()

        mock_zalo_service.disconnect_oa = AsyncMock(return_value={
            "status": "disconnected"
        })

        with patch('backend.api.v1.endpoints.zalo.get_zalo_service', return_value=mock_zalo_service):
            response = await client.delete(
                f"/api/v1/zalo/disconnect?workspace_id={workspace_id}",
                headers=auth_headers
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "disconnected"

    @pytest.mark.asyncio
    async def test_delete_disconnect_oa_not_connected(self, client, auth_headers, mock_zalo_service):
        """Test disconnecting when not connected returns 404"""
        workspace_id = uuid4()

        mock_zalo_service.disconnect_oa = AsyncMock(side_effect=ZaloConfigurationError("Not connected"))

        with patch('backend.api.v1.endpoints.zalo.get_zalo_service', return_value=mock_zalo_service):
            response = await client.delete(
                f"/api/v1/zalo/disconnect?workspace_id={workspace_id}",
                headers=auth_headers
            )

            assert response.status_code == status.HTTP_404_NOT_FOUND


class TestWebhookEndpoint:
    """Tests for webhook endpoint"""

    @pytest.mark.asyncio
    async def test_post_webhook_text_message(self, client, mock_zalo_service):
        """Test POST /api/v1/zalo/webhook processes text message"""
        workspace_id = uuid4()

        mock_zalo_service.process_webhook = AsyncMock(return_value={
            "status": "processed",
            "conversation_id": str(uuid4())
        })

        with patch('backend.api.v1.endpoints.zalo.get_zalo_service', return_value=mock_zalo_service):
            with patch('backend.api.v1.endpoints.zalo.ZaloClient') as MockZaloClient:
                mock_client = Mock()
                mock_client.handle_webhook = Mock(return_value={
                    "event_type": "user_send_text",
                    "user_id": "user_123",
                    "message_text": "Hello",
                    "timestamp": 1234567890
                })
                mock_client.verify_webhook_signature = Mock(return_value=True)
                MockZaloClient.return_value = mock_client

                response = await client.post(
                    f"/api/v1/zalo/webhook?workspace_id={workspace_id}",
                    json={
                        "event_name": "user_send_text",
                        "timestamp": 1234567890,
                        "app_id": "app_123",
                        "user_id": "user_123",
                        "message": {
                            "text": "Hello"
                        }
                    },
                    headers={"X-Zalo-Signature": "valid_signature"}
                )

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["status"] == "processed"

    @pytest.mark.asyncio
    async def test_post_webhook_invalid_signature(self, client):
        """Test webhook with invalid signature returns 401"""
        workspace_id = uuid4()

        with patch('backend.api.v1.endpoints.zalo.ZaloClient') as MockZaloClient:
            mock_client = Mock()
            mock_client.verify_webhook_signature = Mock(return_value=False)
            MockZaloClient.return_value = mock_client

            response = await client.post(
                f"/api/v1/zalo/webhook?workspace_id={workspace_id}",
                json={
                    "event_name": "user_send_text",
                    "user_id": "user_123"
                },
                headers={"X-Zalo-Signature": "invalid_signature"}
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_post_webhook_missing_signature(self, client):
        """Test webhook without signature header returns 400"""
        workspace_id = uuid4()

        response = await client.post(
            f"/api/v1/zalo/webhook?workspace_id={workspace_id}",
            json={"event_name": "test"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_post_webhook_follow_event(self, client, mock_zalo_service):
        """Test webhook processes follow event"""
        workspace_id = uuid4()

        mock_zalo_service.process_webhook = AsyncMock(return_value={
            "status": "processed",
            "event_type": "follow"
        })

        with patch('backend.api.v1.endpoints.zalo.get_zalo_service', return_value=mock_zalo_service):
            with patch('backend.api.v1.endpoints.zalo.ZaloClient') as MockZaloClient:
                mock_client = Mock()
                mock_client.handle_webhook = Mock(return_value={
                    "event_type": "follow",
                    "user_id": "user_123",
                    "timestamp": 1234567890
                })
                mock_client.verify_webhook_signature = Mock(return_value=True)
                MockZaloClient.return_value = mock_client

                response = await client.post(
                    f"/api/v1/zalo/webhook?workspace_id={workspace_id}",
                    json={
                        "event_name": "follow",
                        "user_id": "user_123"
                    },
                    headers={"X-Zalo-Signature": "valid_signature"}
                )

                assert response.status_code == status.HTTP_200_OK


class TestStatusEndpoint:
    """Tests for status endpoint"""

    @pytest.mark.asyncio
    async def test_get_status_connected(self, client, auth_headers, mock_zalo_service):
        """Test GET /api/v1/zalo/status returns connected status"""
        workspace_id = uuid4()

        mock_zalo_service.get_oa_status = AsyncMock(return_value={
            "connected": True,
            "oa_id": "1234567890",
            "app_id": "app_123"
        })

        with patch('backend.api.v1.endpoints.zalo.get_zalo_service', return_value=mock_zalo_service):
            response = await client.get(
                f"/api/v1/zalo/status?workspace_id={workspace_id}",
                headers=auth_headers
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["connected"] is True
            assert data["oa_id"] == "1234567890"

    @pytest.mark.asyncio
    async def test_get_status_not_connected(self, client, auth_headers, mock_zalo_service):
        """Test status when not connected"""
        workspace_id = uuid4()

        mock_zalo_service.get_oa_status = AsyncMock(return_value={
            "connected": False,
            "oa_id": None
        })

        with patch('backend.api.v1.endpoints.zalo.get_zalo_service', return_value=mock_zalo_service):
            response = await client.get(
                f"/api/v1/zalo/status?workspace_id={workspace_id}",
                headers=auth_headers
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["connected"] is False
            assert data["oa_id"] is None

    @pytest.mark.asyncio
    async def test_get_status_missing_workspace_id(self, client, auth_headers):
        """Test status without workspace_id returns 422"""
        response = await client.get(
            "/api/v1/zalo/status",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestValidation:
    """Tests for input validation"""

    @pytest.mark.asyncio
    async def test_connect_invalid_workspace_id_format(self, client, auth_headers):
        """Test connecting with invalid UUID format"""
        response = await client.post(
            "/api/v1/zalo/connect",
            headers=auth_headers,
            json={
                "workspace_id": "not-a-uuid",
                "oa_id": "123",
                "app_id": "app",
                "app_secret": "secret",
                "access_token": "token",
                "refresh_token": "refresh"
            }
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_webhook_invalid_json(self, client):
        """Test webhook with invalid JSON returns 422"""
        workspace_id = uuid4()

        response = await client.post(
            f"/api/v1/zalo/webhook?workspace_id={workspace_id}",
            content="not valid json",
            headers={
                "Content-Type": "application/json",
                "X-Zalo-Signature": "signature"
            }
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestRateLimiting:
    """Tests for rate limiting (if implemented)"""

    @pytest.mark.asyncio
    async def test_webhook_rate_limit(self, client, mock_zalo_service):
        """Test webhook respects rate limiting"""
        # This test validates that rate limiting is considered in design
        # Actual implementation may use Redis or in-memory store
        workspace_id = uuid4()

        mock_zalo_service.process_webhook = AsyncMock(return_value={"status": "processed"})

        with patch('backend.api.v1.endpoints.zalo.get_zalo_service', return_value=mock_zalo_service):
            with patch('backend.api.v1.endpoints.zalo.ZaloClient') as MockZaloClient:
                mock_client = Mock()
                mock_client.handle_webhook = Mock(return_value={
                    "event_type": "user_send_text",
                    "user_id": "user_123",
                    "message_text": "Test",
                    "timestamp": 1234567890
                })
                mock_client.verify_webhook_signature = Mock(return_value=True)
                MockZaloClient.return_value = mock_client

                # Send multiple requests
                for _ in range(5):
                    response = await client.post(
                        f"/api/v1/zalo/webhook?workspace_id={workspace_id}",
                        json={"event_name": "user_send_text", "user_id": "123"},
                        headers={"X-Zalo-Signature": "valid"}
                    )
                    # Should all succeed (or fail at some threshold)
                    assert response.status_code in [200, 429]  # 429 = Too Many Requests


class TestErrorResponses:
    """Tests for error response formats"""

    @pytest.mark.asyncio
    async def test_error_response_format(self, client, auth_headers, mock_zalo_service):
        """Test error responses have consistent format"""
        workspace_id = uuid4()

        mock_zalo_service.connect_oa = AsyncMock(side_effect=ZaloConfigurationError("Test error"))

        with patch('backend.api.v1.endpoints.zalo.get_zalo_service', return_value=mock_zalo_service):
            response = await client.post(
                "/api/v1/zalo/connect",
                headers=auth_headers,
                json={
                    "workspace_id": str(workspace_id),
                    "oa_id": "123",
                    "app_id": "app",
                    "app_secret": "secret",
                    "access_token": "token",
                    "refresh_token": "refresh"
                }
            )

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            data = response.json()
            assert "detail" in data  # FastAPI standard error format
