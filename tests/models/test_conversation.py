"""
Test Conversation Model

Tests conversation creation, relationships, foreign key constraints,
cascade behaviors, unique constraints, status enum, and timestamps
following TDD principles.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from backend.db.base_class import Base
from backend.models.conversation import Conversation, ConversationStatus
from backend.models.workspace import Workspace
from backend.models.user import User
from backend.models.agent_swarm_lifecycle import AgentSwarmInstance, AgentSwarmStatus


@pytest.fixture
def db_engine():
    """Create in-memory SQLite database for testing"""
    from sqlalchemy import Table, Column, String, Text, DateTime, Integer, Boolean, Float, JSON
    from sqlalchemy.dialects.postgresql import UUID as PGUUID

    engine = create_engine("sqlite:///:memory:")

    # Enable foreign key constraints in SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create only the tables we need, excluding ARRAY columns
    # We'll manually recreate agent_swarm_instances without ARRAY
    from backend.models.workspace import Workspace
    from backend.models.user import User
    from backend.models.conversation import Conversation

    # Create workspace and user tables normally
    Workspace.__table__.create(bind=engine, checkfirst=True)
    User.__table__.create(bind=engine, checkfirst=True)

    # Manually create agent_swarm_instances table without ARRAY columns for SQLite compatibility
    from sqlalchemy import MetaData
    metadata = MetaData()

    agent_table = Table(
        'agent_swarm_instances', metadata,
        Column('id', PGUUID(), primary_key=True),
        Column('name', String(255), nullable=False, index=True),
        Column('persona', Text, nullable=True),
        Column('model', String(255), nullable=False),
        Column('user_id', PGUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        Column('workspace_id', PGUUID(), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True),
        Column('status', String(50), nullable=False, index=True),
        Column('openclaw_session_key', String(255), nullable=True, unique=True, index=True),
        Column('openclaw_agent_id', String(255), nullable=True, index=True),
        Column('heartbeat_enabled', Boolean, default=False, nullable=False),
        Column('heartbeat_interval', String(10), nullable=True),
        Column('last_heartbeat_at', DateTime(timezone=True), nullable=True),
        Column('next_heartbeat_at', DateTime(timezone=True), nullable=True),
        Column('configuration', JSON, default=dict, nullable=True),
        Column('error_message', Text, nullable=True),
        Column('error_count', Integer, default=0, nullable=False),
        Column('last_error_at', DateTime(timezone=True), nullable=True),
        Column('created_at', DateTime(timezone=True), nullable=False),
        Column('updated_at', DateTime(timezone=True)),
        Column('provisioned_at', DateTime(timezone=True), nullable=True),
        Column('paused_at', DateTime(timezone=True), nullable=True),
        Column('stopped_at', DateTime(timezone=True), nullable=True),
    )

    metadata.create_all(engine)

    # Create conversation table normally
    Conversation.__table__.create(bind=engine, checkfirst=True)

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
def workspace(db_session):
    """Create a test workspace"""
    workspace = Workspace(
        id=uuid4(),
        name="Test Workspace",
        slug="test-workspace"
    )
    db_session.add(workspace)
    db_session.commit()
    db_session.refresh(workspace)
    return workspace


@pytest.fixture
def user(db_session, workspace):
    """Create a test user"""
    user = User(
        id=uuid4(),
        email="test@example.com",
        workspace_id=workspace.id
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def agent(db_session, user, workspace):
    """Create a test agent"""
    agent = AgentSwarmInstance(
        id=uuid4(),
        name="Test Agent",
        model="claude-3-5-sonnet-20241022",
        user_id=user.id,
        workspace_id=workspace.id,
        status=AgentSwarmStatus.RUNNING,
        heartbeat_enabled=False,
        error_count=0
    )
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    return agent


class TestConversationCreation:
    """Test conversation creation and basic attributes"""

    def test_create_conversation_with_required_fields(self, db_session, workspace, agent):
        """Test creating a conversation with required fields only"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.id is not None
        assert conversation.workspace_id == workspace.id
        assert conversation.agent_id == agent.id
        assert conversation.user_id is None
        assert conversation.started_at is not None
        assert isinstance(conversation.started_at, datetime)
        assert conversation.status == ConversationStatus.ACTIVE
        assert conversation.message_count == 0

    def test_create_conversation_with_user(self, db_session, workspace, agent, user):
        """Test creating a conversation with a user"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            user_id=user.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.id is not None
        assert conversation.user_id == user.id

    def test_create_conversation_with_openclaw_session(self, db_session, workspace, agent):
        """Test creating a conversation with OpenClaw session tracking"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            openclaw_session_key="session_12345abcde"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.openclaw_session_key == "session_12345abcde"

    def test_create_conversation_with_zerodb_fields(self, db_session, workspace, agent):
        """Test creating a conversation with ZeroDB integration fields"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            zerodb_table_name="custom_messages",
            zerodb_conversation_row_id="zerodb_row_123"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.zerodb_table_name == "custom_messages"
        assert conversation.zerodb_conversation_row_id == "zerodb_row_123"

    def test_conversation_id_is_uuid(self, db_session, workspace, agent):
        """Test that conversation ID is generated as UUID"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.id is not None
        assert len(str(conversation.id)) == 36  # UUID string format

    def test_conversation_defaults(self, db_session, workspace, agent):
        """Test that conversation has correct default values"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.status == ConversationStatus.ACTIVE
        assert conversation.message_count == 0
        assert conversation.zerodb_table_name == "messages"
        assert conversation.last_message_at is None


class TestConversationStatusEnum:
    """Test conversation status enumeration"""

    def test_status_active(self, db_session, workspace, agent):
        """Test conversation with ACTIVE status"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            status=ConversationStatus.ACTIVE
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.status == ConversationStatus.ACTIVE
        assert conversation.status.value == "active"

    def test_status_archived(self, db_session, workspace, agent):
        """Test conversation with ARCHIVED status"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            status=ConversationStatus.ARCHIVED
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.status == ConversationStatus.ARCHIVED
        assert conversation.status.value == "archived"

    def test_status_deleted(self, db_session, workspace, agent):
        """Test conversation with DELETED status"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            status=ConversationStatus.DELETED
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.status == ConversationStatus.DELETED
        assert conversation.status.value == "deleted"


