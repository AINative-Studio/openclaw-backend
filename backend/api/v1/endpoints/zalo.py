"""
Zalo API Endpoints (Issue #121)

FastAPI routes for Zalo Official Account integration.

Endpoints:
- GET /api/v1/zalo/oauth/authorize - Get OAuth URL
- POST /api/v1/zalo/oauth/callback - Handle OAuth callback
- POST /api/v1/zalo/connect - Connect Zalo OA
- DELETE /api/v1/zalo/disconnect - Disconnect Zalo OA
- POST /api/v1/zalo/webhook - Webhook for incoming messages
- GET /api/v1/zalo/status - Get connection status
"""

import json
from typing import Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.base import get_db
from backend.schemas.zalo_schemas import (
    ZaloOAuthRequest,
    ZaloOAuthResponse,
    ZaloOAuthCallbackRequest,
    ZaloTokenResponse,
    ZaloConnectRequest,
    ZaloConnectResponse,
    ZaloDisconnectResponse,
    ZaloWebhookEvent,
    ZaloWebhookResponse,
    ZaloStatusResponse
)
from backend.services.zalo_service import (
    ZaloService,
    ZaloConfigurationError,
    ZaloMessageError
)
from backend.services.user_api_key_service import UserAPIKeyService
from backend.services.conversation_service import ConversationService
from backend.integrations.zalo_client import (
    ZaloClient,
    ZaloAuthError,
    ZaloAPIError,
    ZaloWebhookError
)


router = APIRouter(prefix="/zalo", tags=["zalo"])


def get_user_api_key_service(db: AsyncSession = Depends(get_db)) -> UserAPIKeyService:
    """Dependency for UserAPIKeyService"""
    return UserAPIKeyService(db=db)


def get_zalo_service(
    db: AsyncSession = Depends(get_db),
    user_api_key_service: UserAPIKeyService = Depends(get_user_api_key_service)
) -> ZaloService:
    """Dependency for ZaloService"""
    # ConversationService would be injected here in production
    return ZaloService(
        db=db,
        user_api_key_service=user_api_key_service
    )


@router.get("/oauth/authorize", response_model=ZaloOAuthResponse)
async def get_oauth_authorize_url(
    request_data: ZaloOAuthRequest = Depends()
) -> ZaloOAuthResponse:
    """
    Generate OAuth authorization URL.

    Args:
        request_data: OAuth request parameters

    Returns:
        OAuth URL and state token

    Security:
        Requires authentication (Bearer token)
    """
    # Create temporary client for OAuth URL generation
    # In production, app_id would come from workspace config
    client = ZaloClient(
        oa_id="temp",
        app_id="temp_app_id",  # Would be workspace-specific
        app_secret="temp_secret"
    )

    auth_url = client.get_oauth_url(
        redirect_uri=request_data.redirect_uri,
        state=request_data.state
    )

    # Extract state from URL
    import urllib.parse
    parsed = urllib.parse.urlparse(auth_url)
    params = urllib.parse.parse_qs(parsed.query)
    state = params.get("state", [None])[0]

    return ZaloOAuthResponse(auth_url=auth_url, state=state)


@router.post("/oauth/callback", response_model=ZaloTokenResponse)
async def handle_oauth_callback(
    callback_data: ZaloOAuthCallbackRequest
) -> ZaloTokenResponse:
    """
    Handle OAuth callback and exchange code for tokens.

    Args:
        callback_data: Authorization code and state

    Returns:
        Access and refresh tokens

    Raises:
        HTTPException: If token exchange fails
    """
    try:
        # Create temporary client
        client = ZaloClient(
            oa_id="temp",
            app_id="temp_app_id",
            app_secret="temp_secret"
        )

        tokens = await client.exchange_code_for_token(code=callback_data.code)

        return ZaloTokenResponse(
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            expires_in=tokens["expires_in"]
        )

    except ZaloAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/connect", response_model=ZaloConnectResponse)
async def connect_oa(
    connect_data: ZaloConnectRequest,
    zalo_service: ZaloService = Depends(get_zalo_service)
) -> ZaloConnectResponse:
    """
    Connect Zalo Official Account to workspace.

    Args:
        connect_data: OA connection configuration
        zalo_service: Zalo service instance

    Returns:
        Connection result

    Raises:
        HTTPException: If connection fails

    Security:
        Requires authentication
    """
    try:
        oa_config = {
            "oa_id": connect_data.oa_id,
            "app_id": connect_data.app_id,
            "app_secret": connect_data.app_secret,
            "access_token": connect_data.access_token,
            "refresh_token": connect_data.refresh_token
        }

        result = await zalo_service.connect_oa(
            workspace_id=connect_data.workspace_id,
            oa_config=oa_config
        )

        return ZaloConnectResponse(**result)

    except ZaloConfigurationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/disconnect", response_model=ZaloDisconnectResponse)
async def disconnect_oa(
    workspace_id: UUID,
    zalo_service: ZaloService = Depends(get_zalo_service)
) -> ZaloDisconnectResponse:
    """
    Disconnect Zalo Official Account from workspace.

    Args:
        workspace_id: Workspace UUID
        zalo_service: Zalo service instance

    Returns:
        Disconnection result

    Raises:
        HTTPException: If not connected

    Security:
        Requires authentication
    """
    try:
        result = await zalo_service.disconnect_oa(workspace_id=workspace_id)
        return ZaloDisconnectResponse(**result)

    except ZaloConfigurationError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/webhook", response_model=ZaloWebhookResponse)
async def handle_webhook(
    workspace_id: UUID,
    request: Request,
    x_zalo_signature: str = Header(..., alias="X-Zalo-Signature"),
    zalo_service: ZaloService = Depends(get_zalo_service)
) -> ZaloWebhookResponse:
    """
    Handle incoming Zalo webhook events.

    Args:
        workspace_id: Workspace UUID
        request: FastAPI request object
        x_zalo_signature: Webhook signature header
        zalo_service: Zalo service instance

    Returns:
        Processing result

    Raises:
        HTTPException: If webhook processing fails

    Security:
        Validates webhook signature
    """
    # Read raw body for signature verification
    body = await request.body()
    payload_str = body.decode("utf-8")

    # Parse JSON payload
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )

    # Get credentials to verify signature
    try:
        credentials = await zalo_service._get_credentials(workspace_id)
        app_secret = credentials["app_secret"]
    except ZaloConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zalo OA not configured for workspace"
        )

    # Verify signature
    if not zalo_service.verify_webhook_signature(
        payload=payload_str,
        signature=x_zalo_signature,
        app_secret=app_secret
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature"
        )

    # Parse webhook with client
    try:
        client = ZaloClient(
            oa_id=credentials["oa_id"],
            app_id=credentials["app_id"],
            app_secret=app_secret
        )
        parsed_event = client.handle_webhook(payload)

    except ZaloWebhookError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Process event
    try:
        result = await zalo_service.process_webhook(
            workspace_id=workspace_id,
            event=parsed_event
        )
        return ZaloWebhookResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/status", response_model=ZaloStatusResponse)
async def get_status(
    workspace_id: UUID,
    zalo_service: ZaloService = Depends(get_zalo_service)
) -> ZaloStatusResponse:
    """
    Get Zalo OA connection status.

    Args:
        workspace_id: Workspace UUID
        zalo_service: Zalo service instance

    Returns:
        Connection status

    Security:
        Requires authentication
    """
    result = await zalo_service.get_oa_status(workspace_id=workspace_id)
    return ZaloStatusResponse(**result)
