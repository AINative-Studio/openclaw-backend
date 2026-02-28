"""
Security Management UI API Endpoints

Provides REST API for managing security components:
- Capability tokens (create, list, revoke, rotate)
- Peer key management (list, get details)
- Audit log queries and exports

Issue #87: Security Management UI Endpoints
Epic E7: Security & Capability Management
"""

import logging
import csv
import json
from io import StringIO
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum

from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# Import security services with availability check
try:
    from backend.security.token_service import TokenService
    from backend.security.peer_key_store import PeerKeyStore
    from backend.services.security_audit_logger import SecurityAuditLogger
    from backend.services.token_rotation_service import TokenRotationService
    from backend.models.capability_token import CapabilityToken, TokenLimits
    from backend.models.audit_event import (
        AuditEvent,
        AuditEventType,
        AuditEventResult,
        AuditQuery,
    )
    SECURITY_AVAILABLE = True
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"Security services not available: {e}")
    SECURITY_AVAILABLE = False


router = APIRouter(prefix="/security", tags=["Security", "Management"])


# ============================================================================
# Request / Response Models
# ============================================================================

class TokenCreateRequest(BaseModel):
    """Request to create a new capability token"""
    peer_id: str = Field(..., min_length=1, description="libp2p peer ID")
    capabilities: List[str] = Field(
        ..., min_length=1, description="List of capabilities to grant"
    )
    max_gpu_minutes: int = Field(..., ge=0, description="Maximum GPU minutes")
    max_concurrent_tasks: int = Field(..., ge=0, description="Max concurrent tasks")
    data_scope: Optional[List[str]] = Field(
        default=None, description="Allowed project IDs (empty = all)"
    )
    expires_in_seconds: int = Field(
        default=3600, ge=60, description="Token lifetime in seconds"
    )


class TokenResponse(BaseModel):
    """Response containing token details"""
    jti: Optional[str] = Field(None, description="Full JTI (only on creation)")
    jti_masked: str = Field(..., description="Masked JTI for display")
    peer_id: str
    capabilities: List[str]
    max_gpu_minutes: int
    max_concurrent_tasks: int
    data_scope: List[str]
    expires_at: int
    is_expired: bool
    expires_in_seconds: int
    parent_jti: Optional[str] = None


class TokenListResponse(BaseModel):
    """Response containing list of tokens"""
    tokens: List[TokenResponse]
    total: int


class TokenCreatedResponse(BaseModel):
    """Response after creating a token"""
    jti: str
    jti_masked: str
    peer_id: str
    capabilities: List[str]
    expires_at: int
    token: str = Field(..., description="JWT token string")


class TokenRevokedResponse(BaseModel):
    """Response after revoking a token"""
    revoked: bool
    jti: str
    reason: Optional[str] = None


class PeerKeyResponse(BaseModel):
    """Response containing peer key summary"""
    peer_id: str
    public_key_fingerprint: str
    registered_at: str
    last_verified_at: Optional[str] = None
    verification_count: int = 0


class PeerKeyListResponse(BaseModel):
    """Response containing list of peer keys"""
    peer_keys: List[PeerKeyResponse]
    total: int


class PeerKeyDetailsResponse(BaseModel):
    """Response containing detailed peer key info"""
    peer_id: str
    public_key_fingerprint: str
    public_key_bytes: Optional[str] = None
    registered_at: str
    last_verified_at: Optional[str] = None
    verification_count: int = 0


class AuditLogQueryParams(BaseModel):
    """Query parameters for audit logs"""
    peer_id: Optional[str] = None
    event_type: Optional[str] = None
    result: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class AuditEventResponse(BaseModel):
    """Response containing audit event"""
    timestamp: str
    event_type: str
    peer_id: str
    action: str
    resource: Optional[str] = None
    result: str
    reason: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AuditLogResponse(BaseModel):
    """Response containing list of audit events"""
    events: List[AuditEventResponse]
    total: int
    limit: int
    offset: int


class ExportFormat(str, Enum):
    """Export format options"""
    JSON = "json"
    CSV = "csv"


# ============================================================================
# Helper Functions (Service Layer Mocks for Testing)
# ============================================================================

def get_all_tokens(peer_id: Optional[str] = None, expired: Optional[bool] = None) -> List[CapabilityToken]:
    """Get all capability tokens with optional filters"""
    # This would be implemented by actual service
    # For now, return empty list for testing
    return []


