"""
Test AgentSwarmInstance Model with Workspace Integration

Tests agent creation with workspace_id, workspace/conversations relationships,
cascade delete behavior, and data migration scenarios following TDD principles.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, Text, TypeDecorator
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
import json

# Mock ARRAY type for SQLite BEFORE importing models
class MockARRAY(TypeDecorator):
    """SQLite-compatible ARRAY type that stores as JSON text"""
    impl = Text
    cache_ok = True

    def __init__(self, item_type=None):
        self.item_type = item_type
        super().__init__()

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)

# Monkeypatch ARRAY and JSONB before importing models
from sqlalchemy.dialects import postgresql
postgresql.ARRAY = MockARRAY

class MockJSONB(TypeDecorator):
    """SQLite-compatible JSONB type that stores as JSON text"""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)

postgresql.JSONB = MockJSONB

from backend.db.base_class import Base
from backend.models.agent_swarm_lifecycle import (
    AgentSwarmInstance,
    AgentSwarmStatus,
    HeartbeatInterval
)
from backend.models.workspace import Workspace
from backend.models.user import User


@pytest.fixture
def db_engine():
    """Create in-memory SQLite database for testing"""
    from sqlalchemy import event

    engine = create_engine("sqlite:///:memory:")

    # Enable foreign key constraints in SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Drop all existing tables first, then create fresh
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create database session for testing"""
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def sample_workspace(db_session):
    """Create a sample workspace for testing"""
    workspace = Workspace(
        name="Test Workspace",
        slug="test-workspace"
    )
    db_session.add(workspace)
    db_session.commit()
    db_session.refresh(workspace)
    return workspace