class TestOpenclawSessionKeyConstraint:
    """Test unique constraint on openclaw_session_key"""

    def test_openclaw_session_key_unique_constraint(self, db_session, workspace, agent, user):
        """Test that openclaw_session_key must be unique"""
        conversation1 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            openclaw_session_key="unique_session_123"
        )
        db_session.add(conversation1)
        db_session.commit()

        # Create second agent for different conversation
        agent2 = AgentSwarmInstance(
            id=uuid4(),
            name="Second Agent",
            model="claude-3-5-sonnet-20241022",
            user_id=user.id,
            workspace_id=workspace.id,
            status=AgentSwarmStatus.RUNNING,
            heartbeat_enabled=False,
            error_count=0
        )
        db_session.add(agent2)
        db_session.commit()

        # Try to create another conversation with same session key
        conversation2 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent2.id,
            openclaw_session_key="unique_session_123"
        )
        db_session.add(conversation2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_openclaw_session_key_null_allowed(self, db_session, workspace, agent, user):
        """Test that multiple conversations can have null openclaw_session_key"""
        # Create second agent
        agent2 = AgentSwarmInstance(
            id=uuid4(),
            name="Second Agent",
            model="claude-3-5-sonnet-20241022",
            user_id=user.id,
            workspace_id=workspace.id,
            status=AgentSwarmStatus.RUNNING,
            heartbeat_enabled=False,
            error_count=0
        )
        db_session.add(agent2)
        db_session.commit()

        conversation1 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            openclaw_session_key=None
        )
        conversation2 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent2.id,
            openclaw_session_key=None
        )
        db_session.add(conversation1)
        db_session.add(conversation2)
        db_session.commit()

        # Both should be created successfully
        assert conversation1.id is not None
        assert conversation2.id is not None


