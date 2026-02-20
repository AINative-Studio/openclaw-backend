"""
Security Audit Logger Service

Provides structured logging of security events including authentication,
authorization, token management, and signature verification events.
Supports both file-based and database storage with query capabilities.

Epic E7-S6: Audit Logging for Security Events
Refs: #48
"""

import json
import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from logging.handlers import RotatingFileHandler

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from backend.models.audit_event import (
    AuditEvent,
    AuditEventType,
    AuditEventResult,
    AuditLogEntry,
    AuditQuery,
)


logger = logging.getLogger(__name__)


class AuditLogStorage(ABC):
    """
    Abstract base class for audit log storage backends.

    Implementations can store audit events in files, databases,
    or external logging systems.
    """

    @abstractmethod
    def store(self, event: AuditEvent) -> None:
        """
        Store an audit event.

        Args:
            event: AuditEvent to store
        """
        pass

    @abstractmethod
    def query(self, query: AuditQuery) -> List[AuditEvent]:
        """
        Query audit events based on filter criteria.

        Args:
            query: Query parameters

        Returns:
            List of matching AuditEvent objects
        """
        pass


class FileAuditLogStorage(AuditLogStorage):
    """
    File-based audit log storage with rotation.

    Stores audit events as JSON lines in rotated log files.
    Supports log rotation by size with configurable retention.

    Attributes:
        log_dir: Directory for log files
        max_bytes: Maximum size per log file (default 100MB)
        backup_count: Number of backup files to retain (default 30)
    """

    def __init__(
        self,
        log_dir: str,
        max_bytes: int = 100 * 1024 * 1024,  # 100MB
        backup_count: int = 30,
    ):
        """
        Initialize file-based audit log storage.

        Args:
            log_dir: Directory for log files
            max_bytes: Maximum bytes per log file
            backup_count: Number of backup files to keep
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "security_audit.log"
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._lock = threading.Lock()

        # Set up rotating file handler
        self._setup_file_handler()

        # In-memory cache for queries (limited to recent events)
        self._event_cache: List[AuditEvent] = []
        self._max_cache_size = 10000

    def _setup_file_handler(self) -> None:
        """Set up rotating file handler for JSON logging"""
        self.file_handler = RotatingFileHandler(
            filename=str(self.log_file),
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8'
        )

        # Use JSON formatter
        self.file_handler.setLevel(logging.INFO)

        # Create logger for audit events
        self.audit_logger = logging.getLogger('security_audit')
        self.audit_logger.setLevel(logging.INFO)
        self.audit_logger.addHandler(self.file_handler)
        self.audit_logger.propagate = False

    def store(self, event: AuditEvent) -> None:
        """
        Store audit event to file as JSON line.

        Args:
            event: AuditEvent to store
        """
        with self._lock:
            # Validate event (raises ValueError if sensitive data found)
            event_dict = event.model_dump()

            # Convert datetime to ISO format
            event_dict['timestamp'] = event.timestamp.isoformat()

            # Log as JSON line
            self.audit_logger.info(json.dumps(event_dict))

            # Add to cache
            self._event_cache.append(event)
            if len(self._event_cache) > self._max_cache_size:
                self._event_cache.pop(0)

    def query(self, query: AuditQuery) -> List[AuditEvent]:
        """
        Query audit events from cache.

        Note: This implementation uses in-memory cache for recent events.
        For full historical queries, use DatabaseAuditLogStorage.

        Args:
            query: Query parameters

        Returns:
            List of matching AuditEvent objects
        """
        with self._lock:
            results = self._event_cache.copy()

        # Filter by peer_id
        if query.peer_id:
            results = [e for e in results if e.peer_id == query.peer_id]

        # Filter by event_type
        if query.event_type:
            results = [e for e in results if e.event_type == query.event_type]

        # Filter by result
        if query.result:
            results = [e for e in results if e.result == query.result]

        # Filter by time range
        if query.start_time:
            results = [e for e in results if e.timestamp >= query.start_time]

        if query.end_time:
            results = [e for e in results if e.timestamp <= query.end_time]

        # Sort by timestamp (newest first)
        results.sort(key=lambda e: e.timestamp, reverse=True)

        # Apply pagination
        start_idx = query.offset
        end_idx = start_idx + query.limit
        return results[start_idx:end_idx]


class DatabaseAuditLogStorage(AuditLogStorage):
    """
    Database-backed audit log storage.

    Stores audit events in PostgreSQL/SQLite for durable storage
    and efficient querying.

    Attributes:
        session: SQLAlchemy database session
    """

    def __init__(self, session: Session):
        """
        Initialize database audit log storage.

        Args:
            session: SQLAlchemy session
        """
        self.session = session

    def store(self, event: AuditEvent) -> None:
        """
        Store audit event to database.

        Args:
            event: AuditEvent to store
        """
        # Create database entry
        db_entry = AuditLogEntry(
            timestamp=event.timestamp,
            event_type=event.event_type.value,
            peer_id=event.peer_id,
            action=event.action,
            resource=event.resource,
            result=event.result.value,
            reason=event.reason,
            event_metadata=event.metadata,
        )

        self.session.add(db_entry)
        self.session.commit()

    def query(self, query: AuditQuery) -> List[AuditEvent]:
        """
        Query audit events from database.

        Args:
            query: Query parameters

        Returns:
            List of matching AuditEvent objects
        """
        # Build query
        db_query = self.session.query(AuditLogEntry)

        # Apply filters
        filters = []

        if query.peer_id:
            filters.append(AuditLogEntry.peer_id == query.peer_id)

        if query.event_type:
            filters.append(AuditLogEntry.event_type == query.event_type.value)

        if query.result:
            filters.append(AuditLogEntry.result == query.result.value)

        if query.start_time:
            filters.append(AuditLogEntry.timestamp >= query.start_time)

        if query.end_time:
            filters.append(AuditLogEntry.timestamp <= query.end_time)

        if filters:
            db_query = db_query.filter(and_(*filters))

        # Order by timestamp (newest first)
        db_query = db_query.order_by(AuditLogEntry.timestamp.desc())

        # Apply pagination
        db_query = db_query.limit(query.limit).offset(query.offset)

        # Execute query
        results = db_query.all()

        # Convert to AuditEvent objects
        events = []
        for entry in results:
            event = AuditEvent(
                timestamp=entry.timestamp,
                event_type=AuditEventType(entry.event_type),
                peer_id=entry.peer_id,
                action=entry.action,
                resource=entry.resource,
                result=AuditEventResult(entry.result),
                reason=entry.reason,
                metadata=entry.event_metadata or {},
            )
            events.append(event)

        return events


class SecurityAuditLogger:
    """
    Security Audit Logger Service

    Central service for logging security events with structured data.
    Supports multiple storage backends and query capabilities.

    Features:
    - Structured JSON logging
    - Event categorization (AUTH, AUTHZ, TOKEN, SIGNATURE)
    - Sensitive data prevention
    - Query/search interface
    - Log rotation
    - Multi-storage support

    Usage:
        # Create logger with file storage
        storage = FileAuditLogStorage(log_dir="/var/log/openclaw")
        audit_logger = SecurityAuditLogger(storage=storage)

        # Log authentication event
        event = AuditEvent(
            event_type=AuditEventType.AUTHENTICATION_SUCCESS,
            peer_id="12D3KooW...",
            action="node_registration",
            result=AuditEventResult.SUCCESS,
            reason="Valid credentials"
        )
        audit_logger.log_event(event)

        # Query events
        events = audit_logger.query_events(
            AuditQuery(peer_id="12D3KooW...")
        )
    """

    def __init__(self, storage: AuditLogStorage):
        """
        Initialize security audit logger.

        Args:
            storage: Storage backend for audit events
        """
        self.storage = storage
        self._lock = threading.Lock()

    def log_event(self, event: AuditEvent) -> None:
        """
        Log a security audit event.

        Thread-safe operation that validates and stores the event.

        Args:
            event: AuditEvent to log

        Raises:
            ValueError: If event contains sensitive data in metadata
        """
        with self._lock:
            try:
                # Store event (validation happens in Pydantic model)
                self.storage.store(event)

                # Log to application logger for monitoring
                logger.info(
                    f"Audit: {event.event_type.value} "
                    f"peer={event.peer_id} result={event.result.value}"
                )

            except ValueError as e:
                # Re-raise validation errors (e.g., sensitive data)
                logger.error(f"Audit log validation failed: {e}")
                raise

            except Exception as e:
                logger.error(f"Failed to store audit event: {e}", exc_info=True)
                raise

    def query_events(self, query: AuditQuery) -> List[AuditEvent]:
        """
        Query audit events based on filter criteria.

        Args:
            query: Query parameters

        Returns:
            List of matching AuditEvent objects
        """
        try:
            return self.storage.query(query)
        except Exception as e:
            logger.error(f"Failed to query audit events: {e}", exc_info=True)
            return []

    def log_authentication(
        self,
        peer_id: str,
        success: bool,
        reason: str,
        metadata: Optional[dict] = None
    ) -> None:
        """
        Convenience method to log authentication events.

        Args:
            peer_id: Peer identifier
            success: Whether authentication succeeded
            reason: Reason for success/failure
            metadata: Additional context
        """
        event = AuditEvent(
            event_type=(
                AuditEventType.AUTHENTICATION_SUCCESS if success
                else AuditEventType.AUTHENTICATION_FAILURE
            ),
            peer_id=peer_id,
            action="authentication",
            result=AuditEventResult.SUCCESS if success else AuditEventResult.FAILURE,
            reason=reason,
            metadata=metadata or {}
        )
        self.log_event(event)

    def log_authorization(
        self,
        peer_id: str,
        action: str,
        resource: Optional[str],
        granted: bool,
        reason: str,
        metadata: Optional[dict] = None
    ) -> None:
        """
        Convenience method to log authorization events.

        Args:
            peer_id: Peer identifier
            action: Action being authorized
            resource: Resource being accessed
            granted: Whether access was granted
            reason: Reason for grant/denial
            metadata: Additional context
        """
        event = AuditEvent(
            event_type=(
                AuditEventType.AUTHORIZATION_SUCCESS if granted
                else AuditEventType.AUTHORIZATION_FAILURE
            ),
            peer_id=peer_id,
            action=action,
            resource=resource,
            result=AuditEventResult.SUCCESS if granted else AuditEventResult.DENIED,
            reason=reason,
            metadata=metadata or {}
        )
        self.log_event(event)

    def log_token_event(
        self,
        peer_id: str,
        event_type: AuditEventType,
        reason: str,
        metadata: Optional[dict] = None
    ) -> None:
        """
        Convenience method to log token events.

        Args:
            peer_id: Peer identifier
            event_type: TOKEN_ISSUED, TOKEN_RENEWED, or TOKEN_REVOKED
            reason: Reason for token operation
            metadata: Additional context (NEVER include actual token)
        """
        if event_type not in [
            AuditEventType.TOKEN_ISSUED,
            AuditEventType.TOKEN_RENEWED,
            AuditEventType.TOKEN_REVOKED
        ]:
            raise ValueError(f"Invalid token event type: {event_type}")

        event = AuditEvent(
            event_type=event_type,
            peer_id=peer_id,
            action="token_management",
            result=AuditEventResult.SUCCESS,
            reason=reason,
            metadata=metadata or {}
        )
        self.log_event(event)

    def log_signature_verification(
        self,
        peer_id: str,
        valid: bool,
        reason: str,
        metadata: Optional[dict] = None
    ) -> None:
        """
        Convenience method to log signature verification events.

        Args:
            peer_id: Peer identifier
            valid: Whether signature was valid
            reason: Reason for verification result
            metadata: Additional context (NEVER include signature)
        """
        event = AuditEvent(
            event_type=(
                AuditEventType.SIGNATURE_VERIFIED if valid
                else AuditEventType.SIGNATURE_FAILED
            ),
            peer_id=peer_id,
            action="signature_verification",
            result=AuditEventResult.VERIFIED if valid else AuditEventResult.INVALID,
            reason=reason,
            metadata=metadata or {}
        )
        self.log_event(event)
