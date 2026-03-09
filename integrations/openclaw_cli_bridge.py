"""
OpenClaw CLI Bridge - Shell out to openclaw agent command
Simpler and more reliable than trying to reverse-engineer the WebSocket protocol
"""
import asyncio
import json
from typing import Any, Dict


class OpenClawCLIBridge:
    """Bridge to OpenClaw Gateway via CLI commands"""

    def __init__(self):
        self.agent_map = {
            "main": "main",
            "test-agent": "main",  # Map test-agent to main for now
        }

    async def send_to_agent(
        self, session_key: str, message: str, timeout_seconds: int = 600
    ) -> Dict[str, Any]:
        """Send message to agent via openclaw CLI

        Args:
            session_key: Agent session key (e.g., "agent:main:main")
            message: Message to send
            timeout_seconds: Timeout (not used with CLI approach)

        Returns:
            dict with 'response' key containing agent's text response
        """
        # Extract agent name from session key (format: agent:NAME:main)
        parts = session_key.split(":")
        agent_name = parts[1] if len(parts) >= 2 else "main"

        # Map agent name (handle aliases)
        agent_name = self.agent_map.get(agent_name, agent_name)

        try:
            # Call openclaw agent CLI command with local mode
            # --local: Run embedded agent locally with Anthropic API
            # --json: Output result as JSON
            # --timeout: Override default timeout (default 120s)
            proc = await asyncio.create_subprocess_exec(
                "openclaw",
                "agent",
                "-m",
                message,
                "--agent",
                agent_name,
                "--local",  # Run locally with API keys from environment
                "--json",
                "--timeout",
                str(timeout_seconds),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                return {
                    "response": f"Error calling OpenClaw agent: {error_msg}",
                    "error": error_msg,
                }

            # Parse JSON response
            result = json.loads(stdout.decode())

            # Extract text response from payloads
            # The CLI returns: {"payloads": [{"text": "...", "mediaUrl": null}], "meta": {...}}
            response_text = "No response"
            if "payloads" in result:
                payloads = result["payloads"]
                if payloads and len(payloads) > 0:
                    response_text = payloads[0].get("text", "No response")

            return {
                "response": response_text,
                "raw_result": result,
            }

        except Exception as e:
            return {
                "response": f"Error: {str(e)}",
                "error": str(e),
            }

    @property
    def is_connected(self) -> bool:
        """Always return True - CLI doesn't need persistent connection"""
        return True

    async def connect(self):
        """No-op - CLI doesn't need connection"""
        pass

    async def close(self):
        """No-op - CLI doesn't need connection"""
        pass
