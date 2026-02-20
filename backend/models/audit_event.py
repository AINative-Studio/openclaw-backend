"""
Security Audit Event Models

Defines data models for security audit logging including event types,
structured event data, and database schema for audit trail storage.

Epic E7-S6: Audit Logging for Security Events
Refs: #48
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    Column,
    String,
    DateTime,
    JSON,
    Integer,
    Index,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

# Create Base for audit models
Base = declarative_base()


class AuditEventType(str, Enum):
    """Security audit event types"""
    AUTHENTICATION_SUCCESS = "AUTHENTICATION_SUCCESS"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    AUTHORIZATION_SUCCESS = "AUTHORIZATION_SUCCESS"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
    TOKEN_ISSUED = "TOKEN_ISSUED"
    TOKEN_RENEWED = "TOKEN_RENEWED"
    TOKEN_REVOKED = "TOKEN_REVOKED"
    SIGNATURE_VERIFIED = "SIGNATURE_VERIFIED"
    SIGNATURE_FAILED = "SIGNATURE_FAILED"


class AuditEventResult(str, Enum):
    """Audit event result status"""
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    VERIFIED = "verified"
    INVALID = "invalid"


class AuditEvent(BaseModel):
    """
    Security Audit Event Model

    Represents a security-relevant event with structured metadata
    for audit trail and compliance purposes.

    Attributes:
        timestamp: ISO8601 timestamp of event occurrence
        event_type: Category of security event
        peer_id: Identifier of the peer involved in the event
        action: The action attempted (e.g., task_assignment, message_send)
        resource: The resource being accessed (optional)
        result: Outcome of the event
        reason: Human-readable explanation of the result
        metadata: Additional context-specific data
    """
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: AuditEventType
    peer_id: str = Field(..., min_length=1, max_length=255)
    action: str = Field(..., min_length=1, max_length=255)
    resource: Optional[str] = Field(None, max_length=255)
    result: AuditEventResult
    reason: str = Field(..., min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('metadata')
    @classmethod
    def validate_no_sensitive_data(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate that metadata does not contain sensitive data.

        Security rule: Never log tokens, passwords, PII, or sensitive keys.
        """
        sensitive_keys = {
            'token', 'password', 'secret', 'api_key', 'private_key',
            'access_token', 'refresh_token', 'jwt', 'credential',
            'ssn', 'social_security', 'credit_card', 'cvv'
        }

        # Check for sensitive keys (case-insensitive)
        for key in v.keys():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                raise ValueError(
                    f"Metadata contains sensitive key '{key}'. "
                    "Never log tokens, passwords, or PII."
                )

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2026-02-20T08:00:00Z",
                "event_type": "AUTHORIZATION_FAILURE",
                "peer_id": "12D3KooW...",
                "action": "task_assignment",
                "resource": "task_123",
                "result": "denied",
                "reason": "missing_capability:can_execute:llama-2-7b",
                "metadata": {
                    "task_id": "task_123",
                    "required_capability": "can_execute:llama-2-7b",
                    "available_capabilities": ["can_execute:gpt-3.5-turbo"]
                }
            }
        }


class AuditLogEntry(Base):
    """
    AuditLogEntry Database Model

    Persistent storage for security audit events.
    Supports querying by peer_id, event_type, and timestamp.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    peer_id = Column(String(255), nullable=False, index=True)
    action = Column(String(255), nullable=False)
    resource = Column(String(255), nullable=True)
    result = Column(String(20), nullable=False)
    reason = Column(String(1000), nullable=False)
    event_metadata = Column(JSON, nullable=True)
    created_at = Column(
        DateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )

    # Composite indexes for common query patterns
    __table_args__ = (
        Index('ix_audit_logs_peer_timestamp', 'peer_id', 'timestamp'),
        Index('ix_audit_logs_type_timestamp', 'event_type', 'timestamp'),
        Index('ix_audit_logs_result_timestamp', 'result', 'timestamp'),
    )

    def __repr__(self):
        return (
            f"<AuditLogEntry {self.event_type} "
            f"peer={self.peer_id} result={self.result}>"
        )


class AuditQuery(BaseModel):
    """
    Audit Log Query Parameters

    Supports filtering and searching audit logs.
    """
    peer_id: Optional[str] = None
    event_type: Optional[AuditEventType] = None
    result: Optional[AuditEventResult] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

    class Config:
        json_schema_extra = {
            "example": {
                "peer_id": "12D3KooW...",
                "event_type": "AUTHORIZATION_FAILURE",
                "start_time": "2026-02-19T00:00:00Z",
                "end_time": "2026-02-20T00:00:00Z",
                "limit": 50
            }
        }
