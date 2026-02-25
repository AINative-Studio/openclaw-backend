#!/usr/bin/env python3
"""
WhatsApp Orchestrator Service
Connects to OpenClaw Gateway and routes WhatsApp commands to ClaudeOrchestrator
"""
import asyncio
import logging
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from integrations.openclaw_bridge import OpenClawBridge
from backend.agents.orchestration.command_parser import CommandParser
from backend.agents.orchestration.claude_orchestrator import ClaudeOrchestrator
from backend.agents.orchestration.notification_service import NotificationService
from backend.agents.swarm.nouscoder_agent_spawner import NousCoderAgentSpawner

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Start WhatsApp orchestrator service"""
    logger.info("Starting WhatsApp Orchestrator Service")

    # Initialize OpenClaw bridge
    gateway_url = os.getenv("OPENCLAW_GATEWAY_URL", "ws://127.0.0.1:18789")
    gateway_token = os.getenv("OPENCLAW_GATEWAY_TOKEN")

    bridge = OpenClawBridge(url=gateway_url, token=gateway_token)

    # Initialize orchestrator components
    spawner = NousCoderAgentSpawner(openclaw_bridge=bridge)
    notification_service = NotificationService(
        openclaw_bridge=bridge,
        whatsapp_session_key="agent:main:whatsapp"
    )
    command_parser = CommandParser()

    orchestrator = ClaudeOrchestrator(
        spawner=spawner,
        notification_service=notification_service,
        command_parser=command_parser
    )

    # Define message handler
    async def handle_whatsapp_message(event):
        """Handle incoming WhatsApp message"""
        try:
            # Extract message text
            message = event.get("message", {})
            text = message.get("text", "").strip()

            if not text:
                logger.debug("Ignoring empty message")
                return

            logger.info(f"Received WhatsApp message: {text}")

            # Route to orchestrator
            result = await orchestrator.handle_whatsapp_command(text)

            if result.get("success"):
                logger.info(f"Command processed successfully: {result}")
            else:
                logger.error(f"Command processing failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Error handling WhatsApp message: {e}", exc_info=True)

    # Register handler for WhatsApp messages
    bridge.on_event("message", handle_whatsapp_message)

    # Connect to gateway
    logger.info(f"Connecting to OpenClaw Gateway at {gateway_url}")
    await bridge.connect()
    logger.info("Connected to OpenClaw Gateway")

    # Send a startup notification (optional)
    try:
        await notification_service.send_notification(
            "🤖 WhatsApp Orchestrator connected and ready"
        )
    except Exception as e:
        logger.warning(f"Could not send startup notification: {e}")

    # Keep running
    logger.info("WhatsApp Orchestrator is running. Press Ctrl+C to stop.")
    try:
        await asyncio.Event().wait()  # Run forever
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await bridge.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Service stopped")
        sys.exit(0)
