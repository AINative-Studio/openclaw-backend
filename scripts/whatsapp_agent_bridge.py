#!/usr/bin/env python3
"""
Simple WhatsApp Agent Bridge
Connects OpenClaw WhatsApp to the backend agent API
"""
import asyncio
import json
import logging
import os
import sys
import httpx

# Add integrations directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'integrations'))

from openclaw_bridge import OpenClawBridge

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY_URL", "ws://127.0.0.1:18789")
GATEWAY_TOKEN = os.getenv("OPENCLAW_GATEWAY_TOKEN", "7ae5aa8730848791e5a017fe95b80ad26f8c31d90e7b9ab60f5f8974d6519fc1")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


class WhatsAppAgentBridge:
    """Bridges WhatsApp messages to backend agent API"""

    def __init__(self):
        self.bridge = OpenClawBridge(url=GATEWAY_URL, token=GATEWAY_TOKEN)
        self.http = httpx.AsyncClient()
        self.session_key = "agent:main:whatsapp"

    async def connect(self):
        """Connect to OpenClaw Gateway"""
        logger.info(f"Connecting to OpenClaw Gateway...")
        await self.bridge.connect()
        logger.info("✅ Successfully connected to OpenClaw Gateway")

    async def handle_whatsapp_message(self, payload: dict):
        """Handle incoming WhatsApp message event"""
        try:
            # Extract message text
            message_obj = payload.get("message", {})
            text = message_obj.get("text", "").strip().lower()

            logger.info(f"Received WhatsApp message: {text}")

            # Check if it's asking about agents
            if any(keyword in text for keyword in ["agent", "status", "list", "who", "available"]):
                await self.send_agent_status()
            else:
                logger.info(f"Message doesn't match agent query keywords, ignoring")

        except Exception as e:
            logger.error(f"Error handling WhatsApp message: {e}")

    async def send_agent_status(self):
        """Query backend API and send agent status to WhatsApp"""
        try:
            logger.info("Querying backend API for agents...")
            response = await self.http.get(f"{BACKEND_URL}/api/v1/agents?limit=50")
            response.raise_for_status()
            data = response.json()

            agents = data.get("agents", [])
            logger.info(f"Found {len(agents)} agents")

            # Format response for WhatsApp
            message = "🤖 *Agent Swarm Status*\n\n"
            message += f"Total agents: {len(agents)}\n"
            message += f"Active: {sum(1 for a in agents if a['status'] == 'running')}\n\n"

            for i, agent in enumerate(agents, 1):
                message += f"*{i}. {agent['name']}*\n"
                message += f"   Status: {agent['status']}\n"

                # Clean up model name
                model = agent['model'].split('/')[-1] if '/' in agent['model'] else agent['model']
                message += f"   Model: {model}\n"

                if agent.get('heartbeat_enabled'):
                    message += f"   Heartbeat: {agent.get('heartbeat_interval', 'N/A')}\n"

                message += "\n"

            # Send to WhatsApp via OpenClaw Gateway
            await self.send_whatsapp_message(message)

        except Exception as e:
            logger.error(f"Error querying agents: {e}")
            await self.send_whatsapp_message(f"❌ Error querying agents: {str(e)}")

    async def send_whatsapp_message(self, text: str):
        """Send message to WhatsApp via OpenClaw Gateway"""
        logger.info(f"Sending WhatsApp message: {text[:100]}...")

        try:
            result = await self.bridge.send_to_agent(
                session_key=self.session_key,
                message=text
            )
            logger.info(f"✅ Message sent to WhatsApp: {result.get('status')}")
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {e}")

    async def run(self):
        """Main run loop"""
        # Connect to gateway
        await self.connect()

        # Register event handler for WhatsApp messages
        self.bridge.on_event("message", self.handle_whatsapp_message)

        logger.info("✅ Bridge is running and listening for WhatsApp messages...")
        logger.info("Waiting for messages (press Ctrl+C to stop)...")

        # Keep running
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Shutting down...")


async def main():
    """Entry point"""
    bridge = WhatsAppAgentBridge()
    await bridge.run()


if __name__ == "__main__":
    asyncio.run(main())