class TestWorkspaceForeignKey:
    """Test workspace_id foreign key constraint"""

    def test_workspace_foreign_key_valid(self, db_session, workspace, agent):
        """Test that valid workspace_id is accepted"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.workspace_id == workspace.id

    def test_workspace_foreign_key_invalid(self, db_session, agent):
        """Test that invalid workspace_id is rejected"""
        invalid_workspace_id = uuid4()
        conversation = Conversation(
            workspace_id=invalid_workspace_id,
            agent_id=agent.id
        )
        db_session.add(conversation)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_workspace_id_not_null(self, db_session, agent):
        """Test that workspace_id cannot be null"""
        conversation = Conversation(
            agent_id=agent.id
        )
        db_session.add(conversation)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_workspace_id_indexed(self, db_engine):
        """Test that workspace_id column has an index"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        indexes = inspector.get_indexes("conversations")

        workspace_indexed = any(
            "workspace_id" in idx.get("column_names", [])
            for idx in indexes
        )
        assert workspace_indexed, "workspace_id column should have an index"


class TestAgentForeignKey:
    """Test agent_id foreign key constraint"""

    def test_agent_foreign_key_valid(self, db_session, workspace, agent):
        """Test that valid agent_id is accepted"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.agent_id == agent.id

    def test_agent_foreign_key_invalid(self, db_session, workspace):
        """Test that invalid agent_id is rejected"""
        invalid_agent_id = uuid4()
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=invalid_agent_id
        )
        db_session.add(conversation)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_agent_id_not_null(self, db_session, workspace):
        """Test that agent_id cannot be null"""
        conversation = Conversation(
            workspace_id=workspace.id
        )
        db_session.add(conversation)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_agent_id_indexed(self, db_engine):
        """Test that agent_id column has an index"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        indexes = inspector.get_indexes("conversations")

        agent_indexed = any(
            "agent_id" in idx.get("column_names", [])
            for idx in indexes
        )
        assert agent_indexed, "agent_id column should have an index"


class TestUserForeignKey:
    """Test user_id foreign key constraint"""

    def test_user_foreign_key_valid(self, db_session, workspace, agent, user):
        """Test that valid user_id is accepted"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            user_id=user.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.user_id == user.id

    def test_user_foreign_key_invalid(self, db_session, workspace, agent):
        """Test that invalid user_id is rejected"""
        invalid_user_id = uuid4()
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            user_id=invalid_user_id
        )
        db_session.add(conversation)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_user_id_nullable(self, db_session, workspace, agent):
        """Test that user_id can be null"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            user_id=None
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.user_id is None

    def test_user_id_indexed(self, db_engine):
        """Test that user_id column has an index"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        indexes = inspector.get_indexes("conversations")

        user_indexed = any(
            "user_id" in idx.get("column_names", [])
            for idx in indexes
        )
        assert user_indexed, "user_id column should have an index"


class TestCascadeDeleteWorkspace:
    """Test CASCADE delete when workspace is deleted"""

    def test_cascade_delete_conversations_when_workspace_deleted(self, db_session, workspace, agent, user):
        """Test that conversations are deleted when workspace is deleted"""
        # Create second agent
        agent2 = AgentSwarmInstance(
            id=uuid4(),
            name="Second Agent",
            model="claude-3-5-sonnet-20241022",
            user_id=user.id,
            workspace_id=workspace.id,
            status=AgentSwarmStatus.RUNNING,
            heartbeat_enabled=False,
            error_count=0
        )
        db_session.add(agent2)
        db_session.commit()

        # Create multiple conversations
        conversation1 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        conversation2 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent2.id
        )
        db_session.add(conversation1)
        db_session.add(conversation2)
        db_session.commit()

        conversation1_id = conversation1.id
        conversation2_id = conversation2.id

        # Delete workspace
        db_session.delete(workspace)
        db_session.commit()

        # Verify conversations are deleted
        assert db_session.query(Conversation).filter(Conversation.id == conversation1_id).first() is None
        assert db_session.query(Conversation).filter(Conversation.id == conversation2_id).first() is None


class TestCascadeDeleteAgent:
    """Test CASCADE delete when agent is deleted"""

    def test_cascade_delete_conversations_when_agent_deleted(self, db_session, workspace, agent, user):
        """Test that conversations are deleted when agent is deleted"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            user_id=user.id
        )
        db_session.add(conversation)
        db_session.commit()

        conversation_id = conversation.id

        # Delete agent
        db_session.delete(agent)
        db_session.commit()

        # Verify conversation is deleted
        assert db_session.query(Conversation).filter(Conversation.id == conversation_id).first() is None


