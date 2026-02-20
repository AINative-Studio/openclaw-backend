"""
Unit Tests for Security Audit Logger Service

Tests audit logging functionality including event recording,
structured logging, query interface, and log rotation.

Epic E7-S6: Audit Logging for Security Events
Refs: #48
"""

import pytest
import json
import tempfile
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from backend.services.security_audit_logger import (
    SecurityAuditLogger,
    AuditLogStorage,
    FileAuditLogStorage,
    DatabaseAuditLogStorage,
)
from backend.models.audit_event import (
    AuditEvent,
    AuditEventType,
    AuditEventResult,
    AuditQuery,
)


class TestSecurityAuditLogger:
    """Test SecurityAuditLogger service"""

    @pytest.fixture
    def temp_log_dir(self):
        """Create temporary directory for log files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def file_storage(self, temp_log_dir):
        """Create file-based audit log storage"""
        return FileAuditLogStorage(
            log_dir=temp_log_dir,
            max_bytes=1024 * 1024,  # 1MB for testing
            backup_count=5
        )

    @pytest.fixture
    def logger_service(self, file_storage):
        """Create audit logger service with file storage"""
        return SecurityAuditLogger(storage=file_storage)

    def test_log_authentication_attempt(self, logger_service):
        """
        Given auth attempt, when logging,
        then should record peer_id, timestamp, result
        """
        # Given
        event = AuditEvent(
            event_type=AuditEventType.AUTHENTICATION_SUCCESS,
            peer_id="12D3KooWTest123",
            action="node_registration",
            result=AuditEventResult.SUCCESS,
            reason="Valid credentials provided",
            metadata={
                "registration_time": "2026-02-20T08:00:00Z",
                "capabilities": ["can_execute:llama-2-7b"]
            }
        )

        # When
        logger_service.log_event(event)

        # Then
        events = logger_service.query_events(
            AuditQuery(peer_id="12D3KooWTest123")
        )
        assert len(events) == 1
        assert events[0].event_type == AuditEventType.AUTHENTICATION_SUCCESS
        assert events[0].peer_id == "12D3KooWTest123"
        assert events[0].result == AuditEventResult.SUCCESS
        assert isinstance(events[0].timestamp, datetime)

    def test_log_authentication_failure(self, logger_service):
        """
        Given failed auth attempt, when logging,
        then should record failure details
        """
        # Given
        event = AuditEvent(
            event_type=AuditEventType.AUTHENTICATION_FAILURE,
            peer_id="12D3KooWBadActor",
            action="node_registration",
            result=AuditEventResult.FAILURE,
            reason="Invalid signature",
            metadata={"attempt_count": 3}
        )

        # When
        logger_service.log_event(event)

        # Then
        events = logger_service.query_events(
            AuditQuery(event_type=AuditEventType.AUTHENTICATION_FAILURE)
        )
        assert len(events) == 1
        assert events[0].peer_id == "12D3KooWBadActor"
        assert events[0].reason == "Invalid signature"

    def test_log_authorization_failure(self, logger_service):
        """
        Given capability violation, when logging,
        then should record attempted action and reason
        """
        # Given
        event = AuditEvent(
            event_type=AuditEventType.AUTHORIZATION_FAILURE,
            peer_id="12D3KooWUnauthorized",
            action="task_assignment",
            resource="task_123",
            result=AuditEventResult.DENIED,
            reason="missing_capability:can_execute:llama-2-7b",
            metadata={
                "task_id": "task_123",
                "required_capability": "can_execute:llama-2-7b",
                "available_capabilities": ["can_execute:gpt-3.5-turbo"]
            }
        )

        # When
        logger_service.log_event(event)

        # Then
        events = logger_service.query_events(
            AuditQuery(peer_id="12D3KooWUnauthorized")
        )
        assert len(events) == 1
        assert events[0].event_type == AuditEventType.AUTHORIZATION_FAILURE
        assert events[0].action == "task_assignment"
        assert events[0].resource == "task_123"
        assert events[0].result == AuditEventResult.DENIED
        assert "missing_capability" in events[0].reason

    def test_audit_log_searchable(self, logger_service):
        """
        Given audit logs, when querying by peer_id,
        then should return all events for that peer
        """
        # Given - log multiple events for different peers
        peer_a_events = [
            AuditEvent(
                event_type=AuditEventType.AUTHENTICATION_SUCCESS,
                peer_id="peer_a",
                action="login",
                result=AuditEventResult.SUCCESS,
                reason="Valid auth"
            ),
            AuditEvent(
                event_type=AuditEventType.AUTHORIZATION_SUCCESS,
                peer_id="peer_a",
                action="task_assignment",
                result=AuditEventResult.SUCCESS,
                reason="Capability matched"
            )
        ]

        peer_b_events = [
            AuditEvent(
                event_type=AuditEventType.AUTHENTICATION_SUCCESS,
                peer_id="peer_b",
                action="login",
                result=AuditEventResult.SUCCESS,
                reason="Valid auth"
            )
        ]

        for event in peer_a_events + peer_b_events:
            logger_service.log_event(event)

        # When - query for peer_a
        peer_a_results = logger_service.query_events(
            AuditQuery(peer_id="peer_a")
        )

        # Then - should only return peer_a events
        assert len(peer_a_results) == 2
        assert all(e.peer_id == "peer_a" for e in peer_a_results)

    def test_query_by_event_type(self, logger_service):
        """
        Given audit logs, when querying by event_type,
        then should return only matching events
        """
        # Given
        events = [
            AuditEvent(
                event_type=AuditEventType.TOKEN_ISSUED,
                peer_id="peer_1",
                action="issue_token",
                result=AuditEventResult.SUCCESS,
                reason="Token generated"
            ),
            AuditEvent(
                event_type=AuditEventType.TOKEN_REVOKED,
                peer_id="peer_2",
                action="revoke_token",
                result=AuditEventResult.SUCCESS,
                reason="Token expired"
            ),
            AuditEvent(
                event_type=AuditEventType.TOKEN_ISSUED,
                peer_id="peer_3",
                action="issue_token",
                result=AuditEventResult.SUCCESS,
                reason="Token generated"
            )
        ]

        for event in events:
            logger_service.log_event(event)

        # When
        results = logger_service.query_events(
            AuditQuery(event_type=AuditEventType.TOKEN_ISSUED)
        )

        # Then
        assert len(results) == 2
        assert all(e.event_type == AuditEventType.TOKEN_ISSUED for e in results)

    def test_query_with_time_range(self, logger_service):
        """
        Given audit logs, when querying by time range,
        then should return only events within range
        """
        # Given - create events with different timestamps
        now = datetime.now(timezone.utc)
        old_event = AuditEvent(
            timestamp=now - timedelta(hours=2),
            event_type=AuditEventType.AUTHENTICATION_SUCCESS,
            peer_id="peer_old",
            action="login",
            result=AuditEventResult.SUCCESS,
            reason="Valid auth"
        )

        recent_event = AuditEvent(
            timestamp=now - timedelta(minutes=5),
            event_type=AuditEventType.AUTHENTICATION_SUCCESS,
            peer_id="peer_recent",
            action="login",
            result=AuditEventResult.SUCCESS,
            reason="Valid auth"
        )

        logger_service.log_event(old_event)
        logger_service.log_event(recent_event)

        # When - query for last hour
        results = logger_service.query_events(
            AuditQuery(
                start_time=now - timedelta(hours=1),
                end_time=now
            )
        )

        # Then - should only return recent event
        assert len(results) == 1
        assert results[0].peer_id == "peer_recent"

    def test_log_structured_format(self, logger_service, temp_log_dir):
        """
        Given audit event, when logging,
        then should use structured JSON format
        """
        # Given
        event = AuditEvent(
            event_type=AuditEventType.SIGNATURE_VERIFIED,
            peer_id="12D3KooWTest",
            action="message_verification",
            result=AuditEventResult.VERIFIED,
            reason="Valid signature",
            metadata={"message_id": "msg_123"}
        )

        # When
        logger_service.log_event(event)

        # Then - check log file contains valid JSON
        log_file = Path(temp_log_dir) / "security_audit.log"
        assert log_file.exists()

        with open(log_file, 'r') as f:
            log_line = f.readline()
            log_data = json.loads(log_line)

        assert log_data['event_type'] == "SIGNATURE_VERIFIED"
        assert log_data['peer_id'] == "12D3KooWTest"
        assert log_data['result'] == "verified"
        assert 'timestamp' in log_data
        assert log_data['metadata']['message_id'] == "msg_123"

    def test_log_rotation(self, temp_log_dir):
        """
        Given audit log file at max size, when logging,
        then should rotate to new file
        """
        # Given - create storage with small max_bytes for testing
        storage = FileAuditLogStorage(
            log_dir=temp_log_dir,
            max_bytes=500,  # Small size to trigger rotation
            backup_count=3
        )
        logger_service = SecurityAuditLogger(storage=storage)

        # When - log events until rotation occurs
        for i in range(10):
            event = AuditEvent(
                event_type=AuditEventType.AUTHENTICATION_SUCCESS,
                peer_id=f"peer_{i}",
                action="login",
                result=AuditEventResult.SUCCESS,
                reason="Valid auth with some extra data to increase size"
            )
            logger_service.log_event(event)

        # Then - should have rotated log files
        log_files = list(Path(temp_log_dir).glob("security_audit.log*"))
        assert len(log_files) > 1  # Main log + at least one backup

    def test_prevents_sensitive_data_logging(self, logger_service):
        """
        Given event with sensitive data in metadata,
        when creating event, then should raise validation error
        """
        # When/Then - should raise validation error during event creation
        with pytest.raises(ValueError, match="sensitive key"):
            AuditEvent(
                event_type=AuditEventType.TOKEN_ISSUED,
                peer_id="peer_1",
                action="issue_token",
                result=AuditEventResult.SUCCESS,
                reason="Token generated",
                metadata={"token": "sensitive_token_value"}  # FORBIDDEN
            )

    def test_log_signature_failure(self, logger_service):
        """
        Given signature verification failure, when logging,
        then should record details
        """
        # Given
        event = AuditEvent(
            event_type=AuditEventType.SIGNATURE_FAILED,
            peer_id="12D3KooWBadSig",
            action="message_verification",
            result=AuditEventResult.INVALID,
            reason="Signature mismatch",
            metadata={
                "message_id": "msg_456",
                "expected_signer": "peer_a",
                "claimed_signer": "peer_b"
            }
        )

        # When
        logger_service.log_event(event)

        # Then
        events = logger_service.query_events(
            AuditQuery(event_type=AuditEventType.SIGNATURE_FAILED)
        )
        assert len(events) == 1
        assert events[0].result == AuditEventResult.INVALID

    def test_query_pagination(self, logger_service):
        """
        Given many audit logs, when querying with limit/offset,
        then should return paginated results
        """
        # Given - create 20 events
        for i in range(20):
            event = AuditEvent(
                event_type=AuditEventType.AUTHENTICATION_SUCCESS,
                peer_id=f"peer_{i}",
                action="login",
                result=AuditEventResult.SUCCESS,
                reason="Valid auth"
            )
            logger_service.log_event(event)

        # When - query first page
        page1 = logger_service.query_events(
            AuditQuery(limit=5, offset=0)
        )

        # When - query second page
        page2 = logger_service.query_events(
            AuditQuery(limit=5, offset=5)
        )

        # Then
        assert len(page1) == 5
        assert len(page2) == 5
        # Ensure different results
        page1_peers = {e.peer_id for e in page1}
        page2_peers = {e.peer_id for e in page2}
        assert page1_peers.isdisjoint(page2_peers)

    def test_concurrent_logging(self, logger_service):
        """
        Given multiple threads logging events,
        when logging concurrently, then all events should be recorded
        """
        import threading

        def log_events(peer_id: str, count: int):
            for i in range(count):
                event = AuditEvent(
                    event_type=AuditEventType.AUTHENTICATION_SUCCESS,
                    peer_id=peer_id,
                    action="login",
                    result=AuditEventResult.SUCCESS,
                    reason=f"Auth {i}"
                )
                logger_service.log_event(event)

        # When - log from multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(
                target=log_events,
                args=(f"peer_{i}", 10)
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Then - all events should be recorded
        all_events = logger_service.query_events(AuditQuery(limit=100))
        assert len(all_events) == 30


    def test_log_authentication_convenience_method(self, logger_service):
        """
        Given authentication result, when using convenience method,
        then should log correct event type
        """
        # When - log successful authentication
        logger_service.log_authentication(
            peer_id="peer_1",
            success=True,
            reason="Valid credentials",
            metadata={"attempt": 1}
        )

        # Then
        events = logger_service.query_events(
            AuditQuery(peer_id="peer_1")
        )
        assert len(events) == 1
        assert events[0].event_type == AuditEventType.AUTHENTICATION_SUCCESS

    def test_log_authorization_convenience_method(self, logger_service):
        """
        Given authorization decision, when using convenience method,
        then should log correct event type
        """
        # When - log denied authorization
        logger_service.log_authorization(
            peer_id="peer_1",
            action="task_assignment",
            resource="task_123",
            granted=False,
            reason="Missing capability",
            metadata={"required": "can_execute:llama-2-7b"}
        )

        # Then
        events = logger_service.query_events(
            AuditQuery(peer_id="peer_1")
        )
        assert len(events) == 1
        assert events[0].event_type == AuditEventType.AUTHORIZATION_FAILURE
        assert events[0].result == AuditEventResult.DENIED

    def test_log_token_event_convenience_method(self, logger_service):
        """
        Given token operation, when using convenience method,
        then should log correct event type
        """
        # When - log token issuance
        logger_service.log_token_event(
            peer_id="peer_1",
            event_type=AuditEventType.TOKEN_ISSUED,
            reason="New token generated"
        )

        # Then
        events = logger_service.query_events(
            AuditQuery(event_type=AuditEventType.TOKEN_ISSUED)
        )
        assert len(events) == 1

    def test_log_token_event_invalid_type(self, logger_service):
        """
        Given invalid event type for token, when using convenience method,
        then should raise ValueError
        """
        # When/Then - should raise error for non-token event type
        with pytest.raises(ValueError, match="Invalid token event type"):
            logger_service.log_token_event(
                peer_id="peer_1",
                event_type=AuditEventType.AUTHENTICATION_SUCCESS,  # WRONG TYPE
                reason="Test"
            )

    def test_log_signature_verification_convenience_method(self, logger_service):
        """
        Given signature verification result, when using convenience method,
        then should log correct event type
        """
        # When - log signature verification
        logger_service.log_signature_verification(
            peer_id="peer_1",
            valid=True,
            reason="Valid signature",
            metadata={"message_id": "msg_123"}
        )

        # Then
        events = logger_service.query_events(
            AuditQuery(event_type=AuditEventType.SIGNATURE_VERIFIED)
        )
        assert len(events) == 1
        assert events[0].result == AuditEventResult.VERIFIED


class TestDatabaseAuditLogStorage:
    """Test database-based audit log storage"""

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session"""
        return Mock()

    @pytest.fixture
    def db_storage(self, mock_db_session):
        """Create database audit log storage"""
        return DatabaseAuditLogStorage(session=mock_db_session)

    def test_store_event_in_database(self, db_storage, mock_db_session):
        """
        Given audit event, when storing in database,
        then should create database record
        """
        # Given
        event = AuditEvent(
            event_type=AuditEventType.AUTHORIZATION_SUCCESS,
            peer_id="peer_1",
            action="task_assignment",
            result=AuditEventResult.SUCCESS,
            reason="Capability matched"
        )

        # When
        db_storage.store(event)

        # Then
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    def test_query_from_database(self, db_storage, mock_db_session):
        """
        Given query parameters, when querying database,
        then should build correct SQL query
        """
        # Given
        query = AuditQuery(
            peer_id="peer_1",
            event_type=AuditEventType.AUTHENTICATION_SUCCESS
        )

        # Mock the query chain
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = []
        mock_db_session.query.return_value = mock_query

        # When
        results = db_storage.query(query)

        # Then
        mock_db_session.query.assert_called_once()
        assert results == []
