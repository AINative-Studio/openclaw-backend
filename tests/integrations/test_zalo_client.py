"""
Tests for ZaloClient - Zalo API Integration (Issue #121)

Tests the Zalo Official Account API client implementation including:
- OAuth URL generation
- Token exchange and refresh
- Message sending (text and images)
- User profile retrieval
- Webhook payload handling
- Error handling

TDD RED Phase: These tests are written BEFORE implementation.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import httpx
from datetime import datetime, timezone, timedelta

from backend.integrations.zalo_client import (
    ZaloClient,
    ZaloAPIError,
    ZaloAuthError,
    ZaloRateLimitError,
    ZaloWebhookError
)


class TestZaloClientInit:
    """Tests for ZaloClient initialization"""

    def test_init_with_all_credentials(self):
        """Test initialization with all required credentials"""
        client = ZaloClient(
            oa_id="1234567890",
            app_id="app_123",
            app_secret="secret_456"
        )
        assert client.oa_id == "1234567890"
        assert client.app_id == "app_123"
        assert client.app_secret == "secret_456"
        assert client.base_url == "https://openapi.zalo.me"

    def test_init_missing_credentials_raises_error(self):
        """Test initialization fails with missing credentials"""
        with pytest.raises(ValueError, match="oa_id is required"):
            ZaloClient(oa_id="", app_id="app_123", app_secret="secret_456")

        with pytest.raises(ValueError, match="app_id is required"):
            ZaloClient(oa_id="123", app_id="", app_secret="secret_456")

        with pytest.raises(ValueError, match="app_secret is required"):
            ZaloClient(oa_id="123", app_id="app_123", app_secret="")


class TestZaloOAuth:
    """Tests for OAuth flow"""

    def test_get_oauth_url_returns_valid_url(self):
        """Test OAuth URL generation with state parameter"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")
        redirect_uri = "https://example.com/callback"
        state = "random_state_123"

        oauth_url = client.get_oauth_url(redirect_uri=redirect_uri, state=state)

        assert oauth_url.startswith("https://oauth.zaloapp.com/v4/oa/permission")
        assert f"app_id={client.app_id}" in oauth_url
        # URL encoding is expected for redirect_uri
        from urllib.parse import quote
        assert quote(redirect_uri, safe='') in oauth_url
        assert f"state={state}" in oauth_url

    def test_get_oauth_url_without_state_generates_one(self):
        """Test OAuth URL generation auto-generates state if not provided"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")
        oauth_url = client.get_oauth_url(redirect_uri="https://example.com/callback")

        assert "state=" in oauth_url
        # State should be present and non-empty
        state_param = [p for p in oauth_url.split("&") if p.startswith("state=")]
        assert len(state_param) == 1
        assert len(state_param[0].split("=")[1]) > 10  # Should be a random string

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_success(self):
        """Test successful token exchange"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")

        mock_response = {
            "access_token": "access_token_abc",
            "refresh_token": "refresh_token_xyz",
            "expires_in": 7776000  # 90 days
        }

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.exchange_code_for_token(code="auth_code_123")

            assert result["access_token"] == "access_token_abc"
            assert result["refresh_token"] == "refresh_token_xyz"
            assert result["expires_in"] == 7776000
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_invalid_code(self):
        """Test token exchange with invalid code raises error"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = ZaloAuthError("Invalid authorization code")

            with pytest.raises(ZaloAuthError, match="Invalid authorization code"):
                await client.exchange_code_for_token(code="invalid_code")

    @pytest.mark.asyncio
    async def test_refresh_access_token_success(self):
        """Test successful token refresh"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")

        mock_response = {
            "access_token": "new_access_token_abc",
            "refresh_token": "new_refresh_token_xyz",
            "expires_in": 7776000
        }

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.refresh_access_token(refresh_token="old_refresh_token")

            assert result["access_token"] == "new_access_token_abc"
            assert result["refresh_token"] == "new_refresh_token_xyz"
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_access_token_invalid_refresh_token(self):
        """Test token refresh with invalid refresh token"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = ZaloAuthError("Invalid refresh token")

            with pytest.raises(ZaloAuthError, match="Invalid refresh token"):
                await client.refresh_access_token(refresh_token="invalid_token")


class TestZaloMessaging:
    """Tests for message sending"""

    @pytest.mark.asyncio
    async def test_send_text_message_success(self):
        """Test sending text message successfully"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")
        client.access_token = "valid_access_token"

        mock_response = {
            "error": 0,
            "message": "Success",
            "data": {
                "message_id": "msg_12345"
            }
        }

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.send_text_message(
                user_id="user_123",
                message="Hello from OpenClaw"
            )

            assert result["data"]["message_id"] == "msg_12345"
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_text_message_without_access_token(self):
        """Test sending message without access token raises error"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")

        with pytest.raises(ZaloAuthError, match="Access token not set"):
            await client.send_text_message(user_id="user_123", message="Hello")

    @pytest.mark.asyncio
    async def test_send_text_message_empty_message(self):
        """Test sending empty message raises validation error"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")
        client.access_token = "valid_token"

        with pytest.raises(ValueError, match="Message cannot be empty"):
            await client.send_text_message(user_id="user_123", message="")

    @pytest.mark.asyncio
    async def test_send_image_message_success(self):
        """Test sending image message successfully"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")
        client.access_token = "valid_access_token"

        mock_response = {
            "error": 0,
            "message": "Success",
            "data": {
                "message_id": "msg_image_123"
            }
        }

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.send_image_message(
                user_id="user_123",
                image_url="https://example.com/image.jpg"
            )

            assert result["data"]["message_id"] == "msg_image_123"
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_image_message_invalid_url(self):
        """Test sending image with invalid URL raises error"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")
        client.access_token = "valid_token"

        with pytest.raises(ValueError, match="Invalid image URL"):
            await client.send_image_message(user_id="user_123", image_url="not-a-url")


