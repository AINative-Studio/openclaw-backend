"""Models package initialization"""

# Import all models to register them with SQLAlchemy Base
from backend.models.api_key import APIKey  # noqa: F401
from backend.models.user_api_key import UserAPIKey  # noqa: F401
from backend.models.workspace import Workspace  # noqa: F401
from backend.models.user import User  # noqa: F401
from backend.models.agent_swarm_lifecycle import AgentSwarmInstance  # noqa: F401
from backend.models.conversation import Conversation, ConversationStatus  # noqa: F401
from backend.models.agent_skill_configuration import AgentSkillConfiguration  # noqa: F401
from backend.models.agent_channel_credentials import AgentChannelCredentials  # noqa: F401
from backend.models.skill_history import SkillInstallationHistory, SkillExecutionHistory  # noqa: F401

# Canonical Task and TaskLease models (Issue #116)
# All services MUST import from task_lease.py
from backend.models.task_lease import (  # noqa: F401
    Task,
    TaskLease,
    TaskStatus,
    TaskPriority,
)
