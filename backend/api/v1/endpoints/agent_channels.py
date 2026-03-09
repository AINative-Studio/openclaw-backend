"""
Agent Channel OAuth Authentication API Endpoints

Provides OAuth flow for configuring agent communication channels:
- Email (Google, Microsoft)
- Slack
- Discord
- SMS (Twilio)

OAuth Flow:
1. POST /agents/{agent_id}/channels/email/authorize - Start OAuth, return authorization URL
2. User grants permissions in browser
3. GET /oauth/callback - Handle OAuth callback, exchange code for tokens, store encrypted
4. GET /agents/{agent_id}/channels - List configured channels
5. DELETE /agents/{agent_id}/channels/{channel_type} - Revoke channel access
"""

import logging
import secrets
import time
import os
from uuid import UUID
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query

from backend.security.auth_dependencies import get_current_active_user
from backend.models.user import User
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import httpx

logger = logging.getLogger(__name__)

try:
    from backend.db.base import get_db
    from backend.models.agent_channel_credentials import AgentChannelCredentials
    from backend.models.agent_swarm_lifecycle import AgentSwarmInstance
    from backend.schemas.agent_channel_auth import (
        OAuthStartRequest,
        OAuthStartResponse,
        OAuthCallbackRequest,
        ChannelCredentialInfo,
        ChannelCredentialsListResponse,
        OAuthSuccessResponse,
        OAuthErrorResponse,
    )
    AGENT_CHANNEL_AUTH_AVAILABLE = True
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"Agent channel authentication service not available: {e}")
    AGENT_CHANNEL_AUTH_AVAILABLE = False

router = APIRouter(prefix="/agents", tags=["Agent Channels"])

# OAuth configuration - TODO: Replace with actual credentials from Google Cloud Console
# Register at: https://console.cloud.google.com/apis/credentials
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "placeholder-client-id")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "placeholder-client-secret")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# OAuth scopes for Gmail
DEFAULT_GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]

# In-memory OAuth state store (TODO: Replace with Redis in production)
_oauth_state_store: dict[str, dict] = {}


def _check_available() -> None:
    """Raise 503 if service dependencies are not available"""
    if not AGENT_CHANNEL_AUTH_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent channel authentication service is not available",
        )


def _validate_agent_exists(db: Session, agent_id: UUID) -> AgentSwarmInstance:
    """
    Validate that agent exists in database

    Args:
        db: Database session
        agent_id: Agent UUID

    Returns:
        AgentSwarmInstance object

    Raises:
        HTTPException: 404 if agent not found
    """
    agent = db.query(AgentSwarmInstance).filter(AgentSwarmInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )
    return agent


def _store_oauth_state(state: str, agent_id: UUID, channel_type: str, provider: str) -> None:
    """
    Store OAuth state token temporarily (5 minutes TTL)

    Args:
        state: State token
        agent_id: Agent UUID
        channel_type: Channel type (email, slack, etc.)
        provider: OAuth provider (google, microsoft, etc.)
    """
    _oauth_state_store[state] = {
        "agent_id": str(agent_id),
        "channel_type": channel_type,
        "provider": provider,
        "expires_at": time.time() + 300,  # 5 minutes
    }


def _get_oauth_state(state: str) -> Optional[dict]:
    """
    Retrieve and validate OAuth state token

    Args:
        state: State token

    Returns:
        State data dict or None if invalid/expired
    """
    state_data = _oauth_state_store.get(state)
    if not state_data:
        return None

    # Check expiration
    if time.time() > state_data["expires_at"]:
        del _oauth_state_store[state]
        return None

    return state_data


def _cleanup_expired_states() -> None:
    """Remove expired OAuth state tokens"""
    current_time = time.time()
    expired_keys = [
        key for key, data in _oauth_state_store.items()
        if data["expires_at"] < current_time
    ]
    for key in expired_keys:
        del _oauth_state_store[key]


