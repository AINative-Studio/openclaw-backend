"""
Security Management UI Endpoints

Provides REST API for managing capability tokens, peer keys, and audit logs.
Designed for the /security page in the UI dashboard.

Epic E7: Security Management UI Integration
Refs: #87
"""

import logging
import csv
import hashlib
import base64
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, status, Depends, Query, Response
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.models.capability_token import CapabilityToken, TokenLimits
from backend.models.token_revocation import TokenRevocation
from backend.models.audit_event import (
    AuditEventType,
    AuditEventResult,
    AuditQuery,
    AuditLogEntry,
)
from backend.security.token_service import TokenService
from backend.security.peer_key_store import PeerKeyStore
from backend.services.token_rotation_service import TokenRotationService
from backend.services.security_audit_logger import (
    SecurityAuditLogger,
    DatabaseAuditLogStorage,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security", tags=["Security", "Management"])


# ============================================================================
# Dependency Injection
# ============================================================================

def get_token_service() -> TokenService:
    """Get token service instance"""
    import os
    secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    return TokenService(secret_key=secret_key, algorithm="HS256")


def get_peer_key_store() -> PeerKeyStore:
    """Get peer key store instance (singleton)"""
    if not hasattr(get_peer_key_store, "_instance"):
        get_peer_key_store._instance = PeerKeyStore()
    return get_peer_key_store._instance


def get_audit_logger(db: Session = Depends(get_db)) -> SecurityAuditLogger:
    """Get security audit logger instance"""
    storage = DatabaseAuditLogStorage(session=db)
    return SecurityAuditLogger(storage=storage)


# ============================================================================
# Request/Response Models
# ============================================================================

class TokenCreateRequest(BaseModel):
    """Request model for creating a new capability token"""
    peer_id: str = Field(..., min_length=1, description="Peer ID")
    capabilities: List[str] = Field(..., min_length=1, description="List of capabilities")
    limits: TokenLimits = Field(..., description="Resource limits")
    data_scope: Optional[List[str]] = Field(default=None, description="Allowed project IDs")
    expires_in_seconds: int = Field(default=3600, ge=60, description="Token lifetime in seconds")


class TokenResponse(BaseModel):
    """Response model for token with masked JTI"""
    jti: str = Field(..., description="Full JTI (only in create/rotate responses)")
    jti_masked: str = Field(..., description="Masked JTI for display")
    peer_id: str
    capabilities: List[str]
    limits: TokenLimits
    data_scope: List[str]
    expires_at: int = Field(..., description="Unix timestamp")
    is_expired: bool
    expires_in_seconds: int
    parent_jti: Optional[str] = None

    @classmethod
    def from_token(cls, token: CapabilityToken, include_full_jti: bool = False):
        """Create response from CapabilityToken"""
        jti_masked = cls.mask_jti(token.jti)

        return cls(
            jti=token.jti if include_full_jti else jti_masked,
            jti_masked=jti_masked,
            peer_id=token.peer_id,
            capabilities=token.capabilities,
            limits=token.limits,
            data_scope=token.data_scope,
            expires_at=token.expires_at,
            is_expired=token.is_expired(),
            expires_in_seconds=token.expires_in_seconds(),
            parent_jti=token.parent_jti
        )

    @staticmethod
    def mask_jti(jti: str) -> str:
        """Mask JTI: show first 8 and last 8 characters"""
        if len(jti) <= 16:
            return jti[:4] + "***" + jti[-4:]
        return jti[:8] + "..." + jti[-8:]


class TokenListResponse(BaseModel):
    """Response model for token list"""
    total: int
    tokens: List[TokenResponse]
    limit: int = 100
    offset: int = 0


class TokenCreateResponse(TokenResponse):
    """Response model for token creation (includes JWT)"""
    jwt_token: str = Field(..., description="Actual JWT token (use immediately)")


class TokenRevokeResponse(BaseModel):
    """Response model for token revocation"""
    success: bool
    jti: str
    reason: str
    revoked_at: datetime


class TokenRotateResponse(BaseModel):
    """Response model for token rotation"""
    old_jti: str
    new_jti: str
    new_jti_masked: str
    new_jwt_token: str
    peer_id: str
    capabilities: List[str]
    new_expires_at: int
    revocation_reason: str = "rotation"


class PeerKeyResponse(BaseModel):
    """Response model for peer key"""
    peer_id: str
    fingerprint: str = Field(..., description="SHA-256 fingerprint (hex)")
    algorithm: str = "Ed25519"
    public_key_bytes: Optional[str] = Field(None, description="Base64 encoded public key")
    stored_at: Optional[datetime] = None


class PeerKeyListResponse(BaseModel):
    """Response model for peer key list"""
    total: int
    peer_keys: List[PeerKeyResponse]


class AuditEventResponse(BaseModel):
    """Response model for audit event"""
    timestamp: datetime
    event_type: str
    peer_id: str
    action: str
    resource: Optional[str]
    result: str
    reason: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AuditLogQueryResponse(BaseModel):
    """Response model for audit log query"""
    total: int
    events: List[AuditEventResponse]
    limit: int
    offset: int


class AuditLogExportResponse(BaseModel):
    """Response model for audit log export (JSON format)"""
    format: str = "json"
    exported_at: datetime
    total_events: int
    events: List[AuditEventResponse]


# ============================================================================
# Token Management Endpoints
# ============================================================================

@router.get("/tokens", response_model=TokenListResponse)
async def list_tokens(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db)
):
    """
    List all capability tokens with masked JTIs

    Returns paginated list of tokens with expiration status.
    JTIs are masked for security (first 8 + last 8 chars).
    """
    try:
        # Query token revocations to build token list
        # Note: In production, tokens should be stored in DB
        # For now, we return revocations as a proxy
        revocations = db.query(TokenRevocation).order_by(
            TokenRevocation.revoked_at.desc()
        ).limit(limit).offset(offset).all()

        total = db.query(TokenRevocation).count()

        tokens = []
        # Note: This is a placeholder. In production, you'd query active tokens
        # from a tokens table, not revocations.
        # For demo purposes, we return empty list if no revocations exist.

        return TokenListResponse(
            total=total,
            tokens=tokens,
            limit=limit,
            offset=offset
        )

    except Exception as e:
        logger.error(f"Failed to list tokens: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tokens: {str(e)}"
        )


