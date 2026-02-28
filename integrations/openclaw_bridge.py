"""
OpenClaw Bridge - Production-ready WebSocket client for AINative integration
Implements OpenClaw Gateway Protocol v3 with proper authentication handshake
"""
import asyncio
import json
import logging
import os
import platform
import time
import uuid
from typing import Any, Callable, Dict, Optional

import websockets

logger = logging.getLogger(__name__)


class OpenClawBridgeError(Exception):
    """Base exception for OpenClaw bridge errors"""
    pass


class OpenClawAuthenticationError(OpenClawBridgeError):
    """Authentication failed"""
    pass


class OpenClawProtocolError(OpenClawBridgeError):
    """Protocol version mismatch or invalid message"""
    pass


class OpenClawBridge:
    """Production-ready WebSocket bridge to OpenClaw Gateway

    Implements OpenClaw Gateway Protocol v3:
    1. Receive connect.challenge event with nonce
    2. Send connect request with authentication token
    3. Receive hello-ok response confirming connection
    4. Send agent messages using the agent method
    """

    PROTOCOL_VERSION = 3
    # Use official OpenClaw Gateway client IDs
    CLIENT_ID = "gateway-client"  # Valid: gateway-client, backend, cli, etc.
    CLIENT_MODE = "backend"       # Valid: backend, cli, ui, node, etc.
    CLIENT_VERSION = "1.0.0"

    def __init__(
        self,
        url: str = "ws://127.0.0.1:18789",
        token: Optional[str] = None
    ):
        self.url = url
        self.token = token or os.getenv("OPENCLAW_GATEWAY_TOKEN")
        self.ws = None
        self.handlers: Dict[str, Callable] = {}
        self.pending: Dict[str, asyncio.Future] = {}
        self._connected = False
        self._handshake_complete = asyncio.Event()
        self._challenge_nonce: Optional[str] = None

    async def connect(self):
        """Connect to OpenClaw Gateway with proper authentication"""
        if self._connected:
            return

        logger.info(f"Connecting to OpenClaw Gateway at {self.url}")

        try:
            self.ws = await websockets.connect(self.url)
        except Exception as e:
            raise OpenClawBridgeError(f"Failed to connect to gateway: {e}")

        # Start event loop task to handle incoming messages
        self._event_loop_task = asyncio.create_task(self._event_loop())

        # Wait for connect.challenge event
        try:
            await asyncio.wait_for(
                self._wait_for_challenge(),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            raise OpenClawAuthenticationError("No connect.challenge received from gateway")

        # Send connect request with authentication
        await self._send_connect_request()

        # Wait for hello-ok response
        try:
            await asyncio.wait_for(
                self._handshake_complete.wait(),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            raise OpenClawAuthenticationError("No hello-ok response received from gateway")

        self._connected = True
        logger.info("Successfully connected to OpenClaw Gateway")

    async def _wait_for_challenge(self):
        """Wait for connect.challenge event"""
        while not self._challenge_nonce:
            await asyncio.sleep(0.1)

    async def _send_connect_request(self):
        """Send connect request with authentication"""
        connect_id = str(uuid.uuid4())

        connect_request = {
            "type": "req",
            "id": connect_id,
            "method": "connect",
            "params": {
                "minProtocol": self.PROTOCOL_VERSION,
                "maxProtocol": self.PROTOCOL_VERSION,
                "client": {
                    "id": self.CLIENT_ID,        # Must be from GATEWAY_CLIENT_IDS
                    "version": self.CLIENT_VERSION,
                    "platform": platform.system().lower(),
                    "mode": self.CLIENT_MODE     # Must be from GATEWAY_CLIENT_MODES
                },
                "role": "operator",
                "scopes": ["operator.read", "operator.write"],
                "caps": [],
                "commands": [],
                "permissions": {},
                "locale": "en-US",
                "userAgent": f"ainative-backend/{self.CLIENT_VERSION}"
            }
        }

        # Add authentication token if available
        if self.token:
            connect_request["params"]["auth"] = {"token": self.token}
            logger.debug("Including authentication token in connect request")
        else:
            logger.warning("No authentication token configured (OPENCLAW_GATEWAY_TOKEN not set)")

        # Create future to wait for response
        future = asyncio.Future()
        self.pending[connect_id] = future

        logger.debug(f"Sending connect request with protocol v{self.PROTOCOL_VERSION}")
        await self.ws.send(json.dumps(connect_request))

    async def _event_loop(self):
        """Handle incoming WebSocket messages"""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse message: {e}")
                except Exception as e:
                    logger.error(f"Error handling message: {e}", exc_info=True)

        except websockets.exceptions.ConnectionClosed as e:
            self._connected = False
            logger.info(f"OpenClaw connection closed: {e}")
        except Exception as e:
            self._connected = False
            logger.error(f"Event loop error: {e}", exc_info=True)

    async def _handle_message(self, data: Dict[str, Any]):
        """Handle incoming message from gateway"""
        msg_type = data.get("type")

        if msg_type == "event":
            await self._handle_event(data)
        elif msg_type == "res":
            await self._handle_response(data)
        elif msg_type == "error":
            await self._handle_error(data)
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def _handle_event(self, data: Dict[str, Any]):
        """Handle event messages"""
        event = data.get("event")
        payload = data.get("payload", {})

        # Log all events for debugging
        logger.info(f"📨 Received event: {event}, payload keys: {list(payload.keys()) if payload else []}")

        if event == "connect.challenge":
            # Store challenge nonce for signature (not implemented yet)
            self._challenge_nonce = payload.get("nonce")
            logger.debug(f"Received connect.challenge with nonce: {self._challenge_nonce}")

        elif event == "tick":
            # Keepalive event - no action needed
            pass

        elif event == "shutdown":
            # Gateway is shutting down
            reason = payload.get("reason", "unknown")
            logger.warning(f"Gateway is shutting down: {reason}")

        else:
            # Custom event handler
            handler = self.handlers.get(event)
            if handler:
                try:
                    await handler(payload)
                except Exception as e:
                    logger.error(f"Event handler error for {event}: {e}")
            else:
                # Log unhandled events with full payload for discovery
                logger.debug(f"Unhandled event '{event}': {payload}")

    async def _handle_response(self, data: Dict[str, Any]):
        """Handle response messages"""
        req_id = data.get("id")
        ok = data.get("ok")
        payload = data.get("payload", {})
        error = data.get("error")

        if req_id in self.pending:
            future = self.pending.pop(req_id)

            if ok:
                # Check if this is hello-ok response
                if payload.get("type") == "hello-ok":
                    protocol = payload.get("protocol")
                    logger.info(f"Handshake successful (protocol v{protocol})")
                    self._handshake_complete.set()

                future.set_result(payload)
            else:
                error_msg = error.get("message") if error else "Unknown error"
                error_code = error.get("code") if error else "UNKNOWN"
                logger.error(f"Request failed: [{error_code}] {error_msg}")
                future.set_exception(OpenClawBridgeError(f"{error_code}: {error_msg}"))

    async def _handle_error(self, data: Dict[str, Any]):
        """Handle error messages"""
        error = data.get("error", "Unknown error")
        code = data.get("code", "UNKNOWN")

        logger.error(f"Gateway error: [{code}] {error}")

        # Fail all pending requests
        for req_id, future in list(self.pending.items()):
            if not future.done():
                future.set_exception(OpenClawBridgeError(f"{code}: {error}"))

    async def _send_request(self, method: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Send request to gateway and wait for response

        Args:
            method: Request method name
            params: Optional parameters

        Returns:
            Response payload

        Raises:
            OpenClawBridgeError: If request fails
        """
        if not self._connected:
            raise OpenClawBridgeError("Not connected to gateway")

        req_id = str(uuid.uuid4())

        request = {
            "type": "req",
            "id": req_id,
            "method": method
        }

        if params:
            request["params"] = params

        # Create future to wait for response
        future = asyncio.Future()
        self.pending[req_id] = future

        logger.debug(f"Sending request: {method}")
        await self.ws.send(json.dumps(request))

        # Wait for response with timeout
        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            self.pending.pop(req_id, None)
            raise OpenClawBridgeError(f"Request timeout: {method}")

    def on_event(self, event: str, handler: Callable):
        """Register event handler

        Args:
            event: Event name
            handler: Async callable to handle event
        """
        self.handlers[event] = handler

    async def send_to_agent(self, session_key: str, message: str, timeout: float = 120.0) -> Dict[str, Any]:
        """Send message to specific agent session and wait for response

        Uses the 'agent' method to run an agent turn with the message, then uses
        'agent.wait' to wait for completion (proper OpenClaw Gateway pattern).

        Args:
            session_key: Agent session key (e.g., "agent:sales-agent:main")
            message: Message content
            timeout: Maximum seconds to wait for agent response (default 120s)

        Returns:
            Agent response with summary text and metadata

        Raises:
            OpenClawBridgeError: If agent request fails
            asyncio.TimeoutError: If agent doesn't respond within timeout
        """
        logger.info(f"Sending message to agent {session_key}: {message[:100]}")

        # Use the agent method from OpenClaw Gateway protocol
        result = await self._send_request(
            method="agent",
            params={
                "message": message,
                "to": session_key,
                "idempotencyKey": str(uuid.uuid4())
            }
        )

        run_id = result.get("runId")
        logger.info(f"Agent accepted message, runId={run_id}, status={result.get('status')}")

        # Wait for the agent run to complete using agent.wait method
        timeout_ms = int(timeout * 1000)
        wait_result = await self._send_request(
            method="agent.wait",
            params={
                "runId": run_id,
                "timeoutMs": timeout_ms
            }
        )

        wait_status = wait_result.get("status")
        logger.info(f"Agent run completed, status={wait_status}")

        # Fetch the actual response from chat history
        # agent.wait only confirms completion, we need to get the reply separately
        history_result = await self._send_request(
            method="chat.history",
            params={
                "sessionKey": session_key,
                "limit": 1  # Get just the latest message
            }
        )

        # Debug: Log the full history result
        logger.debug(f"chat.history result: {history_result}")

        # Extract the latest assistant message
        messages = history_result.get("messages", [])
        latest_message = messages[0] if messages else {}

        logger.debug(f"Latest message: {latest_message}")

        # Handle different message formats
        # - content array with text content blocks
        # - text field directly
        # - errorMessage if agent failed
        response_text = ""
        error_message = latest_message.get("errorMessage")

        if error_message:
            logger.error(f"Agent execution failed: {error_message}")
        else:
            # Try content array first (standard Claude API format)
            content = latest_message.get("content", [])
            if content:
                # Extract text from content blocks
                text_blocks = [block.get("text", "") for block in content if block.get("type") == "text"]
                response_text = "".join(text_blocks)
            else:
                # Fallback to text field
                response_text = latest_message.get("text", "")

            # Remove internal OpenClaw command markers that shouldn't be shown to users
            response_text = response_text.replace("[[reply_to_current]]", "").strip()

        thinking = latest_message.get("thinking")
        usage = latest_message.get("usage")

        return {
            "response": response_text,
            "status": wait_status,
            "runId": run_id,
            "messageId": result.get("messageId", str(uuid.uuid4())),
            "thinking": thinking,
            "usage": usage,
            "error": error_message or wait_result.get("error")
        }


    async def delegate_task(self, agent_profile: str, task: str) -> str:
        """Delegate task to specialized agent profile

        Args:
            agent_profile: Agent profile name (e.g., "claude-code-main")
            task: Task description

        Returns:
            Agent response summary as string
        """
        session_key = f"agent:{agent_profile}:main"
        result = await self.send_to_agent(session_key, task)
        return result.get("response", "")

    async def close(self):
        """Close WebSocket connection"""
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.error(f"Error closing connection: {e}")

        self._connected = False
        logger.info("Disconnected from OpenClaw Gateway")

    @property
    def is_connected(self) -> bool:
        """Check if connected to gateway"""
        return self._connected
