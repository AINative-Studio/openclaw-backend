"""
OpenClaw Bridge - Minimal WebSocket client for AINative integration
~80 lines of code to connect your agent swarms with OpenClaw Gateway
"""
import asyncio
import json
import os
import uuid
from typing import Any, Callable, Dict, Optional

import websockets


class OpenClawBridge:
    """Lightweight WebSocket bridge to OpenClaw Gateway"""

    def __init__(
        self,
        url: str = "ws://127.0.0.1:18789",
        token: Optional[str] = None
    ):
        self.url = url
        self.token = token or os.getenv("OPENCLAW_TOKEN")
        self.ws = None
        self.handlers: Dict[str, Callable] = {}
        self.pending: Dict[str, asyncio.Future] = {}
        self._connected = False

    async def connect(self):
        """Connect to OpenClaw Gateway and authenticate"""
        self.ws = await websockets.connect(self.url)

        # Start event loop task BEFORE sending requests
        # This ensures responses can be processed
        self._event_loop_task = asyncio.create_task(self._event_loop())

        # Give event loop a chance to start
        await asyncio.sleep(0)

        # Send connect frame with authentication and required protocol fields
        await self._request("connect", {
            "minProtocol": 3,
            "maxProtocol": 3,
            "client": {
                "id": "ainative-agent-swarm",
                "displayName": "AINative Agent Swarm",
                "version": "1.0.0",
                "platform": "python",
                "mode": "backend"
            },
            "auth": {
                "token": self.token
            }
        })

        self._connected = True

    async def _event_loop(self):
        """Handle incoming WebSocket messages"""
        try:
            async for message in self.ws:
                data = json.loads(message)

                if data["type"] == "res":
                    # Response to our request
                    request_id = data["id"]
                    if request_id in self.pending:
                        future = self.pending.pop(request_id)
                        if data.get("ok"):
                            future.set_result(data.get("payload"))
                        else:
                            error_msg = data.get("error", {}).get("message", "Unknown error")
                            future.set_exception(Exception(error_msg))

                elif data["type"] == "evt":
                    # Event broadcast from gateway
                    event_name = data["event"]
                    if event_name in self.handlers:
                        await self.handlers[event_name](data.get("payload", {}))

        except websockets.exceptions.ConnectionClosed:
            self._connected = False
            print("OpenClaw connection closed")

    async def _request(self, method: str, params: Any = None) -> Any:
        """Send RPC request and wait for response"""
        request_id = str(uuid.uuid4())
        frame = {
            "type": "req",
            "id": request_id,
            "method": method,
            "params": params
        }

        future = asyncio.Future()
        self.pending[request_id] = future

        await self.ws.send(json.dumps(frame))
        return await future

    def on_event(self, event: str, handler: Callable):
        """Register event handler"""
        self.handlers[event] = handler

    async def send_to_agent(self, session_key: str, message: str) -> Dict[str, Any]:
        """Send message to specific agent session"""
        return await self._request("agent.send", {
            "sessionKey": session_key,
            "message": message
        })

    async def delegate_task(self, agent_profile: str, task: str) -> str:
        """
        Delegate task to specialized agent profile

        Args:
            agent_profile: Agent profile name (e.g., "claude-code-main", "research-assistant")
            task: Task description

        Returns:
            Agent response as string
        """
        session_key = f"agent:{agent_profile}:main"
        result = await self.send_to_agent(session_key, task)
        return result.get("response", "")

    async def close(self):
        """Close WebSocket connection"""
        if self.ws:
            await self.ws.close()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if connected to gateway"""
        return self._connected