@router.post("/tokens", response_model=TokenCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
    request: TokenCreateRequest,
    token_service: TokenService = Depends(get_token_service),
    db: Session = Depends(get_db)
):
    """
    Create a new capability token

    Issues a new JWT token with specified capabilities and limits.
    Returns both the token metadata and the actual JWT for immediate use.
    """
    try:
        # Create capability token
        token = CapabilityToken.create(
            peer_id=request.peer_id,
            capabilities=request.capabilities,
            limits=request.limits,
            data_scope=request.data_scope or [],
            expires_in_seconds=request.expires_in_seconds
        )

        # Encode to JWT
        jwt_token = token_service.encode_token(token)

        # Create response with full JTI and JWT
        response_data = TokenResponse.from_token(token, include_full_jti=True)

        return TokenCreateResponse(
            **response_data.model_dump(),
            jwt_token=jwt_token
        )

    except ValueError as e:
        logger.warning(f"Token creation validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to create token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create token: {str(e)}"
        )


@router.delete("/tokens/{jti}", response_model=TokenRevokeResponse)
async def revoke_token(
    jti: str,
    reason: str = Query(default="manual", description="Revocation reason"),
    db: Session = Depends(get_db)
):
    """
    Revoke a capability token

    Adds token to revocation list, preventing further use.
    Tokens remain revoked for 30 days for audit purposes.
    """
    try:
        # Check if token already revoked
        existing = db.query(TokenRevocation).filter(
            TokenRevocation.jti == jti
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Token {jti} is already revoked"
            )

        # For demo: assume token expires in 1 hour from now
        # In production, you'd look up the actual token expiration
        expires_at = datetime.utcnow() + timedelta(hours=1)

        # Create revocation
        revocation = TokenRevocation.create(
            jti=jti,
            expires_at=expires_at,
            reason=reason
        )

        db.add(revocation)
        db.commit()

        logger.info(f"Token revoked: {jti}, reason: {reason}")

        return TokenRevokeResponse(
            success=True,
            jti=jti,
            reason=reason,
            revoked_at=revocation.revoked_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to revoke token: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke token: {str(e)}"
        )


