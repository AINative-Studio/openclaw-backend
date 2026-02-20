"""
TaskRequest Protocol Handler (E5-S2)

Implements request/response protocol for task assignment from coordinator to nodes.
Uses libp2p streams with message signing and verification.

Protocol ID: /openclaw/task/request/1.0

Refs #28
"""

import asyncio
import logging
from typing import Optional, Callable, Awaitable
from cryptography.hazmat.primitives.asymmetric import ed25519

from backend.models.task_request_message import TaskRequestMessage, TaskAckMessage


logger = logging.getLogger(__name__)


class TaskRequestProtocol:
    """
    TaskRequest Protocol Handler

    Manages bidirectional communication for task requests between
    coordinator and nodes using libp2p streams.

    Features:
    - Request/Response pattern over libp2p streams
    - Ed25519 message signing and verification
    - Protocol version compatibility checking
    - Timeout handling for unresponsive peers
    """

    PROTOCOL_ID = "/openclaw/task/request/1.0"
    DEFAULT_TIMEOUT = 30.0  # seconds

    def __init__(
        self,
        host: any,
        timeout: float = DEFAULT_TIMEOUT,
        request_handler: Optional[Callable[[TaskRequestMessage], Awaitable[TaskAckMessage]]] = None
    ):
        """
        Initialize TaskRequest protocol handler.

        Args:
            host: libp2p host instance
            timeout: Request timeout in seconds
            request_handler: Optional callback for handling incoming requests
        """
        self.host = host
        self.timeout = timeout
        self.request_handler = request_handler
        self._protocol_id = self.PROTOCOL_ID

    @property
    def protocol_id(self) -> str:
        """Get the protocol ID"""
        return self._protocol_id

    def is_version_compatible(self, protocol_id: str) -> bool:
        """
        Check if a protocol version is compatible.

        Args:
            protocol_id: Protocol ID to check

        Returns:
            True if compatible, False otherwise
        """
        return protocol_id == self.PROTOCOL_ID

    async def send_task_request(
        self,
        node_peer_id: str,
        message: TaskRequestMessage,
        coordinator_key: ed25519.Ed25519PrivateKey
    ) -> TaskAckMessage:
        """
        Send task request to a node and await acknowledgment.

        Args:
            node_peer_id: Target node's libp2p peer ID
            message: TaskRequestMessage to send
            coordinator_key: Coordinator's private key for signing

        Returns:
            TaskAckMessage acknowledgment from node

        Raises:
            asyncio.TimeoutError: If request times out
            ValueError: If signature verification fails
            ConnectionError: If stream creation fails
        """
        logger.info(
            f"Sending task request {message.task_id} to node {node_peer_id}"
        )

        # Sign the message
        message.sign(coordinator_key)

        try:
            # Create new stream to node
            stream = await asyncio.wait_for(
                self.host.new_stream(node_peer_id, [self.PROTOCOL_ID]),
                timeout=self.timeout
            )

            # Serialize and send message
            message_bytes = message.to_bytes()
            await asyncio.wait_for(
                stream.write(message_bytes),
                timeout=self.timeout
            )

            logger.debug(
                f"Sent task request {message.task_id}, "
                f"waiting for ACK (timeout: {self.timeout}s)"
            )

            # Wait for acknowledgment
            ack_bytes = await asyncio.wait_for(
                stream.read(),
                timeout=self.timeout
            )

            # Deserialize ACK
            ack = TaskAckMessage.from_bytes(ack_bytes)

            logger.info(
                f"Received ACK for task {message.task_id}: "
                f"status={ack.status}"
            )

            # Close stream
            await stream.close()

            return ack

        except asyncio.TimeoutError as e:
            logger.error(
                f"Timeout sending task request {message.task_id} "
                f"to node {node_peer_id}"
            )
            raise

        except Exception as e:
            logger.error(
                f"Error sending task request {message.task_id}: {e}"
            )
            raise

    async def handle_task_request(
        self,
        stream: any,
        expected_coordinator_key: ed25519.Ed25519PublicKey
    ) -> None:
        """
        Handle incoming task request from coordinator.

        This is the stream handler registered with libp2p host.

        Args:
            stream: libp2p stream from coordinator
            expected_coordinator_key: Expected coordinator's public key

        Raises:
            ValueError: If signature verification fails
        """
        try:
            # Read message from stream
            message_bytes = await asyncio.wait_for(
                stream.read(),
                timeout=self.timeout
            )

            # Deserialize message
            message = TaskRequestMessage.from_bytes(message_bytes)

            logger.info(
                f"Received task request {message.task_id} "
                f"from coordinator {message.coordinator_peer_id}"
            )

            # Verify signature
            if not message.verify_signature(expected_coordinator_key):
                logger.error(
                    f"Invalid signature on task request {message.task_id}"
                )
                raise ValueError("Invalid signature")

            logger.debug(
                f"Signature verified for task request {message.task_id}"
            )

            # Process request with handler if available
            if self.request_handler:
                ack = await self.request_handler(message)
            else:
                # Default: accept all requests
                from datetime import datetime
                ack = TaskAckMessage(
                    task_id=message.task_id,
                    node_peer_id=message.node_peer_id,
                    status="accepted",
                    timestamp=datetime.utcnow()
                )

            # Send acknowledgment
            ack_bytes = ack.to_bytes()
            await asyncio.wait_for(
                stream.write(ack_bytes),
                timeout=self.timeout
            )

            logger.info(
                f"Sent ACK for task {message.task_id}: status={ack.status}"
            )

            # Close stream
            await stream.close()

        except asyncio.TimeoutError:
            logger.error("Timeout handling task request")
            raise

        except ValueError as e:
            logger.error(f"Validation error: {e}")
            raise

        except Exception as e:
            logger.error(f"Error handling task request: {e}")
            raise

    def register_stream_handler(
        self,
        coordinator_public_key: ed25519.Ed25519PublicKey
    ) -> None:
        """
        Register this protocol's stream handler with libp2p host.

        Args:
            coordinator_public_key: Expected coordinator's public key for verification
        """
        async def stream_handler(stream: any) -> None:
            """Wrapper to pass coordinator key to handler"""
            await self.handle_task_request(stream, coordinator_public_key)

        self.host.set_stream_handler(self.PROTOCOL_ID, stream_handler)

        logger.info(
            f"Registered stream handler for protocol {self.PROTOCOL_ID}"
        )

    async def send_batch_requests(
        self,
        requests: list[tuple[str, TaskRequestMessage]],
        coordinator_key: ed25519.Ed25519PrivateKey,
        max_concurrent: int = 10
    ) -> list[TaskAckMessage]:
        """
        Send multiple task requests concurrently with rate limiting.

        Args:
            requests: List of (node_peer_id, message) tuples
            coordinator_key: Coordinator's private key for signing
            max_concurrent: Maximum concurrent requests

        Returns:
            List of TaskAckMessage acknowledgments
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def send_with_limit(node_peer_id: str, message: TaskRequestMessage):
            async with semaphore:
                return await self.send_task_request(
                    node_peer_id,
                    message,
                    coordinator_key
                )

        tasks = [
            send_with_limit(node_peer_id, message)
            for node_peer_id, message in requests
        ]

        return await asyncio.gather(*tasks, return_exceptions=True)


class TaskRequestProtocolError(Exception):
    """Base exception for TaskRequest protocol errors"""
    pass


class TaskRequestTimeoutError(TaskRequestProtocolError):
    """Raised when task request times out"""
    pass


class TaskRequestValidationError(TaskRequestProtocolError):
    """Raised when task request validation fails"""
    pass