class TestSetNullUser:
    """Test SET NULL when user is deleted"""

    def test_set_null_user_when_user_deleted(self, db_session, workspace, agent, user):
        """Test that user_id is set to NULL when user is deleted"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            user_id=user.id
        )
        db_session.add(conversation)
        db_session.commit()

        conversation_id = conversation.id

        # Delete user
        db_session.delete(user)
        db_session.commit()

        # Verify conversation still exists but user_id is NULL
        found_conversation = db_session.query(Conversation).filter(Conversation.id == conversation_id).first()
        assert found_conversation is not None
        assert found_conversation.user_id is None


class TestConversationRelationships:
    """Test conversation relationships with workspace, agent, and user"""

    def test_workspace_relationship(self, db_session, workspace, agent):
        """Test that conversation has workspace relationship"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        # Access workspace relationship
        assert conversation.workspace is not None
        assert conversation.workspace.id == workspace.id
        assert conversation.workspace.name == workspace.name

    def test_agent_relationship(self, db_session, workspace, agent):
        """Test that conversation has agent relationship"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        # Access agent relationship
        assert conversation.agent is not None
        assert conversation.agent.id == agent.id
        assert conversation.agent.name == agent.name

    def test_user_relationship(self, db_session, workspace, agent, user):
        """Test that conversation has user relationship"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            user_id=user.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        # Access user relationship
        assert conversation.user is not None
        assert conversation.user.id == user.id
        assert conversation.user.email == user.email

    def test_workspace_conversations_backref(self, db_session, workspace, agent, user):
        """Test that workspace has conversations back-reference"""
        # Create second agent
        agent2 = AgentSwarmInstance(
            id=uuid4(),
            name="Second Agent",
            model="claude-3-5-sonnet-20241022",
            user_id=user.id,
            workspace_id=workspace.id,
            status=AgentSwarmStatus.RUNNING,
            heartbeat_enabled=False,
            error_count=0
        )
        db_session.add(agent2)
        db_session.commit()

        conversation1 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        conversation2 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent2.id
        )
        db_session.add(conversation1)
        db_session.add(conversation2)
        db_session.commit()
        db_session.refresh(workspace)

        # Access conversations through workspace
        assert len(workspace.conversations) == 2

    def test_agent_conversations_backref(self, db_session, workspace, agent):
        """Test that agent has conversations back-reference"""
        conversation1 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        conversation2 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        db_session.add(conversation1)
        db_session.add(conversation2)
        db_session.commit()
        db_session.refresh(agent)

        # Access conversations through agent
        assert len(agent.conversations) == 2

    def test_user_conversations_backref(self, db_session, workspace, agent, user):
        """Test that user has conversations back-reference"""
        conversation1 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            user_id=user.id
        )
        conversation2 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            user_id=user.id
        )
        db_session.add(conversation1)
        db_session.add(conversation2)
        db_session.commit()
        db_session.refresh(user)

        # Access conversations through user
        assert len(user.conversations) == 2


class TestMessageCount:
    """Test message_count field"""

    def test_message_count_default_zero(self, db_session, workspace, agent):
        """Test that message_count defaults to 0"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.message_count == 0

    def test_message_count_increment(self, db_session, workspace, agent):
        """Test incrementing message_count"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        # Increment message count
        conversation.message_count += 1
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.message_count == 1

        # Increment again
        conversation.message_count += 1
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.message_count == 2