@router.post("/tokens/{jti}/rotate", response_model=TokenRotateResponse)
async def rotate_token(
    jti: str,
    extends_by_seconds: int = Query(default=3600, ge=60, description="Extension period"),
    token_service: TokenService = Depends(get_token_service),
    db: Session = Depends(get_db)
):
    """
    Rotate a capability token

    Creates a new token with extended expiration and same capabilities.
    Old token is revoked with grace period for smooth transition.
    """
    try:
        # In production, look up the original token from database
        # For demo, we'll return 404 if token doesn't exist
        # (tokens aren't stored in this implementation)

        # Check if token is already revoked
        revoked = db.query(TokenRevocation).filter(
            TokenRevocation.jti == jti
        ).first()

        if revoked:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Token {jti} not found or already revoked"
            )

        # For demo: simulate token lookup failure
        # In production, you'd fetch the actual token from database
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Token {jti} not found. Note: Token storage not implemented in this demo."
        )

        # Production implementation would be:
        # rotation_service = TokenRotationService(db)
        # original_token = lookup_token_from_db(jti)
        # new_token = await rotation_service.renew_token(
        #     original_token,
        #     extends_by_seconds=extends_by_seconds
        # )
        # new_jwt = token_service.encode_token(new_token)
        #
        # return TokenRotateResponse(
        #     old_jti=jti,
        #     new_jti=new_token.jti,
        #     new_jti_masked=TokenResponse.mask_jti(new_token.jti),
        #     new_jwt_token=new_jwt,
        #     peer_id=new_token.peer_id,
        #     capabilities=new_token.capabilities,
        #     new_expires_at=new_token.expires_at
        # )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rotate token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rotate token: {str(e)}"
        )


# ============================================================================
# Peer Key Management Endpoints
# ============================================================================

@router.get("/peer-keys", response_model=PeerKeyListResponse)
async def list_peer_keys(
    key_store: PeerKeyStore = Depends(get_peer_key_store)
):
    """
    List all peer public keys

    Returns list of peer IDs with their Ed25519 public key fingerprints.
    Fingerprints are SHA-256 hashes of the public key bytes.
    """
    try:
        peer_ids = key_store.get_all_peer_ids()

        peer_keys = []
        for peer_id in peer_ids:
            public_key_bytes = key_store.export_public_key_bytes(peer_id)
            if public_key_bytes:
                fingerprint = hashlib.sha256(public_key_bytes).hexdigest()

                peer_keys.append(PeerKeyResponse(
                    peer_id=peer_id,
                    fingerprint=fingerprint,
                    algorithm="Ed25519"
                ))

        return PeerKeyListResponse(
            total=len(peer_keys),
            peer_keys=peer_keys
        )

    except Exception as e:
        logger.error(f"Failed to list peer keys: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list peer keys: {str(e)}"
        )


@router.get("/peer-keys/{peer_id}", response_model=PeerKeyResponse)
async def get_peer_key(
    peer_id: str,
    key_store: PeerKeyStore = Depends(get_peer_key_store)
):
    """
    Get peer public key details

    Returns public key fingerprint, algorithm, and optionally the raw key bytes.
    Fingerprint is SHA-256 hash of public key for verification.
    """
    try:
        public_key_bytes = key_store.export_public_key_bytes(peer_id)

        if not public_key_bytes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Peer key not found for {peer_id}"
            )

        fingerprint = hashlib.sha256(public_key_bytes).hexdigest()
        public_key_b64 = base64.b64encode(public_key_bytes).decode('utf-8')

        return PeerKeyResponse(
            peer_id=peer_id,
            fingerprint=fingerprint,
            algorithm="Ed25519",
            public_key_bytes=public_key_b64,
            stored_at=datetime.now(timezone.utc)  # Placeholder
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get peer key: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get peer key: {str(e)}"
        )


# ============================================================================
# Audit Log Endpoints
# ============================================================================

