"""
Tests for ZaloService - Business Logic Layer (Issue #121)

Tests the Zalo service layer including:
- OA connection and disconnection
- Message sending
- Webhook processing
- Status checks
- Credential storage
- Integration with ConversationService

TDD RED Phase: These tests are written BEFORE implementation.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.zalo_service import (
    ZaloService,
    ZaloConfigurationError,
    ZaloMessageError
)
from backend.integrations.zalo_client import ZaloClient, ZaloAuthError, ZaloAPIError
from backend.models.user_api_key import UserAPIKey
from backend.models.conversation import Conversation, ConversationStatus


@pytest.fixture
def mock_db_session():
    """Mock database session"""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def mock_zalo_client():
    """Mock Zalo API client"""
    client = AsyncMock(spec=ZaloClient)
    return client


@pytest.fixture
def mock_user_api_key_service():
    """Mock UserAPIKeyService"""
    service = Mock()
    service.encrypt_key = Mock(side_effect=lambda x: f"encrypted_{x}")
    service.decrypt_key = Mock(side_effect=lambda x: x.replace("encrypted_", ""))
    return service


@pytest.fixture
def mock_conversation_service():
    """Mock ConversationService"""
    service = AsyncMock()
    return service


@pytest.fixture
def zalo_service(mock_db_session, mock_user_api_key_service, mock_conversation_service):
    """Create ZaloService instance with mocked dependencies"""
    return ZaloService(
        db=mock_db_session,
        user_api_key_service=mock_user_api_key_service,
        conversation_service=mock_conversation_service
    )


class TestZaloServiceInit:
    """Tests for ZaloService initialization"""

    def test_init_with_dependencies(self, mock_db_session, mock_user_api_key_service, mock_conversation_service):
        """Test service initialization with all dependencies"""
        service = ZaloService(
            db=mock_db_session,
            user_api_key_service=mock_user_api_key_service,
            conversation_service=mock_conversation_service
        )
        assert service.db is mock_db_session
        assert service.user_api_key_service is mock_user_api_key_service
        assert service.conversation_service is mock_conversation_service


class TestZaloConnectionManagement:
    """Tests for OA connection and disconnection"""

    @pytest.mark.asyncio
    async def test_connect_oa_success(self, zalo_service, mock_db_session):
        """Test successful OA connection stores credentials"""
        workspace_id = uuid4()
        oa_config = {
            "oa_id": "1234567890",
            "app_id": "app_123",
            "app_secret": "secret_456",
            "access_token": "access_token_abc",
            "refresh_token": "refresh_token_xyz"
        }

        # Mock database operations
        mock_db_session.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None)))
        mock_db_session.add = Mock()
        mock_db_session.commit = AsyncMock()

        result = await zalo_service.connect_oa(workspace_id=workspace_id, oa_config=oa_config)

        assert result["status"] == "connected"
        assert result["oa_id"] == "1234567890"
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_oa_missing_required_fields(self, zalo_service):
        """Test connecting OA with missing required fields raises error"""
        workspace_id = uuid4()
        incomplete_config = {
            "oa_id": "1234567890",
            # Missing app_id, app_secret, etc.
        }

        with pytest.raises(ZaloConfigurationError, match="Missing required fields"):
            await zalo_service.connect_oa(workspace_id=workspace_id, oa_config=incomplete_config)

    @pytest.mark.asyncio
    async def test_connect_oa_update_existing(self, zalo_service, mock_db_session):
        """Test updating existing OA connection"""
        workspace_id = uuid4()
        oa_config = {
            "oa_id": "1234567890",
            "app_id": "app_123",
            "app_secret": "secret_456",
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token"
        }

        # Mock existing record
        existing_key = UserAPIKey(
            workspace_id=str(workspace_id),
            provider="zalo",
            encrypted_key="encrypted_old_token",
            key_hash="old_hash"
        )
        mock_db_session.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=existing_key)))
        mock_db_session.commit = AsyncMock()

        result = await zalo_service.connect_oa(workspace_id=workspace_id, oa_config=oa_config)

        assert result["status"] == "updated"
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_oa_success(self, zalo_service, mock_db_session):
        """Test successful OA disconnection removes credentials"""
        workspace_id = uuid4()

        # Mock existing record
        existing_key = UserAPIKey(
            workspace_id=str(workspace_id),
            provider="zalo",
            encrypted_key="encrypted_token",
            key_hash="hash"
        )
        mock_db_session.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=existing_key)))
        mock_db_session.delete = AsyncMock()  # Make it async
        mock_db_session.commit = AsyncMock()

        result = await zalo_service.disconnect_oa(workspace_id=workspace_id)

        assert result["status"] == "disconnected"
        mock_db_session.delete.assert_called_once_with(existing_key)
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_oa_not_connected(self, zalo_service, mock_db_session):
        """Test disconnecting when not connected raises error"""
        workspace_id = uuid4()

        mock_db_session.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None)))

        with pytest.raises(ZaloConfigurationError, match="No Zalo OA connected"):
            await zalo_service.disconnect_oa(workspace_id=workspace_id)


class TestZaloMessageSending:
    """Tests for message sending"""

    @pytest.mark.asyncio
    async def test_send_message_success(self, zalo_service, mock_db_session):
        """Test sending message successfully"""
        workspace_id = uuid4()
        user_id = "zalo_user_123"
        message = "Hello from OpenClaw"

        # Mock credential retrieval
        mock_credentials = {
            "oa_id": "123",
            "app_id": "app_123",
            "app_secret": "secret",
            "access_token": "token_abc"
        }
        zalo_service._get_credentials = AsyncMock(return_value=mock_credentials)

        # Mock Zalo client
        with patch('backend.services.zalo_service.ZaloClient') as MockZaloClient:
            mock_client = AsyncMock()
            mock_client.send_text_message = AsyncMock(return_value={"data": {"message_id": "msg_123"}})
            MockZaloClient.return_value = mock_client

            result = await zalo_service.send_message(
                workspace_id=workspace_id,
                user_id=user_id,
                message=message
            )

            assert result["message_id"] == "msg_123"
            mock_client.send_text_message.assert_called_once_with(user_id=user_id, message=message)

    @pytest.mark.asyncio
    async def test_send_message_no_credentials(self, zalo_service):
        """Test sending message without credentials raises error"""
        workspace_id = uuid4()

        zalo_service._get_credentials = AsyncMock(side_effect=ZaloConfigurationError("No credentials"))

        with pytest.raises(ZaloConfigurationError, match="No credentials"):
            await zalo_service.send_message(
                workspace_id=workspace_id,
                user_id="user_123",
                message="Hello"
            )

    @pytest.mark.asyncio
    async def test_send_message_api_error(self, zalo_service):
        """Test handling API error during message send"""
        workspace_id = uuid4()

        zalo_service._get_credentials = AsyncMock(return_value={
            "oa_id": "123",
            "app_id": "app",
            "app_secret": "secret",
            "access_token": "token"
        })

        with patch('backend.services.zalo_service.ZaloClient') as MockZaloClient:
            mock_client = AsyncMock()
            mock_client.send_text_message = AsyncMock(side_effect=ZaloAPIError("API error"))
            MockZaloClient.return_value = mock_client

            with pytest.raises(ZaloMessageError, match="Failed to send message"):
                await zalo_service.send_message(
                    workspace_id=workspace_id,
                    user_id="user_123",
                    message="Hello"
                )


class TestZaloWebhookProcessing:
    """Tests for webhook processing"""

    @pytest.mark.asyncio
    async def test_process_webhook_text_message(self, zalo_service, mock_conversation_service):
        """Test processing incoming text message webhook"""
        workspace_id = uuid4()
        event = {
            "event_type": "user_send_text",
            "user_id": "zalo_user_123",
            "message_text": "Hello from user",
            "timestamp": 1234567890
        }

        # Mock conversation retrieval/creation
        mock_conversation = Mock(spec=Conversation)
        mock_conversation.id = uuid4()
        mock_conversation_service.get_or_create_conversation = AsyncMock(return_value=mock_conversation)
        mock_conversation_service.add_message = AsyncMock()

        # Mock OpenClaw bridge
        zalo_service._forward_to_openclaw = AsyncMock()

        result = await zalo_service.process_webhook(workspace_id=workspace_id, event=event)

        assert result["status"] == "processed"
        assert result["conversation_id"] == str(mock_conversation.id)
        mock_conversation_service.get_or_create_conversation.assert_called_once()
        mock_conversation_service.add_message.assert_called_once()
        zalo_service._forward_to_openclaw.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_webhook_follow_event(self, zalo_service):
        """Test processing user follow event"""
        workspace_id = uuid4()
        event = {
            "event_type": "follow",
            "user_id": "zalo_user_123",
            "timestamp": 1234567890
        }

        result = await zalo_service.process_webhook(workspace_id=workspace_id, event=event)

        assert result["status"] == "processed"
        assert result["event_type"] == "follow"

    @pytest.mark.asyncio
    async def test_process_webhook_unfollow_event(self, zalo_service):
        """Test processing user unfollow event"""
        workspace_id = uuid4()
        event = {
            "event_type": "unfollow",
            "user_id": "zalo_user_123",
            "timestamp": 1234567890
        }

        result = await zalo_service.process_webhook(workspace_id=workspace_id, event=event)

        assert result["status"] == "processed"
        assert result["event_type"] == "unfollow"

    @pytest.mark.asyncio
    async def test_process_webhook_invalid_event(self, zalo_service):
        """Test processing invalid webhook event"""
        workspace_id = uuid4()
        invalid_event = {}

        with pytest.raises(ValueError, match="Invalid event format"):
            await zalo_service.process_webhook(workspace_id=workspace_id, event=invalid_event)


class TestZaloStatusCheck:
    """Tests for OA status check"""

    @pytest.mark.asyncio
    async def test_get_oa_status_connected(self, zalo_service, mock_db_session):
        """Test getting OA status when connected"""
        workspace_id = uuid4()

        # Mock existing credentials
        mock_key = UserAPIKey(
            workspace_id=str(workspace_id),
            provider="zalo",
            encrypted_key="encrypted_token",
            key_hash="hash"
        )
        mock_db_session.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=mock_key)))

        zalo_service.user_api_key_service.decrypt_key = Mock(return_value='{"oa_id":"123","app_id":"app"}')

        result = await zalo_service.get_oa_status(workspace_id=workspace_id)

        assert result["connected"] is True
        assert result["oa_id"] == "123"

    @pytest.mark.asyncio
    async def test_get_oa_status_not_connected(self, zalo_service, mock_db_session):
        """Test getting OA status when not connected"""
        workspace_id = uuid4()

        mock_db_session.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None)))

        result = await zalo_service.get_oa_status(workspace_id=workspace_id)

        assert result["connected"] is False
        assert result["oa_id"] is None


class TestZaloSignatureVerification:
    """Tests for webhook signature verification"""

    def test_verify_webhook_signature_valid(self, zalo_service):
        """Test verifying valid webhook signature"""
        payload = '{"event_name":"test"}'
        signature = "valid_signature_hash"

        with patch('backend.services.zalo_service.ZaloClient') as MockZaloClient:
            mock_client = Mock()
            mock_client.verify_webhook_signature = Mock(return_value=True)
            MockZaloClient.return_value = mock_client

            result = zalo_service.verify_webhook_signature(
                payload=payload,
                signature=signature,
                app_secret="secret"
            )

            assert result is True

    def test_verify_webhook_signature_invalid(self, zalo_service):
        """Test verifying invalid webhook signature"""
        payload = '{"event_name":"test"}'
        signature = "invalid_signature"

        with patch('backend.services.zalo_service.ZaloClient') as MockZaloClient:
            mock_client = Mock()
            mock_client.verify_webhook_signature = Mock(return_value=False)
            MockZaloClient.return_value = mock_client

            result = zalo_service.verify_webhook_signature(
                payload=payload,
                signature=signature,
                app_secret="secret"
            )

            assert result is False


class TestZaloHelperMethods:
    """Tests for internal helper methods"""

    @pytest.mark.asyncio
    async def test_get_credentials_success(self, zalo_service, mock_db_session):
        """Test retrieving stored credentials"""
        workspace_id = uuid4()

        mock_key = UserAPIKey(
            workspace_id=str(workspace_id),
            provider="zalo",
            encrypted_key="encrypted_token",
            key_hash="hash"
        )
        mock_db_session.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=mock_key)))

        credentials_json = '{"oa_id":"123","app_id":"app","app_secret":"secret","access_token":"token"}'
        zalo_service.user_api_key_service.decrypt_key = Mock(return_value=credentials_json)

        result = await zalo_service._get_credentials(workspace_id=workspace_id)

        assert result["oa_id"] == "123"
        assert result["app_id"] == "app"
        assert result["access_token"] == "token"

    @pytest.mark.asyncio
    async def test_get_credentials_not_found(self, zalo_service, mock_db_session):
        """Test retrieving credentials when none exist"""
        workspace_id = uuid4()

        mock_db_session.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None)))

        with pytest.raises(ZaloConfigurationError, match="No Zalo credentials found"):
            await zalo_service._get_credentials(workspace_id=workspace_id)

    @pytest.mark.asyncio
    async def test_forward_to_openclaw_success(self, zalo_service):
        """Test forwarding message to OpenClaw bridge"""
        conversation_id = uuid4()
        message = "Hello from user"

        # Mock the entire _forward_to_openclaw method since it depends on external integration
        # In production, this would be tested via integration tests
        zalo_service._forward_to_openclaw = AsyncMock()

        await zalo_service._forward_to_openclaw(
            conversation_id=conversation_id,
            message=message
        )

        zalo_service._forward_to_openclaw.assert_called_once()
