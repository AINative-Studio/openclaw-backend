#!/usr/bin/env python3
"""
MCP Server for Agent Swarm Backend API
Exposes agent management functions to OpenClaw
"""
import asyncio
import json
from typing import Any, Dict, List
import httpx

# MCP Server implementation
class AgentSwarmMCPServer:
    """MCP Server that provides agent management tools"""

    def __init__(self, backend_url: str = "http://localhost:8000"):
        self.backend_url = backend_url
        self.client = httpx.AsyncClient()

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Return available tools"""
        return [
            {
                "name": "list_agents",
                "description": "List all agents in the swarm with their status, models, and configurations",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of agents to return",
                            "default": 50
                        }
                    }
                }
            },
            {
                "name": "get_agent",
                "description": "Get detailed information about a specific agent",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "The UUID of the agent"
                        }
                    },
                    "required": ["agent_id"]
                }
            },
            {
                "name": "get_swarm_health",
                "description": "Get overall swarm health status",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool and return results"""

        if name == "list_agents":
            limit = arguments.get("limit", 50)
            response = await self.client.get(f"{self.backend_url}/api/v1/agents?limit={limit}")
            data = response.json()

            # Format response nicely for WhatsApp
            agents = data.get("agents", [])
            result = f"📊 Agent Swarm Status\n\n"
            result += f"Total agents: {len(agents)}\n"
            result += f"Active: {sum(1 for a in agents if a['status'] == 'running')}\n\n"

            for i, agent in enumerate(agents, 1):
                result += f"{i}. {agent['name']}\n"
                result += f"   Status: {agent['status']}\n"
                model = agent['model'].split('/')[-1] if '/' in agent['model'] else agent['model']
                result += f"   Model: {model}\n"
                if agent.get('heartbeat_enabled'):
                    result += f"   Heartbeat: {agent['heartbeat_interval']}\n"
                result += "\n"

            return result

        elif name == "get_agent":
            agent_id = arguments.get("agent_id")
            response = await self.client.get(f"{self.backend_url}/api/v1/agents/{agent_id}")
            agent = response.json()

            result = f"🤖 {agent['name']}\n\n"
            result += f"Status: {agent['status']}\n"
            result += f"Model: {agent['model']}\n"
            result += f"ID: {agent['id']}\n\n"
            result += f"Persona:\n{agent['persona'][:200]}...\n"

            return result

        elif name == "get_swarm_health":
            response = await self.client.get(f"{self.backend_url}/api/v1/swarm/health")
            data = response.json()

            result = f"🏥 Swarm Health\n\n"
            result += f"Status: {data.get('status', 'unknown')}\n"

            return result

        return f"Unknown tool: {name}"


async def main():
    """Run MCP server"""
    server = AgentSwarmMCPServer()

    # Print available tools
    tools = await server.list_tools()
    print(json.dumps({
        "jsonrpc": "2.0",
        "result": {
            "tools": tools
        }
    }))

    # Keep server running
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