@router.get("/audit-logs", response_model=AuditLogQueryResponse)
async def query_audit_logs(
    peer_id: Optional[str] = Query(None, description="Filter by peer ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    result: Optional[str] = Query(None, description="Filter by result"),
    start_time: Optional[datetime] = Query(None, description="Filter by start time (ISO 8601)"),
    end_time: Optional[datetime] = Query(None, description="Filter by end time (ISO 8601)"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    audit_logger: SecurityAuditLogger = Depends(get_audit_logger)
):
    """
    Query audit logs with filters

    Supports filtering by peer_id, event_type, result, and date range.
    Returns paginated results ordered by timestamp (newest first).
    """
    try:
        # Build query
        event_type_enum = None
        if event_type:
            try:
                event_type_enum = AuditEventType(event_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid event_type: {event_type}"
                )

        result_enum = None
        if result:
            try:
                result_enum = AuditEventResult(result)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid result: {result}"
                )

        query = AuditQuery(
            peer_id=peer_id,
            event_type=event_type_enum,
            result=result_enum,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )

        # Execute query
        events = audit_logger.query_events(query)

        # Convert to response models
        event_responses = [
            AuditEventResponse(
                timestamp=event.timestamp,
                event_type=event.event_type.value,
                peer_id=event.peer_id,
                action=event.action,
                resource=event.resource,
                result=event.result.value,
                reason=event.reason,
                metadata=event.metadata
            )
            for event in events
        ]

        # Get total count (for pagination)
        # Note: This is approximate. In production, you'd run a count query
        total = len(event_responses)

        return AuditLogQueryResponse(
            total=total,
            events=event_responses,
            limit=limit,
            offset=offset
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to query audit logs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query audit logs: {str(e)}"
        )


@router.get("/audit-logs/export")
async def export_audit_logs(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    peer_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(default=1000, ge=1, le=1000),
    audit_logger: SecurityAuditLogger = Depends(get_audit_logger)
):
    """
    Export audit logs in JSON or CSV format

    Supports same filters as query endpoint.
    Returns downloadable file with appropriate Content-Type and filename.
    """
    try:
        # Validate format
        if format not in ["json", "csv"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid format: {format}. Must be 'json' or 'csv'."
            )

        # Build query
        event_type_enum = None
        if event_type:
            try:
                event_type_enum = AuditEventType(event_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid event_type: {event_type}"
                )

        result_enum = None
        if result:
            try:
                result_enum = AuditEventResult(result)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid result: {result}"
                )

        query = AuditQuery(
            peer_id=peer_id,
            event_type=event_type_enum,
            result=result_enum,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=0
        )

        # Execute query
        events = audit_logger.query_events(query)

        # Generate timestamp for filename
        export_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        if format == "json":
            # Export as JSON
            event_dicts = [
                {
                    "timestamp": event.timestamp.isoformat(),
                    "event_type": event.event_type.value,
                    "peer_id": event.peer_id,
                    "action": event.action,
                    "resource": event.resource,
                    "result": event.result.value,
                    "reason": event.reason,
                    "metadata": event.metadata
                }
                for event in events
            ]

            export_data = AuditLogExportResponse(
                format="json",
                exported_at=datetime.now(timezone.utc),
                total_events=len(events),
                events=[
                    AuditEventResponse(**event_dict)
                    for event_dict in event_dicts
                ]
            )

            return JSONResponse(
                content=export_data.model_dump(mode='json'),
                headers={
                    "Content-Disposition": f"attachment; filename=audit_logs_{export_timestamp}.json"
                }
            )

        else:  # format == "csv"
            # Export as CSV
            output = StringIO()
            fieldnames = [
                "timestamp",
                "event_type",
                "peer_id",
                "action",
                "resource",
                "result",
                "reason"
            ]
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()

            for event in events:
                writer.writerow({
                    "timestamp": event.timestamp.isoformat(),
                    "event_type": event.event_type.value,
                    "peer_id": event.peer_id,
                    "action": event.action,
                    "resource": event.resource or "",
                    "result": event.result.value,
                    "reason": event.reason
                })

            csv_content = output.getvalue()

            return Response(
                content=csv_content,
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=audit_logs_{export_timestamp}.csv"
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export audit logs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export audit logs: {str(e)}"
        )