class TestTimestamps:
    """Test conversation timestamp fields"""

    def test_started_at_auto_generated(self, db_session, workspace, agent):
        """Test that started_at is auto-generated"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.started_at is not None
        assert isinstance(conversation.started_at, datetime)

        # Should be within the last minute
        now = datetime.now(timezone.utc)
        time_diff = (now - conversation.started_at.replace(tzinfo=timezone.utc)).total_seconds()
        assert time_diff < 60

    def test_last_message_at_null_on_creation(self, db_session, workspace, agent):
        """Test that last_message_at is null on creation"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.last_message_at is None

    def test_last_message_at_can_be_updated(self, db_session, workspace, agent):
        """Test that last_message_at can be updated"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        # Update last_message_at
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        conversation.last_message_at = now
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.last_message_at is not None
        assert isinstance(conversation.last_message_at, datetime)


class TestConversationQuery:
    """Test conversation query operations"""

    def test_query_by_workspace(self, db_session, workspace, agent, user):
        """Test querying conversations by workspace"""
        # Create second agent
        agent2 = AgentSwarmInstance(
            id=uuid4(),
            name="Second Agent",
            model="claude-3-5-sonnet-20241022",
            user_id=user.id,
            workspace_id=workspace.id,
            status=AgentSwarmStatus.RUNNING,
            heartbeat_enabled=False,
            error_count=0
        )
        db_session.add(agent2)
        db_session.commit()

        conversation1 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        conversation2 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent2.id
        )
        db_session.add(conversation1)
        db_session.add(conversation2)
        db_session.commit()

        # Query by workspace
        conversations = db_session.query(Conversation).filter(
            Conversation.workspace_id == workspace.id
        ).all()
        assert len(conversations) == 2

    def test_query_by_agent(self, db_session, workspace, agent):
        """Test querying conversations by agent"""
        conversation1 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        conversation2 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id
        )
        db_session.add(conversation1)
        db_session.add(conversation2)
        db_session.commit()

        # Query by agent
        conversations = db_session.query(Conversation).filter(
            Conversation.agent_id == agent.id
        ).all()
        assert len(conversations) == 2

    def test_query_by_user(self, db_session, workspace, agent, user):
        """Test querying conversations by user"""
        conversation1 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            user_id=user.id
        )
        conversation2 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            user_id=user.id
        )
        db_session.add(conversation1)
        db_session.add(conversation2)
        db_session.commit()

        # Query by user
        conversations = db_session.query(Conversation).filter(
            Conversation.user_id == user.id
        ).all()
        assert len(conversations) == 2

    def test_query_by_openclaw_session_key(self, db_session, workspace, agent):
        """Test querying conversation by openclaw_session_key"""
        conversation = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            openclaw_session_key="session_xyz"
        )
        db_session.add(conversation)
        db_session.commit()

        # Query by session key
        found_conversation = db_session.query(Conversation).filter(
            Conversation.openclaw_session_key == "session_xyz"
        ).first()
        assert found_conversation is not None
        assert found_conversation.id == conversation.id

    def test_query_by_status(self, db_session, workspace, agent, user):
        """Test querying conversations by status"""
        # Create second agent
        agent2 = AgentSwarmInstance(
            id=uuid4(),
            name="Second Agent",
            model="claude-3-5-sonnet-20241022",
            user_id=user.id,
            workspace_id=workspace.id,
            status=AgentSwarmStatus.RUNNING,
            heartbeat_enabled=False,
            error_count=0
        )
        db_session.add(agent2)
        db_session.commit()

        conversation1 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent.id,
            status=ConversationStatus.ACTIVE
        )
        conversation2 = Conversation(
            workspace_id=workspace.id,
            agent_id=agent2.id,
            status=ConversationStatus.ARCHIVED
        )
        db_session.add(conversation1)
        db_session.add(conversation2)
        db_session.commit()

        # Query by status
        active_conversations = db_session.query(Conversation).filter(
            Conversation.status == ConversationStatus.ACTIVE
        ).all()
        assert len(active_conversations) == 1
        assert active_conversations[0].id == conversation1.id


class TestStatusIndex:
    """Test status column index"""

    def test_status_indexed(self, db_engine):
        """Test that status column has an index"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        indexes = inspector.get_indexes("conversations")

        status_indexed = any(
            "status" in idx.get("column_names", [])
            for idx in indexes
        )
        assert status_indexed, "status column should have an index"