@pytest.fixture
def sample_user(db_session, sample_workspace):
    """Create a sample user for testing"""
    user = User(
        email="test@example.com",
        workspace_id=sample_workspace.id
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestAgentSwarmInstanceWorkspaceIntegration:
    """Test AgentSwarmInstance integration with Workspace"""

    def test_create_agent_with_workspace_id(self, db_session, sample_workspace, sample_user):
        """Test creating an agent with workspace_id"""
        agent = AgentSwarmInstance(
            name="Test Agent",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert agent.id is not None
        assert agent.workspace_id == sample_workspace.id
        assert agent.name == "Test Agent"
        assert agent.status == AgentSwarmStatus.PROVISIONING

    def test_create_agent_without_workspace_id_nullable(self, db_session, sample_user):
        """Test creating an agent without workspace_id (should be allowed initially for migration)"""
        agent = AgentSwarmInstance(
            name="Agent Without Workspace",
            model="claude-3-opus-20240229",
            user_id=sample_user.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert agent.id is not None
        assert agent.workspace_id is None

    def test_workspace_id_has_index(self, db_engine):
        """Test that workspace_id column has an index"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        indexes = inspector.get_indexes("agent_swarm_instances")

        # Find index on workspace_id column
        workspace_id_indexed = any(
            "workspace_id" in idx.get("column_names", [])
            for idx in indexes
        )
        assert workspace_id_indexed, "workspace_id column should have an index"

    def test_workspace_id_foreign_key_constraint(self, db_engine):
        """Test that workspace_id has foreign key constraint to workspaces table"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        foreign_keys = inspector.get_foreign_keys("agent_swarm_instances")

        # Find foreign key on workspace_id
        workspace_fk = any(
            fk.get("constrained_columns") == ["workspace_id"] and
            fk.get("referred_table") == "workspaces" and
            fk.get("referred_columns") == ["id"]
            for fk in foreign_keys
        )
        assert workspace_fk, "workspace_id should have foreign key to workspaces.id"

    def test_workspace_foreign_key_on_delete_cascade(self, db_engine):
        """Test that workspace_id foreign key has ON DELETE CASCADE"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        foreign_keys = inspector.get_foreign_keys("agent_swarm_instances")

        # Find workspace_id foreign key and check ondelete
        workspace_fk = next(
            (fk for fk in foreign_keys
             if fk.get("constrained_columns") == ["workspace_id"]),
            None
        )
        assert workspace_fk is not None
        assert workspace_fk.get("options", {}).get("ondelete") == "CASCADE"


class TestAgentWorkspaceRelationship:
    """Test workspace relationship on AgentSwarmInstance"""

    def test_agent_workspace_relationship_exists(self, db_session, sample_workspace, sample_user):
        """Test that agent has workspace relationship"""
        agent = AgentSwarmInstance(
            name="Relationship Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert hasattr(agent, "workspace")
        assert agent.workspace is not None
        assert agent.workspace.id == sample_workspace.id
        assert agent.workspace.name == "Test Workspace"

    def test_workspace_agents_relationship(self, db_session, sample_workspace, sample_user):
        """Test that workspace has agents back-reference"""
        agent1 = AgentSwarmInstance(
            name="Agent 1",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        agent2 = AgentSwarmInstance(
            name="Agent 2",
            model="claude-3-sonnet-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add_all([agent1, agent2])
        db_session.commit()
        db_session.refresh(sample_workspace)

        assert hasattr(sample_workspace, "agents")
        assert len(sample_workspace.agents) == 2
        agent_names = {agent.name for agent in sample_workspace.agents}
        assert "Agent 1" in agent_names
        assert "Agent 2" in agent_names

    def test_workspace_delete_cascades_to_agents(self, db_session, sample_workspace, sample_user):
        """Test that deleting workspace cascades to delete agents"""
        agent = AgentSwarmInstance(
            name="Cascade Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id

        # Delete workspace
        db_session.delete(sample_workspace)
        db_session.commit()

        # Verify agent was also deleted
        found_agent = db_session.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()
        assert found_agent is None


class TestAgentConversationsRelationship:
    """Test conversations relationship on AgentSwarmInstance"""

    def test_agent_conversations_relationship_exists(self, db_session, sample_workspace, sample_user):
        """Test that agent has conversations relationship"""
        agent = AgentSwarmInstance(
            name="Conversations Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert hasattr(agent, "conversations")
        # Initially empty list (Conversation model will be created in separate issue)
        assert isinstance(agent.conversations, list)
        assert len(agent.conversations) == 0


class TestAgentWorkspaceQuery:
    """Test querying agents by workspace"""

    def test_query_agents_by_workspace_id(self, db_session, sample_workspace, sample_user):
        """Test querying all agents in a workspace"""
        agent1 = AgentSwarmInstance(
            name="Agent 1",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        agent2 = AgentSwarmInstance(
            name="Agent 2",
            model="claude-3-sonnet-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add_all([agent1, agent2])
        db_session.commit()

        # Query agents by workspace_id
        agents = db_session.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.workspace_id == sample_workspace.id
        ).all()

        assert len(agents) == 2
        agent_names = {agent.name for agent in agents}
        assert "Agent 1" in agent_names
        assert "Agent 2" in agent_names

    def test_query_agents_with_null_workspace(self, db_session, sample_user):
        """Test querying agents without workspace (for migration scenarios)"""
        agent = AgentSwarmInstance(
            name="No Workspace Agent",
            model="claude-3-opus-20240229",
            user_id=sample_user.id
        )
        db_session.add(agent)
        db_session.commit()

        # Query agents with null workspace_id
        agents = db_session.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.workspace_id.is_(None)
        ).all()

        assert len(agents) == 1
        assert agents[0].name == "No Workspace Agent"


class TestAgentWorkspaceMigration:
    """Test data migration scenarios for existing agents"""

    def test_migrate_existing_agent_to_workspace(self, db_session, sample_workspace, sample_user):
        """Test migrating an agent without workspace to a workspace"""
        # Create agent without workspace (simulating legacy data)
        agent = AgentSwarmInstance(
            name="Legacy Agent",
            model="claude-3-opus-20240229",
            user_id=sample_user.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert agent.workspace_id is None

        # Migrate agent to workspace
        agent.workspace_id = sample_workspace.id
        db_session.commit()
        db_session.refresh(agent)

        assert agent.workspace_id == sample_workspace.id
        assert agent.workspace.name == "Test Workspace"

    def test_bulk_migrate_agents_to_default_workspace(self, db_session, sample_workspace, sample_user):
        """Test bulk migration of agents to default workspace"""
        # Create multiple agents without workspace
        agents = [
            AgentSwarmInstance(
                name=f"Agent {i}",
                model="claude-3-opus-20240229",
                user_id=sample_user.id
            )
            for i in range(5)
        ]
        db_session.add_all(agents)
        db_session.commit()

        # Verify all have no workspace
        agents_without_workspace = db_session.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.workspace_id.is_(None)
        ).count()
        assert agents_without_workspace == 5

        # Bulk migrate to default workspace
        db_session.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.workspace_id.is_(None)
        ).update({"workspace_id": sample_workspace.id})
        db_session.commit()

        # Verify all have workspace
        agents_with_workspace = db_session.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.workspace_id == sample_workspace.id
        ).count()
        assert agents_with_workspace == 5


class TestAgentSwarmInstanceExistingFunctionality:
    """Test that existing AgentSwarmInstance functionality still works"""

    def test_agent_status_enum(self, db_session, sample_workspace, sample_user):
        """Test that agent status enum still works correctly"""
        agent = AgentSwarmInstance(
            name="Status Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id,
            status=AgentSwarmStatus.RUNNING
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert agent.status == AgentSwarmStatus.RUNNING

    def test_agent_heartbeat_configuration(self, db_session, sample_workspace, sample_user):
        """Test that heartbeat configuration still works"""
        agent = AgentSwarmInstance(
            name="Heartbeat Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id,
            heartbeat_enabled=True,
            heartbeat_interval=HeartbeatInterval.FIFTEEN_MINUTES
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert agent.heartbeat_enabled is True
        assert agent.heartbeat_interval == HeartbeatInterval.FIFTEEN_MINUTES

    def test_agent_user_relationship(self, db_session, sample_workspace, sample_user):
        """Test that user relationship still works"""
        agent = AgentSwarmInstance(
            name="User Relationship Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert agent.user is not None
        assert agent.user.id == sample_user.id
        assert agent.user.email == "test@example.com"

    def test_agent_heartbeat_executions_relationship(self, db_session, sample_workspace, sample_user):
        """Test that heartbeat_executions relationship still works"""
        agent = AgentSwarmInstance(
            name="Heartbeat Exec Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert hasattr(agent, "heartbeat_executions")
        assert isinstance(agent.heartbeat_executions, list)
        assert len(agent.heartbeat_executions) == 0


class TestAgentSwarmInstanceUserIntegration:
    """Test AgentSwarmInstance integration with User"""

    def test_user_id_has_index(self, db_engine):
        """Test that user_id column has an index"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        indexes = inspector.get_indexes("agent_swarm_instances")

        # Find index on user_id column
        user_id_indexed = any(
            "user_id" in idx.get("column_names", [])
            for idx in indexes
        )
        assert user_id_indexed, "user_id column should have an index"

    def test_user_id_foreign_key_constraint(self, db_engine):
        """Test that user_id has foreign key constraint to users table"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        foreign_keys = inspector.get_foreign_keys("agent_swarm_instances")

        # Find foreign key on user_id
        user_fk = any(
            fk.get("constrained_columns") == ["user_id"] and
            fk.get("referred_table") == "users" and
            fk.get("referred_columns") == ["id"]
            for fk in foreign_keys
        )
        assert user_fk, "user_id should have foreign key to users.id"

    def test_user_foreign_key_on_delete_cascade(self, db_engine):
        """Test that user_id foreign key has ON DELETE CASCADE"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        foreign_keys = inspector.get_foreign_keys("agent_swarm_instances")

        # Find user_id foreign key and check ondelete
        user_fk = next(
            (fk for fk in foreign_keys
             if fk.get("constrained_columns") == ["user_id"]),
            None
        )
        assert user_fk is not None
        # The model uses CASCADE for user deletion
        assert user_fk.get("options", {}).get("ondelete") == "CASCADE"

    def test_user_agents_relationship(self, db_session, sample_workspace, sample_user):
        """Test that user has agents back-reference"""
        agent1 = AgentSwarmInstance(
            name="User Agent 1",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        agent2 = AgentSwarmInstance(
            name="User Agent 2",
            model="claude-3-sonnet-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add_all([agent1, agent2])
        db_session.commit()
        db_session.refresh(sample_user)

        assert hasattr(sample_user, "agents")
        assert len(sample_user.agents) == 2
        agent_names = {agent.name for agent in sample_user.agents}
        assert "User Agent 1" in agent_names
        assert "User Agent 2" in agent_names

    def test_user_delete_cascades_to_agents_via_workspace(self, db_session, sample_workspace):
        """Test that deleting user (via workspace cascade) cascades to delete agents"""
        # Create a new workspace with user and agent
        workspace2 = Workspace(
            name="Workspace 2",
            slug="workspace-2"
        )
        db_session.add(workspace2)
        db_session.commit()
        db_session.refresh(workspace2)

        user = User(
            email="delete_test@example.com",
            workspace_id=workspace2.id
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        agent = AgentSwarmInstance(
            name="Delete Cascade Test",
            model="claude-3-opus-20240229",
            user_id=user.id,
            workspace_id=workspace2.id
        )
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id

        # Delete workspace (which cascades to user, which cascades to agent)
        db_session.delete(workspace2)
        db_session.commit()

        # Verify agent was also deleted (CASCADE behavior through workspace → user → agent)
        found_agent = db_session.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()
        assert found_agent is None

    def test_query_agents_by_user_id(self, db_session, sample_workspace, sample_user):
        """Test querying all agents for a specific user"""
        agent1 = AgentSwarmInstance(
            name="User Query 1",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        agent2 = AgentSwarmInstance(
            name="User Query 2",
            model="claude-3-sonnet-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add_all([agent1, agent2])
        db_session.commit()

        # Query agents by user_id
        agents = db_session.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.user_id == sample_user.id
        ).all()

        assert len(agents) == 2
        agent_names = {agent.name for agent in agents}
        assert "User Query 1" in agent_names
        assert "User Query 2" in agent_names


class TestAgentSwarmInstanceRepr:
    """Test agent string representation"""

    def test_agent_repr(self, db_session, sample_workspace, sample_user):
        """Test that agent has meaningful string representation"""
        agent = AgentSwarmInstance(
            name="Repr Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id,
            status=AgentSwarmStatus.RUNNING
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        repr_str = repr(agent)
        assert "AgentSwarmInstance" in repr_str
        assert "Repr Test" in repr_str
        assert "running" in repr_str or "RUNNING" in repr_str.upper()


class TestAgentConversationAttachment:
    """
    TDD Tests for Issue #104: Extend AgentSwarmInstance for Conversations

    RED Phase: Write tests FIRST to define the expected behavior.
    These tests will fail until the implementation is complete.
    """

    def test_current_conversation_id_column_exists(self, db_engine):
        """Test that current_conversation_id column exists in agent_swarm_instances table"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        columns = inspector.get_columns("agent_swarm_instances")

        column_names = [col["name"] for col in columns]
        assert "current_conversation_id" in column_names, "current_conversation_id column should exist"

    def test_current_conversation_id_is_nullable(self, db_engine):
        """Test that current_conversation_id column is nullable"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        columns = inspector.get_columns("agent_swarm_instances")

        current_conv_col = next(
            (col for col in columns if col["name"] == "current_conversation_id"),
            None
        )
        assert current_conv_col is not None
        assert current_conv_col["nullable"] is True, "current_conversation_id should be nullable"

    def test_current_conversation_id_foreign_key(self, db_engine):
        """Test that current_conversation_id has foreign key to conversations table"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        foreign_keys = inspector.get_foreign_keys("agent_swarm_instances")

        conv_fk = any(
            fk.get("constrained_columns") == ["current_conversation_id"] and
            fk.get("referred_table") == "conversations" and
            fk.get("referred_columns") == ["id"]
            for fk in foreign_keys
        )
        assert conv_fk, "current_conversation_id should have foreign key to conversations.id"

    def test_agent_has_current_conversation_relationship(self, db_session, sample_workspace, sample_user):
        """Test that agent has current_conversation relationship attribute"""
        from backend.models.conversation import Conversation

        agent = AgentSwarmInstance(
            name="Conversation Relationship Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert hasattr(agent, "current_conversation"), "Agent should have current_conversation relationship"

    def test_attach_conversation_sets_current_conversation_id(self, db_session, sample_workspace, sample_user):
        """Test that attach_conversation() sets current_conversation_id"""
        from backend.models.conversation import Conversation

        # Create agent and conversation
        agent = AgentSwarmInstance(
            name="Attach Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        conversation = Conversation(
            workspace_id=sample_workspace.id,
            agent_swarm_instance_id=agent.id,
            user_id=sample_user.id,
            channel="test",
            channel_conversation_id=f"test_conv_{agent.id}"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        # Attach conversation
        agent.attach_conversation(conversation.id)
        db_session.commit()
        db_session.refresh(agent)

        assert agent.current_conversation_id == conversation.id

    def test_attach_conversation_method_exists(self, db_session, sample_workspace, sample_user):
        """Test that attach_conversation() method exists"""
        agent = AgentSwarmInstance(
            name="Method Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert hasattr(agent, "attach_conversation"), "Agent should have attach_conversation method"
        assert callable(agent.attach_conversation), "attach_conversation should be callable"

    def test_detach_conversation_clears_current_conversation_id(self, db_session, sample_workspace, sample_user):
        """Test that detach_conversation() clears current_conversation_id"""
        from backend.models.conversation import Conversation

        # Create agent and conversation
        agent = AgentSwarmInstance(
            name="Detach Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        conversation = Conversation(
            workspace_id=sample_workspace.id,
            agent_swarm_instance_id=agent.id,
            user_id=sample_user.id,
            channel="test",
            channel_conversation_id=f"test_conv_{agent.id}"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        # Attach then detach
        agent.attach_conversation(conversation.id)
        db_session.commit()
        db_session.refresh(agent)

        agent.detach_conversation()
        db_session.commit()
        db_session.refresh(agent)

        assert agent.current_conversation_id is None

    def test_detach_conversation_method_exists(self, db_session, sample_workspace, sample_user):
        """Test that detach_conversation() method exists"""
        agent = AgentSwarmInstance(
            name="Detach Method Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert hasattr(agent, "detach_conversation"), "Agent should have detach_conversation method"
        assert callable(agent.detach_conversation), "detach_conversation should be callable"

    def test_get_active_conversation_returns_conversation_object(self, db_session, sample_workspace, sample_user):
        """Test that get_active_conversation() returns Conversation object"""
        from backend.models.conversation import Conversation

        # Create agent and conversation
        agent = AgentSwarmInstance(
            name="Get Active Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        conversation = Conversation(
            workspace_id=sample_workspace.id,
            agent_swarm_instance_id=agent.id,
            user_id=sample_user.id,
            channel="test",
            channel_conversation_id=f"test_conv_{agent.id}"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        # Attach conversation
        agent.attach_conversation(conversation.id)
        db_session.commit()
        db_session.refresh(agent)

        # Get active conversation
        active_conv = agent.get_active_conversation()

        assert active_conv is not None
        assert active_conv.id == conversation.id
        assert isinstance(active_conv, Conversation)

    def test_get_active_conversation_returns_none_when_no_conversation(self, db_session, sample_workspace, sample_user):
        """Test that get_active_conversation() returns None when no conversation attached"""
        agent = AgentSwarmInstance(
            name="No Active Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        active_conv = agent.get_active_conversation()
        assert active_conv is None

    def test_get_active_conversation_method_exists(self, db_session, sample_workspace, sample_user):
        """Test that get_active_conversation() method exists"""
        agent = AgentSwarmInstance(
            name="Get Method Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert hasattr(agent, "get_active_conversation"), "Agent should have get_active_conversation method"
        assert callable(agent.get_active_conversation), "get_active_conversation should be callable"

    def test_multiple_agents_attach_different_conversations(self, db_session, sample_workspace, sample_user):
        """Test that multiple agents can attach to different conversations"""
        from backend.models.conversation import Conversation

        # Create two agents
        agent1 = AgentSwarmInstance(
            name="Agent 1",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        agent2 = AgentSwarmInstance(
            name="Agent 2",
            model="claude-3-sonnet-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add_all([agent1, agent2])
        db_session.commit()
        db_session.refresh(agent1)
        db_session.refresh(agent2)

        # Create two conversations
        conv1 = Conversation(
            workspace_id=sample_workspace.id,
            agent_swarm_instance_id=agent1.id,
            user_id=sample_user.id,
            channel="test",
            channel_conversation_id=f"test_conv_{agent1.id}_1"
        )
        conv2 = Conversation(
            workspace_id=sample_workspace.id,
            agent_swarm_instance_id=agent2.id,
            user_id=sample_user.id,
            channel="test",
            channel_conversation_id=f"test_conv_{agent2.id}_2"
        )
        db_session.add_all([conv1, conv2])
        db_session.commit()
        db_session.refresh(conv1)
        db_session.refresh(conv2)

        # Attach different conversations
        agent1.attach_conversation(conv1.id)
        agent2.attach_conversation(conv2.id)
        db_session.commit()
        db_session.refresh(agent1)
        db_session.refresh(agent2)

        assert agent1.current_conversation_id == conv1.id
        assert agent2.current_conversation_id == conv2.id
        assert agent1.current_conversation_id != agent2.current_conversation_id

    def test_conversation_relationship_loads_correctly(self, db_session, sample_workspace, sample_user):
        """Test that conversation relationship loads correctly via current_conversation"""
        from backend.models.conversation import Conversation

        # Create agent and conversation
        agent = AgentSwarmInstance(
            name="Relationship Load Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        conversation = Conversation(
            workspace_id=sample_workspace.id,
            agent_swarm_instance_id=agent.id,
            user_id=sample_user.id,
            channel="test",
            channel_conversation_id=f"test_conv_{agent.id}"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        # Attach conversation
        agent.attach_conversation(conversation.id)
        db_session.commit()
        db_session.refresh(agent)

        # Access via relationship
        assert agent.current_conversation is not None
        assert agent.current_conversation.id == conversation.id
        assert agent.current_conversation.workspace_id == sample_workspace.id

    def test_attach_conversation_validates_workspace_match(self, db_session, sample_workspace, sample_user):
        """Test that attach_conversation() validates conversation belongs to agent's workspace"""
        from backend.models.conversation import Conversation
        from backend.models.workspace import Workspace

        # Create agent in workspace1
        agent = AgentSwarmInstance(
            name="Validation Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        # Create another workspace
        workspace2 = Workspace(
            name="Workspace 2",
            slug="workspace-2"
        )
        db_session.add(workspace2)
        db_session.commit()
        db_session.refresh(workspace2)

        # Create user in workspace2
        user2 = User(
            email="user2@example.com",
            workspace_id=workspace2.id
        )
        db_session.add(user2)
        db_session.commit()
        db_session.refresh(user2)

        # Create agent2 in workspace2
        agent2 = AgentSwarmInstance(
            name="Agent 2",
            model="claude-3-opus-20240229",
            user_id=user2.id,
            workspace_id=workspace2.id
        )
        db_session.add(agent2)
        db_session.commit()
        db_session.refresh(agent2)

        # Create conversation in workspace2
        conversation = Conversation(
            workspace_id=workspace2.id,
            agent_swarm_instance_id=agent2.id,
            user_id=user2.id,
            channel="test",
            channel_conversation_id=f"test_conv_{agent2.id}_ws2"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        # Try to attach conversation from workspace2 to agent in workspace1
        with pytest.raises(ValueError, match="Conversation must belong to the same workspace"):
            agent.attach_conversation(conversation.id)

    def test_attach_conversation_validates_conversation_exists(self, db_session, sample_workspace, sample_user):
        """Test that attach_conversation() validates conversation exists"""
        agent = AgentSwarmInstance(
            name="Exists Validation Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        # Try to attach non-existent conversation
        fake_conversation_id = uuid4()
        with pytest.raises(ValueError, match="Conversation .* not found"):
            agent.attach_conversation(fake_conversation_id)

    def test_agent_can_switch_conversations(self, db_session, sample_workspace, sample_user):
        """Test that agent can switch from one conversation to another"""
        from backend.models.conversation import Conversation

        # Create agent
        agent = AgentSwarmInstance(
            name="Switch Test",
            model="claude-3-opus-20240229",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        # Create two conversations
        conv1 = Conversation(
            workspace_id=sample_workspace.id,
            agent_swarm_instance_id=agent.id,
            user_id=sample_user.id,
            channel="test",
            channel_conversation_id=f"test_conv_{agent.id}_switch1"
        )
        conv2 = Conversation(
            workspace_id=sample_workspace.id,
            agent_swarm_instance_id=agent.id,
            user_id=sample_user.id,
            channel="test",
            channel_conversation_id=f"test_conv_{agent.id}_switch2"
        )
        db_session.add_all([conv1, conv2])
        db_session.commit()
        db_session.refresh(conv1)
        db_session.refresh(conv2)

        # Attach first conversation
        agent.attach_conversation(conv1.id)
        db_session.commit()
        db_session.refresh(agent)
        assert agent.current_conversation_id == conv1.id

        # Switch to second conversation
        agent.attach_conversation(conv2.id)
        db_session.commit()
        db_session.refresh(agent)
        assert agent.current_conversation_id == conv2.id
        assert agent.current_conversation_id != conv1.id