def _credential_to_info(credential: AgentChannelCredentials) -> ChannelCredentialInfo:
    """
    Convert ORM model to API response (redacts credentials)

    Args:
        credential: AgentChannelCredentials ORM object

    Returns:
        ChannelCredentialInfo with credentials redacted
    """
    return ChannelCredentialInfo(
        id=credential.id,
        agent_id=credential.agent_id,
        channel_type=credential.channel_type,
        provider=credential.provider,
        has_credentials=bool(credential.credentials),
        is_expired=credential.is_expired(),
        metadata=credential.get_metadata(),
        expires_at=credential.expires_at,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


@router.post(
    "/{agent_id}/channels/email/authorize",
    response_model=OAuthStartResponse,
    status_code=status.HTTP_200_OK,
    summary="Start OAuth flow for email channel",
)
def start_email_oauth(
    agent_id: UUID,
    request: OAuthStartRequest = OAuthStartRequest(),
    db: Session = Depends(get_db),
) -> OAuthStartResponse:
    """
    Initiate OAuth flow for email channel (Google or Microsoft).

    Returns an authorization URL for the user to grant permissions.
    The user should be redirected to this URL in their browser.

    After granting permissions, Google will redirect to the callback URL
    with an authorization code that can be exchanged for access/refresh tokens.
    """
    _check_available()

    try:
        # Validate agent exists
        _validate_agent_exists(db, agent_id)

        # Generate secure state token for CSRF protection
        state = secrets.token_urlsafe(32)

        # Store state with agent context
        _store_oauth_state(
            state=state,
            agent_id=agent_id,
            channel_type="email",
            provider="google",
        )

        # Cleanup expired states
        _cleanup_expired_states()

        # Determine scopes
        scopes = request.scopes if request.scopes else DEFAULT_GMAIL_SCOPES
        scope_string = " ".join(scopes)

        # Build Google OAuth URL
        oauth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={GOOGLE_CLIENT_ID}&"
            f"redirect_uri={BACKEND_URL}/api/v1/oauth/callback&"
            f"response_type=code&"
            f"scope={scope_string}&"
            f"access_type=offline&"  # Request refresh token
            f"prompt=consent&"  # Force consent screen to get refresh token
            f"state={state}"
        )

        return OAuthStartResponse(
            oauth_url=oauth_url,
            state=state,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting OAuth flow: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start OAuth flow: {str(e)}",
        )