def create_token(request: TokenCreateRequest) -> CapabilityToken:
    """Create a new capability token"""
    # This would be implemented by actual TokenService
    expires_at = int((datetime.utcnow() + timedelta(seconds=request.expires_in_seconds)).timestamp())

    limits = TokenLimits(
        max_gpu_minutes=request.max_gpu_minutes,
        max_concurrent_tasks=request.max_concurrent_tasks
    )

    return CapabilityToken.create(
        peer_id=request.peer_id,
        capabilities=request.capabilities,
        limits=limits,
        data_scope=request.data_scope,
        expires_in_seconds=request.expires_in_seconds
    )


def encode_token(token: CapabilityToken) -> str:
    """Encode token to JWT string"""
    # This would use actual TokenService
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.mock.token"


def revoke_token(jti: str, reason: Optional[str] = None) -> bool:
    """Revoke a capability token"""
    # This would be implemented by actual TokenRotationService
    return True


def rotate_token(jti: str, extends_by: Optional[int] = None) -> CapabilityToken:
    """Rotate a capability token"""
    # This would be implemented by actual TokenRotationService
    raise ValueError("Token not found")


def get_all_peer_keys() -> List[Dict[str, Any]]:
    """Get all registered peer keys"""
    # This would be implemented by actual PeerKeyStore
    return []


def get_peer_key_details(peer_id: str) -> Optional[Dict[str, Any]]:
    """Get detailed peer key information"""
    # This would be implemented by actual PeerKeyStore
    return None


def query_audit_logs(params: AuditLogQueryParams) -> Dict[str, Any]:
    """Query audit logs with filters"""
    # This would be implemented by actual SecurityAuditLogger
    return {
        "events": [],
        "total": 0,
        "limit": params.limit,
        "offset": params.offset
    }


def export_audit_logs(params: AuditLogQueryParams, format: ExportFormat) -> str:
    """Export audit logs in specified format"""
    # This would be implemented by actual SecurityAuditLogger
    if format == ExportFormat.JSON:
        return "[]"
    else:  # CSV
        return "timestamp,event_type,peer_id,action,result,reason\n"


def mask_jti(jti: str) -> str:
    """Mask JTI for display (first 8 chars + ***)"""
    if len(jti) <= 8:
        return jti + "***"
    return jti[:8] + "***"


# ============================================================================
# Capability Token Endpoints
# ============================================================================

@router.get(
    "/tokens",
    response_model=TokenListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all capability tokens",
    description="Get list of all capability tokens with optional filtering by peer_id or expiration status"
)
async def list_capability_tokens(
    peer_id: Optional[str] = Query(None, description="Filter by peer ID"),
    expired: Optional[bool] = Query(None, description="Filter by expiration status")
) -> TokenListResponse:
    """List all capability tokens"""
    try:
        tokens = get_all_tokens(peer_id=peer_id, expired=expired)

        token_responses = []
        for token in tokens:
            token_responses.append(TokenResponse(
                jti=None,  # Don't expose full JTI in list
                jti_masked=mask_jti(token.jti),
                peer_id=token.peer_id,
                capabilities=token.capabilities,
                max_gpu_minutes=token.limits.max_gpu_minutes,
                max_concurrent_tasks=token.limits.max_concurrent_tasks,
                data_scope=token.data_scope,
                expires_at=token.expires_at,
                is_expired=token.is_expired(),
                expires_in_seconds=token.expires_in_seconds(),
                parent_jti=token.parent_jti
            ))

        return TokenListResponse(tokens=token_responses, total=len(token_responses))

    except Exception as e:
        logger.error(f"Error listing tokens: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/tokens",
    response_model=TokenCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new capability token",
    description="Create a new capability token with specified capabilities and resource limits"
)
async def create_capability_token(request: TokenCreateRequest) -> TokenCreatedResponse:
    """Create a new capability token"""
    try:
        # Create token model
        token = create_token(request)

        # Encode to JWT
        jwt_string = encode_token(token)

        return TokenCreatedResponse(
            jti=token.jti,
            jti_masked=mask_jti(token.jti),
            peer_id=token.peer_id,
            capabilities=token.capabilities,
            expires_at=token.expires_at,
            token=jwt_string
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete(
    "/tokens/{jti}",
    response_model=TokenRevokedResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke a capability token",
    description="Revoke a capability token by its JTI"
)
async def revoke_capability_token(
    jti: str,
    reason: Optional[str] = Query(None, description="Revocation reason")
) -> TokenRevokedResponse:
    """Revoke a capability token"""
    try:
        success = revoke_token(jti, reason=reason)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Token with JTI '{jti}' not found"
            )

        return TokenRevokedResponse(revoked=True, jti=jti, reason=reason)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/tokens/{jti}/rotate",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate a capability token",
    description="Create a new token with same capabilities, linking to original via parent_jti"
)
async def rotate_capability_token(
    jti: str,
    extends_by: Optional[int] = Query(None, ge=60, description="Extend expiration by seconds")
) -> TokenResponse:
    """Rotate a capability token"""
    try:
        new_token = rotate_token(jti, extends_by=extends_by)

        return TokenResponse(
            jti=new_token.jti,
            jti_masked=mask_jti(new_token.jti),
            peer_id=new_token.peer_id,
            capabilities=new_token.capabilities,
            max_gpu_minutes=new_token.limits.max_gpu_minutes,
            max_concurrent_tasks=new_token.limits.max_concurrent_tasks,
            data_scope=new_token.data_scope,
            expires_at=new_token.expires_at,
            is_expired=new_token.is_expired(),
            expires_in_seconds=new_token.expires_in_seconds(),
            parent_jti=new_token.parent_jti
        )

    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error rotating token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# Peer Key Management Endpoints
