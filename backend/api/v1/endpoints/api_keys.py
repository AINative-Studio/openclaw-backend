"""
API Key Management Endpoints (Issue #83)

REST API for managing encrypted API keys for external services.

Endpoints:
    GET    /api/v1/api-keys                      - List all API keys (masked)
    POST   /api/v1/api-keys                      - Create new API key
    PUT    /api/v1/api-keys/{service_name}       - Update existing API key
    DELETE /api/v1/api-keys/{service_name}       - Delete API key
    GET    /api/v1/api-keys/{service_name}/verify - Verify API key against service
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.schemas.api_key import (
    APIKeyCreate,
    APIKeyUpdate,
    APIKeyResponse,
    APIKeyVerifyResponse,
    SupportedService,
)
from backend.services.api_key_service import APIKeyService


router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


def get_api_key_service(db: Session = Depends(get_db)) -> APIKeyService:
    """Dependency to create APIKeyService instance."""
    try:
        return APIKeyService(db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"API key encryption not configured: {str(e)}"
        )


@router.get("", response_model=list[APIKeyResponse])
def list_api_keys(
    service: APIKeyService = Depends(get_api_key_service)
):
    """
    List all configured API keys.

    Returns masked keys (only last 4 characters visible).
    Never returns plaintext or encrypted keys.
    """
    api_keys = service.list_api_keys()

    # Build response with masked keys
    response = []
    for api_key in api_keys:
        # Decrypt to mask (not exposed in response)
        plaintext = service.decrypt_key(api_key.encrypted_key)
        masked = service.mask_key(plaintext)

        response.append(
            APIKeyResponse(
                id=api_key.id,
                service_name=api_key.service_name,
                masked_key=masked,
                created_at=api_key.created_at,
                updated_at=api_key.updated_at,
                is_active=api_key.is_active,
            )
        )

    return response


@router.post("", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: APIKeyCreate,
    service: APIKeyService = Depends(get_api_key_service)
):
    """
    Create a new API key.

    The key will be encrypted before storage using Fernet symmetric encryption.
    Returns a masked version of the key (only last 4 characters visible).
    """
    try:
        api_key = service.create_api_key(payload.service_name, payload.api_key)

        # Mask key for response
        masked = service.mask_key(payload.api_key)

        return APIKeyResponse(
            id=api_key.id,
            service_name=api_key.service_name,
            masked_key=masked,
            created_at=api_key.created_at,
            updated_at=api_key.updated_at,
            is_active=api_key.is_active,
        )
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API key: {str(e)}"
        )


@router.put("/{service_name}", response_model=APIKeyResponse)
def update_api_key(
    service_name: str,
    payload: APIKeyUpdate,
    service: APIKeyService = Depends(get_api_key_service)
):
    """
    Update an existing API key.

    The new key will be encrypted before storage.
    Returns a masked version of the key.
    """
    try:
        api_key = service.update_api_key(service_name, payload.api_key)

        # Mask key for response
        masked = service.mask_key(payload.api_key)

        return APIKeyResponse(
            id=api_key.id,
            service_name=api_key.service_name,
            masked_key=masked,
            created_at=api_key.created_at,
            updated_at=api_key.updated_at,
            is_active=api_key.is_active,
        )
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update API key: {str(e)}"
        )


@router.delete("/{service_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_api_key(
    service_name: str,
    service: APIKeyService = Depends(get_api_key_service)
):
    """
    Delete an API key.

    Permanently removes the key from the database.
    """
    try:
        service.delete_api_key(service_name)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete API key: {str(e)}"
        )


@router.get("/{service_name}/verify", response_model=APIKeyVerifyResponse)
def verify_api_key(
    service_name: SupportedService,
    service: APIKeyService = Depends(get_api_key_service)
):
    """
    Verify an API key by testing it against the actual service API.

    Makes a lightweight API call to the service to check if the key is valid.
    Supported services: anthropic, openai, cohere, huggingface

    Returns verification status and message.
    """
    try:
        is_valid, message = service.verify_api_key(service_name)

        return APIKeyVerifyResponse(
            service_name=service_name,
            is_valid=is_valid,
            message=message
        )
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        elif "not supported" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {str(e)}"
        )
