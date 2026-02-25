#!/usr/bin/env python3
"""Add the main agent to the backend database"""
import httpx

# Create the main agent
agent_data = {
    "name": "Main Agent",
    "persona": "You are the main AI assistant that manages the AINative agent swarm platform via WhatsApp. You can check agent status by querying other agents and coordinating their work.",
    "model": "anthropic/claude-sonnet-4-5-20250929",
    "status": "running",
    "openclaw_session_key": "agent:main:main",
    "heartbeat_enabled": False
}

response = httpx.post(
    "http://localhost:8000/api/v1/agents",
    json=agent_data
)

print(f"Status: {response.status_code}")
print(response.text)