# ============================================================================

@router.get(
    "/peer-keys",
    response_model=PeerKeyListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all peer public keys",
    description="Get list of all registered peer public keys with fingerprints"
)
async def list_peer_keys() -> PeerKeyListResponse:
    """List all peer public keys"""
    try:
        peer_keys = get_all_peer_keys()

        key_responses = [PeerKeyResponse(**key) for key in peer_keys]

        return PeerKeyListResponse(peer_keys=key_responses, total=len(key_responses))

    except Exception as e:
        logger.error(f"Error listing peer keys: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/peer-keys/{peer_id}",
    response_model=PeerKeyDetailsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get peer key details",
    description="Get detailed information about a specific peer's public key"
)
async def get_peer_key(peer_id: str) -> PeerKeyDetailsResponse:
    """Get detailed peer key information"""
    try:
        key_details = get_peer_key_details(peer_id)

        if key_details is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Peer key for '{peer_id}' not found"
            )

        return PeerKeyDetailsResponse(**key_details)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting peer key: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# Audit Log Endpoints
# ============================================================================

@router.get(
    "/audit-logs",
    response_model=AuditLogResponse,
    status_code=status.HTTP_200_OK,
    summary="Query audit logs",
    description="Query security audit logs with filtering and pagination"
)
async def get_audit_logs(
    peer_id: Optional[str] = Query(None, description="Filter by peer ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    result: Optional[str] = Query(None, description="Filter by result status"),
    start_time: Optional[str] = Query(None, description="Start time (ISO 8601)"),
    end_time: Optional[str] = Query(None, description="End time (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset")
) -> AuditLogResponse:
    """Query audit logs"""
    try:
        params = AuditLogQueryParams(
            peer_id=peer_id,
            event_type=event_type,
            result=result,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )

        result_data = query_audit_logs(params)

        # Convert events to response format
        event_responses = []
        for event in result_data.get("events", []):
            if isinstance(event, dict):
                event_responses.append(AuditEventResponse(**event))
            else:
                # Handle AuditEvent objects
                event_responses.append(AuditEventResponse(
                    timestamp=event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else event.timestamp,
                    event_type=event.event_type.value if hasattr(event.event_type, 'value') else event.event_type,
                    peer_id=event.peer_id,
                    action=event.action,
                    resource=event.resource,
                    result=event.result.value if hasattr(event.result, 'value') else event.result,
                    reason=event.reason,
                    metadata=event.metadata
                ))

        return AuditLogResponse(
            events=event_responses,
            total=result_data.get("total", 0),
            limit=params.limit,
            offset=params.offset
        )

    except Exception as e:
        logger.error(f"Error querying audit logs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/audit-logs/export",
    status_code=status.HTTP_200_OK,
    summary="Export audit logs",
    description="Export audit logs in JSON or CSV format"
)
async def export_audit_logs_endpoint(
    format: ExportFormat = Query(ExportFormat.JSON, description="Export format"),
    peer_id: Optional[str] = Query(None, description="Filter by peer ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    result: Optional[str] = Query(None, description="Filter by result status"),
    start_time: Optional[str] = Query(None, description="Start time (ISO 8601)"),
    end_time: Optional[str] = Query(None, description="End time (ISO 8601)"),
    limit: int = Query(1000, ge=1, le=10000, description="Max records"),
    offset: int = Query(0, ge=0, description="Offset")
) -> Response:
    """Export audit logs"""
    try:
        params = AuditLogQueryParams(
            peer_id=peer_id,
            event_type=event_type,
            result=result,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )

        export_content = export_audit_logs(params, format)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        if format == ExportFormat.JSON:
            return Response(
                content=export_content,
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename=audit-logs-{timestamp}.json"
                }
            )
        else:  # CSV
            return Response(
                content=export_content,
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=audit-logs-{timestamp}.csv"
                }
            )

    except Exception as e:
        logger.error(f"Error exporting audit logs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
