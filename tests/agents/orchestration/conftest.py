"""
Conftest for orchestration tests - sets up import mocks
"""
import sys
from unittest.mock import MagicMock

# Mock all app.* modules to avoid import errors
sys.modules['app'] = MagicMock()
sys.modules['app.agents'] = MagicMock()
sys.modules['app.agents.orchestration'] = MagicMock()
sys.modules['app.agents.orchestration.openclaw_bridge_protocol'] = MagicMock()
sys.modules['app.agents.orchestration.command_parser'] = MagicMock()
sys.modules['app.agents.orchestration.notification_service'] = MagicMock()
sys.modules['app.agents.swarm'] = MagicMock()
sys.modules['app.agents.swarm.nouscoder_agent_spawner'] = MagicMock()
