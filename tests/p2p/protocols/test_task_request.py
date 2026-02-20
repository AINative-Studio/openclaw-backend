"""
Tests for TaskRequest Protocol (E5-S2)

Following TDD and BDD principles with Given/When/Then structure.
Tests the Request/Response protocol for task requests from coordinator to nodes.

Refs #28
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4


class TestTaskRequestMessage:
    """Test suite for TaskRequest message structure"""

    def test_create_task_request_message(self):
        """Given task details and lease, when creating request message,
        then should contain all required fields"""
        from backend.models.task_request_message import TaskRequestMessage

        # Given: Task details and lease token
        task_id = str(uuid4())
        lease_token = "lease_token_123"
        task_payload = {"action": "compute", "data": "test"}
        coordinator_peer_id = "12D3KooWCoordinator123456789"
        node_peer_id = "12D3KooWNode456789012345678"

        # When: Creating task request message
        message = TaskRequestMessage(
            task_id=task_id,
            lease_token=lease_token,
            task_payload=task_payload,
            coordinator_peer_id=coordinator_peer_id,
            node_peer_id=node_peer_id,
            timestamp=datetime.utcnow()
        )

        # Then: Should contain all required fields
        assert message.task_id == task_id
        assert message.lease_token == lease_token
        assert message.task_payload == task_payload
        assert message.coordinator_peer_id == coordinator_peer_id
        assert message.node_peer_id == node_peer_id
        assert message.timestamp is not None
        assert message.signature is None  # Not yet signed

    def test_task_request_message_serialization(self):
        """Given task request message, when serializing to bytes,
        then should produce valid protobuf/msgpack encoding"""
        from backend.models.task_request_message import TaskRequestMessage

        # Given: Task request message
        message = TaskRequestMessage(
            task_id=str(uuid4()),
            lease_token="lease_123",
            task_payload={"test": "data"},
            coordinator_peer_id="12D3KooWCoordinator123456789",
            node_peer_id="12D3KooWNode456789012345678",
            timestamp=datetime.utcnow()
        )

        # When: Serializing to bytes
        message_bytes = message.to_bytes()

        # Then: Should produce valid bytes
        assert isinstance(message_bytes, bytes)
        assert len(message_bytes) > 0

    def test_task_request_message_deserialization(self):
        """Given serialized message bytes, when deserializing,
        then should restore original message"""
        from backend.models.task_request_message import TaskRequestMessage

        # Given: Serialized message
        original = TaskRequestMessage(
            task_id=str(uuid4()),
            lease_token="lease_456",
            task_payload={"key": "value"},
            coordinator_peer_id="12D3KooWCoordinator123456789",
            node_peer_id="12D3KooWNode456789012345678",
            timestamp=datetime.utcnow()
        )
        message_bytes = original.to_bytes()

        # When: Deserializing
        restored = TaskRequestMessage.from_bytes(message_bytes)

        # Then: Should match original
        assert restored.task_id == original.task_id
        assert restored.lease_token == original.lease_token
        assert restored.task_payload == original.task_payload
        assert restored.coordinator_peer_id == original.coordinator_peer_id
        assert restored.node_peer_id == original.node_peer_id


class TestTaskRequestAcknowledgment:
    """Test suite for TaskRequest acknowledgment messages"""

    def test_create_task_ack_message(self):
        """Given received task request, when creating ACK,
        then should reference original task"""
        from backend.models.task_request_message import TaskAckMessage

        # Given: Original task ID
        task_id = str(uuid4())
        node_peer_id = "12D3KooWNode123"

        # When: Creating ACK message
        ack = TaskAckMessage(
            task_id=task_id,
            node_peer_id=node_peer_id,
            status="accepted",
            timestamp=datetime.utcnow()
        )

        # Then: Should reference task and indicate acceptance
        assert ack.task_id == task_id
        assert ack.node_peer_id == node_peer_id
        assert ack.status == "accepted"
        assert ack.timestamp is not None

    def test_task_ack_rejection(self):
        """Given node cannot accept task, when creating ACK,
        then should indicate rejection with reason"""
        from backend.models.task_request_message import TaskAckMessage

        # Given: Task rejection scenario
        task_id = str(uuid4())
        rejection_reason = "Node at capacity"

        # When: Creating rejection ACK
        ack = TaskAckMessage(
            task_id=task_id,
            node_peer_id="12D3KooWNode",
            status="rejected",
            rejection_reason=rejection_reason,
            timestamp=datetime.utcnow()
        )

        # Then: Should indicate rejection with reason
        assert ack.status == "rejected"
        assert ack.rejection_reason == rejection_reason


class TestTaskRequestSigning:
    """Test suite for message signing and verification"""

    def test_sign_task_request_message(self):
        """Given task request message, when signing with coordinator key,
        then should produce valid Ed25519 signature"""
        from backend.models.task_request_message import TaskRequestMessage
        from backend.p2p.libp2p_identity import LibP2PIdentity

        # Given: Coordinator identity and message
        coordinator = LibP2PIdentity()
        coordinator.generate()

        message = TaskRequestMessage(
            task_id=str(uuid4()),
            lease_token="lease_789",
            task_payload={"test": "data"},
            coordinator_peer_id=coordinator.peer_id,
            node_peer_id="12D3KooWNode",
            timestamp=datetime.utcnow()
        )

        # When: Signing message
        message.sign(coordinator.private_key)

        # Then: Should have valid signature
        assert message.signature is not None
        assert isinstance(message.signature, bytes)
        assert len(message.signature) == 64  # Ed25519 signature length

    def test_verify_task_request_signature(self):
        """Given signed task request, when verifying signature,
        then should validate coordinator signature"""
        from backend.models.task_request_message import TaskRequestMessage
        from backend.p2p.libp2p_identity import LibP2PIdentity

        # Given: Signed message
        coordinator = LibP2PIdentity()
        coordinator.generate()

        message = TaskRequestMessage(
            task_id=str(uuid4()),
            lease_token="lease_abc",
            task_payload={"test": "data"},
            coordinator_peer_id=coordinator.peer_id,
            node_peer_id="12D3KooWNode",
            timestamp=datetime.utcnow()
        )
        message.sign(coordinator.private_key)

        # When: Verifying signature
        is_valid = message.verify_signature(coordinator.public_key)

        # Then: Should be valid
        assert is_valid is True

    def test_verify_tampered_message_fails(self):
        """Given tampered message, when verifying signature,
        then should fail validation"""
        from backend.models.task_request_message import TaskRequestMessage
        from backend.p2p.libp2p_identity import LibP2PIdentity

        # Given: Signed message that is then tampered
        coordinator = LibP2PIdentity()
        coordinator.generate()

        message = TaskRequestMessage(
            task_id=str(uuid4()),
            lease_token="lease_def",
            task_payload={"test": "data"},
            coordinator_peer_id=coordinator.peer_id,
            node_peer_id="12D3KooWNode",
            timestamp=datetime.utcnow()
        )
        message.sign(coordinator.private_key)

        # When: Tampering with message after signing
        message.task_payload = {"tampered": "data"}

        # Then: Verification should fail
        is_valid = message.verify_signature(coordinator.public_key)
        assert is_valid is False


@pytest.mark.asyncio
class TestTaskRequestProtocol:
    """Test suite for TaskRequest protocol handler"""

    async def test_initialize_task_request_protocol(self):
        """Given libp2p host, when initializing protocol,
        then should register protocol handler"""
        from backend.p2p.protocols.task_request import TaskRequestProtocol

        # Given: Mock libp2p host
        mock_host = Mock()
        mock_host.set_stream_handler = Mock()

        # When: Initializing protocol
        protocol = TaskRequestProtocol(mock_host)

        # Then: Should register stream handler
        assert protocol.protocol_id == "/openclaw/task/request/1.0"
        assert protocol.host == mock_host

    async def test_send_task_request_to_peer(self):
        """Given task and lease, when sending request to node,
        then should deliver via libp2p stream"""
        from backend.p2p.protocols.task_request import TaskRequestProtocol
        from backend.models.task_request_message import TaskRequestMessage
        from backend.p2p.libp2p_identity import LibP2PIdentity

        # Given: Protocol instance and task details
        mock_host = Mock()
        mock_stream = AsyncMock()
        mock_host.new_stream = AsyncMock(return_value=mock_stream)

        protocol = TaskRequestProtocol(mock_host)

        coordinator = LibP2PIdentity()
        coordinator.generate()

        message = TaskRequestMessage(
            task_id=str(uuid4()),
            lease_token="lease_ghi",
            task_payload={"action": "process"},
            coordinator_peer_id=coordinator.peer_id,
            node_peer_id="12D3KooWNode789",
            timestamp=datetime.utcnow()
        )

        # When: Sending task request
        ack = await protocol.send_task_request(
            node_peer_id="12D3KooWNode789",
            message=message,
            coordinator_key=coordinator.private_key
        )

        # Then: Should create stream and send message
        mock_host.new_stream.assert_called_once()
        assert ack is not None

    async def test_receive_task_request_handler(self):
        """Given incoming task request, when received by node,
        then should validate and return ACK"""
        from backend.p2p.protocols.task_request import TaskRequestProtocol
        from backend.models.task_request_message import TaskRequestMessage
        from backend.p2p.libp2p_identity import LibP2PIdentity

        # Given: Mock stream with incoming request
        mock_host = Mock()
        protocol = TaskRequestProtocol(mock_host)

        coordinator = LibP2PIdentity()
        coordinator.generate()

        message = TaskRequestMessage(
            task_id=str(uuid4()),
            lease_token="lease_jkl",
            task_payload={"action": "test"},
            coordinator_peer_id=coordinator.peer_id,
            node_peer_id="12D3KooWNode",
            timestamp=datetime.utcnow()
        )
        message.sign(coordinator.private_key)

        mock_stream = AsyncMock()
        mock_stream.read = AsyncMock(return_value=message.to_bytes())
        mock_stream.write = AsyncMock()

        # When: Handling incoming request
        await protocol.handle_task_request(mock_stream, coordinator.public_key)

        # Then: Should read message and send ACK
        mock_stream.read.assert_called_once()
        mock_stream.write.assert_called_once()

    async def test_request_timeout_handling(self):
        """Given unresponsive node, when sending request times out,
        then should raise timeout exception"""
        from backend.p2p.protocols.task_request import TaskRequestProtocol
        from backend.models.task_request_message import TaskRequestMessage
        from backend.p2p.libp2p_identity import LibP2PIdentity

        # Given: Mock host that times out
        mock_host = Mock()
        mock_host.new_stream = AsyncMock(
            side_effect=asyncio.TimeoutError("Stream timeout")
        )

        protocol = TaskRequestProtocol(mock_host, timeout=1.0)

        coordinator = LibP2PIdentity()
        coordinator.generate()

        message = TaskRequestMessage(
            task_id=str(uuid4()),
            lease_token="lease_mno",
            task_payload={"test": "data"},
            coordinator_peer_id=coordinator.peer_id,
            node_peer_id="12D3KooWNode",
            timestamp=datetime.utcnow()
        )

        # When/Then: Sending should raise timeout
        with pytest.raises(asyncio.TimeoutError):
            await protocol.send_task_request(
                node_peer_id="12D3KooWNode",
                message=message,
                coordinator_key=coordinator.private_key
            )

    async def test_invalid_signature_rejection(self):
        """Given request with invalid signature, when validating,
        then should reject and not process"""
        from backend.p2p.protocols.task_request import TaskRequestProtocol
        from backend.models.task_request_message import TaskRequestMessage
        from backend.p2p.libp2p_identity import LibP2PIdentity

        # Given: Message with invalid signature
        mock_host = Mock()
        protocol = TaskRequestProtocol(mock_host)

        coordinator = LibP2PIdentity()
        coordinator.generate()

        wrong_identity = LibP2PIdentity()
        wrong_identity.generate()

        message = TaskRequestMessage(
            task_id=str(uuid4()),
            lease_token="lease_pqr",
            task_payload={"test": "data"},
            coordinator_peer_id=coordinator.peer_id,
            node_peer_id="12D3KooWNode",
            timestamp=datetime.utcnow()
        )
        message.sign(wrong_identity.private_key)  # Sign with wrong key

        mock_stream = AsyncMock()
        mock_stream.read = AsyncMock(return_value=message.to_bytes())
        mock_stream.write = AsyncMock()

        # When: Handling request with invalid signature
        with pytest.raises(ValueError, match="Invalid signature"):
            await protocol.handle_task_request(
                mock_stream,
                coordinator.public_key  # Expected public key
            )

    async def test_protocol_version_compatibility(self):
        """Given protocol version check, when versions match,
        then should proceed with communication"""
        from backend.p2p.protocols.task_request import TaskRequestProtocol

        # Given: Protocol instance
        mock_host = Mock()
        protocol = TaskRequestProtocol(mock_host)

        # When: Checking version compatibility
        is_compatible = protocol.is_version_compatible("/openclaw/task/request/1.0")

        # Then: Should be compatible
        assert is_compatible is True

    async def test_protocol_version_incompatibility(self):
        """Given mismatched protocol version, when checking compatibility,
        then should detect incompatibility"""
        from backend.p2p.protocols.task_request import TaskRequestProtocol

        # Given: Protocol instance
        mock_host = Mock()
        protocol = TaskRequestProtocol(mock_host)

        # When: Checking incompatible version
        is_compatible = protocol.is_version_compatible("/openclaw/task/request/2.0")

        # Then: Should be incompatible
        assert is_compatible is False


@pytest.fixture
def coordinator_identity():
    """Fixture providing coordinator identity"""
    from backend.p2p.libp2p_identity import LibP2PIdentity
    identity = LibP2PIdentity()
    identity.generate()
    return identity


@pytest.fixture
def node_identity():
    """Fixture providing node identity"""
    from backend.p2p.libp2p_identity import LibP2PIdentity
    identity = LibP2PIdentity()
    identity.generate()
    return identity


@pytest.fixture
def sample_task_payload():
    """Fixture providing sample task payload"""
    return {
        "action": "compute",
        "algorithm": "sha256",
        "data": "test_data_123",
        "timeout": 30
    }