@router.get(
    "/oauth/callback",
    summary="OAuth callback endpoint",
    description="Handles OAuth callback from providers (Google, Microsoft, etc.)",
)
async def oauth_callback(
    code: Optional[str] = Query(None, description="Authorization code"),
    state: Optional[str] = Query(None, description="State token"),
    error: Optional[str] = Query(None, description="Error code if OAuth failed"),
    error_description: Optional[str] = Query(None, description="Error description"),
    db: Session = Depends(get_db),
):
    """
    Handle OAuth callback from provider.

    This endpoint receives the authorization code from the OAuth provider
    and exchanges it for access/refresh tokens.

    On success, redirects to frontend with success message.
    On error, redirects to frontend with error message.
    """
    _check_available()

    try:
        # Check for OAuth errors
        if error:
            logger.warning(f"OAuth error: {error} - {error_description}")
            return RedirectResponse(
                url=f"{FRONTEND_URL}/agents?oauth_error={error}&error_description={error_description}",
                status_code=status.HTTP_302_FOUND,
            )

        # Validate required parameters
        if not code or not state:
            logger.error("Missing code or state in OAuth callback")
            return RedirectResponse(
                url=f"{FRONTEND_URL}/agents?oauth_error=invalid_request&error_description=Missing+code+or+state",
                status_code=status.HTTP_302_FOUND,
            )

        # Validate and retrieve state data
        state_data = _get_oauth_state(state)
        if not state_data:
            logger.error(f"Invalid or expired state token: {state}")
            return RedirectResponse(
                url=f"{FRONTEND_URL}/agents?oauth_error=invalid_state&error_description=Invalid+or+expired+state+token",
                status_code=status.HTTP_302_FOUND,
            )

        agent_id = UUID(state_data["agent_id"])
        channel_type = state_data["channel_type"]
        provider = state_data["provider"]

        # Delete state token (one-time use)
        del _oauth_state_store[state]

        # Exchange authorization code for tokens
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": f"{BACKEND_URL}/api/v1/oauth/callback",
                    "grant_type": "authorization_code",
                },
                timeout=10.0,
            )

            if token_response.status_code != 200:
                logger.error(f"Token exchange failed: {token_response.text}")
                return RedirectResponse(
                    url=f"{FRONTEND_URL}/agents?oauth_error=token_exchange_failed&error_description={token_response.text}",
                    status_code=status.HTTP_302_FOUND,
                )

            token_data = token_response.json()

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)

        if not access_token:
            logger.error("No access_token in token response")
            return RedirectResponse(
                url=f"{FRONTEND_URL}/agents?oauth_error=missing_token&error_description=No+access+token+received",
                status_code=status.HTTP_302_FOUND,
            )

        # Get user email from Google
        user_email = None
        try:
            async with httpx.AsyncClient() as client:
                userinfo_response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10.0,
                )
                if userinfo_response.status_code == 200:
                    userinfo = userinfo_response.json()
                    user_email = userinfo.get("email")
        except Exception as e:
            logger.warning(f"Failed to fetch user email: {e}")

        # Calculate expiration timestamp
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Store credentials in database
        # Check if credentials already exist
        existing_credential = (
            db.query(AgentChannelCredentials)
            .filter(
                AgentChannelCredentials.agent_id == agent_id,
                AgentChannelCredentials.channel_type == channel_type,
                AgentChannelCredentials.provider == provider,
            )
            .first()
        )

        if existing_credential:
            # Update existing credentials
            credential = existing_credential
        else:
            # Create new credentials
            credential = AgentChannelCredentials(
                agent_id=agent_id,
                channel_type=channel_type,
                provider=provider,
            )
            db.add(credential)

        # Store encrypted credentials
        credential.set_credentials({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": token_data.get("token_type", "Bearer"),
            "scope": token_data.get("scope", ""),
        })

        credential.expires_at = expires_at

        # Store metadata (non-sensitive)
        metadata = {}
        if user_email:
            metadata["email_address"] = user_email
        metadata["scopes"] = token_data.get("scope", "").split()
        credential.set_metadata(metadata)

        # Commit to database
        try:
            db.commit()
            db.refresh(credential)
        except IntegrityError as e:
            db.rollback()
            logger.warning(f"Integrity error storing credentials: {e}")
            return RedirectResponse(
                url=f"{FRONTEND_URL}/agents?oauth_error=storage_conflict&error_description=Credentials+already+exist",
                status_code=status.HTTP_302_FOUND,
            )

        # Redirect to frontend with success
        return RedirectResponse(
            url=f"{FRONTEND_URL}/agents/{agent_id}?oauth=success&channel={channel_type}",
            status_code=status.HTTP_302_FOUND,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in OAuth callback: {e}", exc_info=True)
        return RedirectResponse(
            url=f"{FRONTEND_URL}/agents?oauth_error=server_error&error_description={str(e)}",
            status_code=status.HTTP_302_FOUND,
        )


@router.get(
    "/{agent_id}/channels",
    response_model=ChannelCredentialsListResponse,
    status_code=status.HTTP_200_OK,
    summary="List configured channels for an agent",
)
def list_agent_channels(
    agent_id: UUID,
    db: Session = Depends(get_db),
) -> ChannelCredentialsListResponse:
    """
    List all configured communication channels for an agent.

    Returns credential status and metadata but not actual tokens.
    """
    _check_available()

    try:
        # Validate agent exists
        _validate_agent_exists(db, agent_id)

        # Query all channels for this agent
        credentials = (
            db.query(AgentChannelCredentials)
            .filter(AgentChannelCredentials.agent_id == agent_id)
            .order_by(AgentChannelCredentials.channel_type, AgentChannelCredentials.provider)
            .all()
        )

        return ChannelCredentialsListResponse(
            credentials=[_credential_to_info(c) for c in credentials]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing agent channels: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agent channels: {str(e)}",
        )


@router.delete(
    "/{agent_id}/channels/{channel_type}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke channel access",
)
def revoke_channel_access(
    agent_id: UUID,
    channel_type: str,
    provider: Optional[str] = Query(None, description="OAuth provider (google, microsoft, etc.)"),
    db: Session = Depends(get_db),
) -> None:
    """
    Revoke access to a communication channel for an agent.

    Deletes stored credentials. If provider is specified, only that provider's
    credentials are deleted. Otherwise, all credentials for the channel type are deleted.

    Returns 204 No Content on success.
    """
    _check_available()

    try:
        # Validate agent exists
        _validate_agent_exists(db, agent_id)

        # Build query
        query = db.query(AgentChannelCredentials).filter(
            AgentChannelCredentials.agent_id == agent_id,
            AgentChannelCredentials.channel_type == channel_type,
        )

        if provider:
            query = query.filter(AgentChannelCredentials.provider == provider)

        credentials = query.all()

        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No {channel_type} credentials found for agent '{agent_id}'",
            )

        # Delete all matching credentials
        for credential in credentials:
            db.delete(credential)

        db.commit()

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error revoking channel access: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke channel access: {str(e)}",
        )


@router.get(
    "/{agent_id}/channels/{channel_type}",
    response_model=ChannelCredentialInfo,
    status_code=status.HTTP_200_OK,
    summary="Get specific channel configuration",
)
def get_channel_configuration(
    agent_id: UUID,
    channel_type: str,
    provider: Optional[str] = Query(None, description="OAuth provider (google, microsoft, etc.)"),
    db: Session = Depends(get_db),
) -> ChannelCredentialInfo:
    """
    Get configuration for a specific channel.

    Returns credential status and metadata but not actual tokens.
    If provider is specified, returns credentials for that provider only.
    If multiple providers exist for the channel type, returns the first one.
    """
    _check_available()

    try:
        # Validate agent exists
        _validate_agent_exists(db, agent_id)

        # Build query
        query = db.query(AgentChannelCredentials).filter(
            AgentChannelCredentials.agent_id == agent_id,
            AgentChannelCredentials.channel_type == channel_type,
        )

        if provider:
            query = query.filter(AgentChannelCredentials.provider == provider)

        credential = query.first()

        if not credential:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Channel '{channel_type}' not configured for agent '{agent_id}'",
            )

        return _credential_to_info(credential)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting channel configuration: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get channel configuration: {str(e)}",
        )
