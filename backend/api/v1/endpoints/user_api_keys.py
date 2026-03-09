"""
User API Key Management Endpoints (Issue #96)

REST API for managing workspace-level encrypted API keys for external services.

Security Features:
- All keys encrypted at rest using ENCRYPTION_SECRET
- Never exposes plaintext keys in responses (only masked)
- Validates keys before storage (optional)
- Rate limiting should be applied at nginx/gateway level

Endpoints:
    POST   /api/v1/settings/api-keys          - Create new API key
    GET    /api/v1/settings/api-keys          - List all API keys for workspace (masked)
    DELETE /api/v1/settings/api-keys/{key_id} - Delete API key
    POST   /api/v1/settings/api-keys/test     - Test API key (before or after saving)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query

from backend.security.auth_dependencies import get_current_active_user
from backend.models.user import User
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.schemas.user_api_key import (
    UserAPIKeyCreate,
    UserAPIKeyResponse,
    UserAPIKeyListItem,
    UserAPIKeyTestRequest,
    UserAPIKeyTestResponse,
    UserAPIKeyDeleteResponse,
)
from backend.services.user_api_key_service import UserAPIKeyService


router = APIRouter(prefix="/api/v1/settings/api-keys", tags=["user-api-keys"])


def get_user_api_key_service(db: Session = Depends(get_db)) -> UserAPIKeyService:
    """Dependency to create UserAPIKeyService instance."""
    try:
        return UserAPIKeyService(db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"API key encryption not configured: {str(e)}"
        )


@router.post("", response_model=UserAPIKeyResponse, status_code=status.HTTP_201_CREATED)
def add_api_key(
    payload: UserAPIKeyCreate,
    current_user: User = Depends(get_current_active_user),
    service: UserAPIKeyService = Depends(get_user_api_key_service)
):
    """
    Add a new workspace-level API key.

    The key will be encrypted before storage using Fernet symmetric encryption.
    Returns a masked version of the key (only prefix and last 4 characters visible).

    Security:
        - Key encrypted at rest
        - Optional validation against provider API
        - One key per provider per workspace (enforced by unique constraint)

    Args:
        payload: UserAPIKeyCreate with workspace_id, provider, api_key, and optional validate flag

    Returns:
        UserAPIKeyResponse with masked key

    Raises:
        400: If key already exists or validation fails
        500: If encryption fails
    """
    try:
        user_api_key = service.add_key(
            workspace_id=payload.workspace_id,
            provider=payload.provider,
            plaintext_key=payload.api_key,
            validate=payload.validate
        )

        # Mask key for response
        masked = service.mask_key(payload.api_key)

        return UserAPIKeyResponse(
            id=user_api_key.id,
            workspace_id=user_api_key.workspace_id,
            provider=user_api_key.provider,
            masked_key=masked,
            is_active=user_api_key.is_active,
            last_validated_at=user_api_key.last_validated_at,
            created_at=user_api_key.created_at,
            updated_at=user_api_key.updated_at,
        )
    except ValueError as e:
        error_msg = str(e)
        if "already exists" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        elif "validation failed" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add API key: {error_msg}"
        )


@router.get("", response_model=list[UserAPIKeyListItem])
def list_api_keys(
    workspace_id: str = Query(..., description="Workspace UUID to filter keys"),
    current_user: User = Depends(get_current_active_user),
    service: UserAPIKeyService = Depends(get_user_api_key_service)
):
    """
    List all configured API keys for a workspace.

    Returns masked keys (only prefix and last 4 characters visible).
    Never returns plaintext or encrypted keys.

    Args:
        workspace_id: Workspace UUID (query parameter)

    Returns:
        List of UserAPIKeyListItem with masked keys

    Security:
        - Keys are decrypted only for masking, never exposed in response
        - Only returns keys for specified workspace
    """
    try:
        user_api_keys = service.list_keys(workspace_id)

        # Build response with masked keys
        response = []
        for user_api_key in user_api_keys:
            # Decrypt to mask (not exposed in response)
            plaintext = service.decrypt_key(user_api_key.encrypted_key)
            masked = service.mask_key(plaintext)

            response.append(
                UserAPIKeyListItem(
                    id=user_api_key.id,
                    provider=user_api_key.provider,
                    masked_key=masked,
                    is_active=user_api_key.is_active,
                    last_validated_at=user_api_key.last_validated_at,
                    created_at=user_api_key.created_at,
                )
            )

        return response
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list API keys: {str(e)}"
        )


@router.delete("/{key_id}", response_model=UserAPIKeyDeleteResponse)
def delete_api_key(
    key_id: str,
    current_user: User = Depends(get_current_active_user),
    service: UserAPIKeyService = Depends(get_user_api_key_service)
):
    """
    Delete an API key by ID.

    Permanently removes the key from the database.

    Args:
        key_id: UserAPIKey UUID

    Returns:
        UserAPIKeyDeleteResponse with success status

    Raises:
        404: If key not found
        500: If deletion fails
    """
    try:
        deleted = service.delete_key_by_id(key_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key with ID '{key_id}' not found"
            )

        return UserAPIKeyDeleteResponse(
            success=True,
            message="API key deleted successfully",
            deleted_id=key_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete API key: {str(e)}"
        )


@router.post("/test", response_model=UserAPIKeyTestResponse)
def test_api_key(
    payload: UserAPIKeyTestRequest,
    current_user: User = Depends(get_current_active_user),
    service: UserAPIKeyService = Depends(get_user_api_key_service)
):
    """
    Test an API key by making a lightweight API call to the provider.

    Use this endpoint to validate a key before saving it, or to verify an existing key.

    Supported providers:
        - anthropic: Tests against Claude API
        - openai: Tests against GPT API
        - cohere: Tests against Cohere API
        - huggingface: Tests against HuggingFace API
        - google: Tests against Gemini API

    Args:
        payload: UserAPIKeyTestRequest with provider and api_key

    Returns:
        UserAPIKeyTestResponse with validation result

    Security:
        - Key is never stored during testing
        - Rate limiting recommended at gateway level
        - Validation makes real API calls (may incur costs)

    Raises:
        400: If provider not supported
        500: If test fails unexpectedly
    """
    try:
        is_valid, message = service.validate_key(payload.provider, payload.api_key)

        return UserAPIKeyTestResponse(
            provider=payload.provider,
            is_valid=is_valid,
            message=message
        )
    except ValueError as e:
        if "not supported" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test failed: {str(e)}"
        )