class TestZaloUserProfile:
    """Tests for user profile retrieval"""

    @pytest.mark.asyncio
    async def test_get_user_profile_success(self):
        """Test getting user profile successfully"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")
        client.access_token = "valid_access_token"

        mock_response = {
            "error": 0,
            "message": "Success",
            "data": {
                "user_id": "user_123",
                "display_name": "John Doe",
                "avatar": "https://avatar.url/image.jpg"
            }
        }

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.get_user_profile(user_id="user_123")

            assert result["data"]["user_id"] == "user_123"
            assert result["data"]["display_name"] == "John Doe"
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_profile_user_not_found(self):
        """Test getting profile for non-existent user"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")
        client.access_token = "valid_token"

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = ZaloAPIError("User not found", error_code=-124)

            with pytest.raises(ZaloAPIError, match="User not found"):
                await client.get_user_profile(user_id="nonexistent_user")


class TestZaloWebhooks:
    """Tests for webhook handling"""

    def test_handle_webhook_text_message(self):
        """Test handling incoming text message webhook"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")

        payload = {
            "event_name": "user_send_text",
            "timestamp": 1234567890,
            "app_id": "app_123",
            "user_id": "user_123",
            "message": {
                "text": "Hello from user"
            }
        }

        result = client.handle_webhook(payload)

        assert result["event_type"] == "user_send_text"
        assert result["user_id"] == "user_123"
        assert result["message_text"] == "Hello from user"
        assert result["timestamp"] == 1234567890

    def test_handle_webhook_follow_event(self):
        """Test handling user follow webhook"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")

        payload = {
            "event_name": "follow",
            "timestamp": 1234567890,
            "app_id": "app_123",
            "user_id": "user_123"
        }

        result = client.handle_webhook(payload)

        assert result["event_type"] == "follow"
        assert result["user_id"] == "user_123"

    def test_handle_webhook_unfollow_event(self):
        """Test handling user unfollow webhook"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")

        payload = {
            "event_name": "unfollow",
            "timestamp": 1234567890,
            "app_id": "app_123",
            "user_id": "user_123"
        }

        result = client.handle_webhook(payload)

        assert result["event_type"] == "unfollow"
        assert result["user_id"] == "user_123"

    def test_handle_webhook_invalid_payload(self):
        """Test handling webhook with invalid payload"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")

        with pytest.raises(ZaloWebhookError, match="Invalid webhook payload"):
            client.handle_webhook({})

    def test_handle_webhook_missing_required_fields(self):
        """Test handling webhook with missing required fields"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")

        payload = {
            "event_name": "user_send_text",
            # Missing timestamp, app_id, user_id
        }

        with pytest.raises(ZaloWebhookError, match="Missing required fields"):
            client.handle_webhook(payload)


class TestZaloErrorHandling:
    """Tests for error handling"""

    @pytest.mark.asyncio
    async def test_api_error_rate_limit(self):
        """Test handling rate limit error"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")
        client.access_token = "valid_token"

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = ZaloRateLimitError(
                "Rate limit exceeded",
                retry_after=60
            )

            with pytest.raises(ZaloRateLimitError) as exc_info:
                await client.send_text_message(user_id="user_123", message="Hello")

            assert exc_info.value.retry_after == 60

    @pytest.mark.asyncio
    async def test_api_error_network_failure(self):
        """Test handling network failure"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")
        client.access_token = "valid_token"

        with patch('backend.integrations.zalo_client.httpx.AsyncClient') as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
            MockClient.return_value.__aenter__.return_value = mock_client_instance

            with pytest.raises(ZaloAPIError, match="Network error"):
                await client.send_text_message(user_id="user_123", message="Hello")

    @pytest.mark.asyncio
    async def test_api_error_timeout(self):
        """Test handling request timeout"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")
        client.access_token = "valid_token"

        with patch('backend.integrations.zalo_client.httpx.AsyncClient') as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request = AsyncMock(side_effect=httpx.TimeoutException("Request timeout"))
            MockClient.return_value.__aenter__.return_value = mock_client_instance

            with pytest.raises(ZaloAPIError, match="Request timeout"):
                await client.send_text_message(user_id="user_123", message="Hello")

    @pytest.mark.asyncio
    async def test_api_error_invalid_response_format(self):
        """Test handling invalid API response format"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")
        client.access_token = "valid_token"

        with patch('backend.integrations.zalo_client.httpx.AsyncClient') as MockClient:
            mock_response = Mock()
            mock_response.json = Mock(return_value="not a dict")  # Returns non-dict
            mock_response.raise_for_status = Mock()

            mock_client_instance = AsyncMock()
            mock_client_instance.request = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__.return_value = mock_client_instance

            with pytest.raises(ZaloAPIError, match="Invalid response format"):
                await client.send_text_message(user_id="user_123", message="Hello")


class TestZaloClientHelpers:
    """Tests for helper methods"""

    def test_verify_webhook_signature_valid(self):
        """Test webhook signature verification with valid signature"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")

        payload = '{"event_name":"user_send_text","user_id":"123"}'
        # This would be a real HMAC-SHA256 signature in production
        signature = client._compute_signature(payload)

        assert client.verify_webhook_signature(payload, signature) is True

    def test_verify_webhook_signature_invalid(self):
        """Test webhook signature verification with invalid signature"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")

        payload = '{"event_name":"user_send_text","user_id":"123"}'
        invalid_signature = "invalid_signature_hash"

        assert client.verify_webhook_signature(payload, invalid_signature) is False

    def test_compute_signature_consistent(self):
        """Test signature computation is consistent"""
        client = ZaloClient(oa_id="123", app_id="app_123", app_secret="secret")

        payload = '{"test":"data"}'
        sig1 = client._compute_signature(payload)
        sig2 = client._compute_signature(payload)

        assert sig1 == sig2
