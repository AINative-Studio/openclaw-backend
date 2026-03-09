"""
Zalo Service - Business Logic Layer (Issue #121)

Manages Zalo Official Account integration including:
- OA connection/disconnection
- Credential storage (encrypted)
- Message sending
- Webhook processing
- Integration with ConversationService and OpenClaw Bridge
"""

import json
from typing import Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models.user_api_key import UserAPIKey
from backend.models.conversation import Conversation, ConversationStatus
from backend.services.user_api_key_service import UserAPIKeyService
from backend.services.conversation_service import ConversationService
from backend.integrations.zalo_client import (
    ZaloClient,
    ZaloAPIError,
    ZaloAuthError
)


class ZaloConfigurationError(Exception):
    """Exception for configuration errors"""
    pass


class ZaloMessageError(Exception):
    """Exception for message sending errors"""
    pass


class ZaloService:
    """
    Service for managing Zalo Official Account integration.

    Handles credential storage, message sending, and webhook processing.
    """

    PROVIDER_NAME = "zalo"

    def __init__(
        self,
        db: AsyncSession,
        user_api_key_service: UserAPIKeyService,
        conversation_service: Optional[ConversationService] = None
    ):
        """
        Initialize Zalo service.

        Args:
            db: Async database session
            user_api_key_service: Service for encrypted credential storage
            conversation_service: Optional conversation service for message storage
        """
        self.db = db
        self.user_api_key_service = user_api_key_service
        self.conversation_service = conversation_service

    async def connect_oa(
        self,
        workspace_id: UUID,
        oa_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Connect Zalo Official Account to workspace.

        Stores encrypted credentials in user_api_keys table.

        Args:
            workspace_id: Workspace UUID
            oa_config: Dict with oa_id, app_id, app_secret, access_token, refresh_token

        Returns:
            Connection result dict

        Raises:
            ZaloConfigurationError: If configuration is invalid
        """
        # Validate required fields
        required_fields = ["oa_id", "app_id", "app_secret", "access_token", "refresh_token"]
        missing = [f for f in required_fields if f not in oa_config]

        if missing:
            raise ZaloConfigurationError(f"Missing required fields: {', '.join(missing)}")

        # Serialize config to JSON
        credentials_json = json.dumps(oa_config)

        # Encrypt credentials
        encrypted_credentials = self.user_api_key_service.encrypt_key(credentials_json)

        # Check if credentials already exist
        stmt = select(UserAPIKey).where(
            UserAPIKey.workspace_id == str(workspace_id),
            UserAPIKey.provider == self.PROVIDER_NAME
        )
        result = await self.db.execute(stmt)
        existing_key = result.scalar_one_or_none()

        if existing_key:
            # Update existing
            existing_key.encrypted_key = encrypted_credentials
            existing_key.key_hash = UserAPIKey.compute_key_hash(credentials_json)
            status = "updated"
        else:
            # Create new
            new_key = UserAPIKey(
                workspace_id=str(workspace_id),
                provider=self.PROVIDER_NAME,
                encrypted_key=encrypted_credentials,
                key_hash=UserAPIKey.compute_key_hash(credentials_json)
            )
            self.db.add(new_key)
            status = "connected"

        await self.db.commit()

        return {
            "status": status,
            "oa_id": oa_config["oa_id"],
            "oa_info": None  # Can be populated later
        }

    async def disconnect_oa(self, workspace_id: UUID) -> Dict[str, str]:
        """
        Disconnect Zalo Official Account from workspace.

        Removes stored credentials.

        Args:
            workspace_id: Workspace UUID

        Returns:
            Disconnection result dict

        Raises:
            ZaloConfigurationError: If no connection exists
        """
        stmt = select(UserAPIKey).where(
            UserAPIKey.workspace_id == str(workspace_id),
            UserAPIKey.provider == self.PROVIDER_NAME
        )
        result = await self.db.execute(stmt)
        existing_key = result.scalar_one_or_none()

        if not existing_key:
            raise ZaloConfigurationError("No Zalo OA connected for this workspace")

        await self.db.delete(existing_key)
        await self.db.commit()

        return {"status": "disconnected"}

    async def send_message(
        self,
        workspace_id: UUID,
        user_id: str,
        message: str
    ) -> Dict[str, Any]:
        """
        Send message to Zalo user.

        Args:
            workspace_id: Workspace UUID
            user_id: Zalo user ID
            message: Message text

        Returns:
            Send result dict with message_id

        Raises:
            ZaloConfigurationError: If credentials not found
            ZaloMessageError: If message send fails
        """
        # Get credentials
        credentials = await self._get_credentials(workspace_id)

        # Create Zalo client
        client = ZaloClient(
            oa_id=credentials["oa_id"],
            app_id=credentials["app_id"],
            app_secret=credentials["app_secret"]
        )
        client.access_token = credentials["access_token"]

        # Send message
        try:
            response = await client.send_text_message(user_id=user_id, message=message)
            return {"message_id": response["data"]["message_id"]}
        except ZaloAPIError as e:
            raise ZaloMessageError(f"Failed to send message: {str(e)}")

    async def process_webhook(
        self,
        workspace_id: UUID,
        event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process incoming webhook event.

        Args:
            workspace_id: Workspace UUID
            event: Parsed webhook event dict

        Returns:
            Processing result dict

        Raises:
            ValueError: If event format is invalid
        """
        if not event or "event_type" not in event or "user_id" not in event:
            raise ValueError("Invalid event format")

        event_type = event["event_type"]

        # Handle different event types
        if event_type == "user_send_text":
            # Create/get conversation
            if self.conversation_service:
                conversation = await self.conversation_service.get_or_create_conversation(
                    workspace_id=workspace_id,
                    channel="zalo",
                    channel_conversation_id=event["user_id"]
                )

                # Store message
                await self.conversation_service.add_message(
                    conversation_id=conversation.id,
                    role="user",
                    content=event.get("message_text", "")
                )

                # Forward to OpenClaw Bridge
                await self._forward_to_openclaw(
                    conversation_id=conversation.id,
                    message=event.get("message_text", "")
                )

                return {
                    "status": "processed",
                    "conversation_id": str(conversation.id)
                }

        # Handle follow/unfollow events
        elif event_type in ["follow", "unfollow"]:
            return {
                "status": "processed",
                "event_type": event_type
            }

        return {"status": "processed"}

    async def get_oa_status(self, workspace_id: UUID) -> Dict[str, Any]:
        """
        Get Zalo OA connection status.

        Args:
            workspace_id: Workspace UUID

        Returns:
            Status dict with connection info
        """
        stmt = select(UserAPIKey).where(
            UserAPIKey.workspace_id == str(workspace_id),
            UserAPIKey.provider == self.PROVIDER_NAME
        )
        result = await self.db.execute(stmt)
        existing_key = result.scalar_one_or_none()

        if not existing_key:
            return {
                "connected": False,
                "oa_id": None
            }

        # Decrypt and parse credentials
        try:
            credentials_json = self.user_api_key_service.decrypt_key(
                existing_key.encrypted_key
            )
            credentials = json.loads(credentials_json)

            return {
                "connected": True,
                "oa_id": credentials.get("oa_id"),
                "app_id": credentials.get("app_id")
            }
        except Exception:
            return {
                "connected": False,
                "oa_id": None
            }

    def verify_webhook_signature(
        self,
        payload: str,
        signature: str,
        app_secret: str
    ) -> bool:
        """
        Verify webhook signature.

        Args:
            payload: Raw webhook payload string
            signature: Signature from header
            app_secret: Zalo app secret

        Returns:
            True if signature is valid
        """
        client = ZaloClient(
            oa_id="temp",  # Not needed for signature verification
            app_id="temp",
            app_secret=app_secret
        )
        return client.verify_webhook_signature(payload, signature)

    async def _get_credentials(self, workspace_id: UUID) -> Dict[str, Any]:
        """
        Retrieve and decrypt stored credentials.

        Args:
            workspace_id: Workspace UUID

        Returns:
            Credentials dict

        Raises:
            ZaloConfigurationError: If credentials not found
        """
        stmt = select(UserAPIKey).where(
            UserAPIKey.workspace_id == str(workspace_id),
            UserAPIKey.provider == self.PROVIDER_NAME
        )
        result = await self.db.execute(stmt)
        key_record = result.scalar_one_or_none()

        if not key_record:
            raise ZaloConfigurationError("No Zalo credentials found for workspace")

        # Decrypt credentials
        credentials_json = self.user_api_key_service.decrypt_key(
            key_record.encrypted_key
        )

        return json.loads(credentials_json)

    async def _forward_to_openclaw(
        self,
        conversation_id: UUID,
        message: str
    ) -> None:
        """
        Forward message to OpenClaw Bridge.

        Args:
            conversation_id: Conversation UUID
            message: Message text
        """
        # Import here to avoid circular dependency
        from integrations.openclaw_bridge import get_openclaw_bridge

        bridge = get_openclaw_bridge()
        await bridge.send_message(
            conversation_id=str(conversation_id),
            content=message
        )
