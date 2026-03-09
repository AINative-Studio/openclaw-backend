"""
Test Conversation Model (Issue #103)

Comprehensive tests for conversation creation, relationships, foreign key constraints,
cascade behaviors, unique constraints, status enum, channel fields, metadata, and timestamps 
following TDD principles for Epic E9 Sprint 2.
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


@pytest.fixture
def db_engine():
    """Create in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")

    # Enable foreign key constraints in SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables
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





class TestConversationCreationIssue103:
    """Test conversation creation with Issue #103 requirements"""

    def test_create_conversation_with_required_fields(self, db_session, workspace, user):
        """Test creating a conversation with only required fields"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_12345"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.id is not None
        assert conversation.workspace_id == workspace.id
        assert conversation.user_id == user.id
        assert conversation.channel == "whatsapp"
        assert conversation.channel_conversation_id == "wa_12345"
        assert conversation.agent_swarm_instance_id is None  # Nullable
        assert conversation.status == ConversationStatus.ACTIVE
        assert conversation.created_at is not None

    def test_create_conversation_with_title(self, db_session, workspace, user):
        """Test creating a conversation with a title"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="slack",
            channel_conversation_id="slack_abc",
            title="Customer Support Conversation"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.title == "Customer Support Conversation"

    def test_create_conversation_with_metadata(self, db_session, workspace, user):
        """Test creating a conversation with channel-specific conversation_metadata"""
        meta_data = {
            "whatsapp_phone": "+1234567890",
            "customer_name": "John Doe",
            "priority": "high"
        }
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_meta_123",
            conversation_metadata=meta_data
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.conversation_metadata == meta_data
        assert conversation.conversation_metadata["whatsapp_phone"] == "+1234567890"

    def test_conversation_id_is_uuid(self, db_session, workspace, user):
        """Test that conversation ID is generated as UUID"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_uuid_test"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.id is not None
        assert len(str(conversation.id)) == 36  # UUID string format

    def test_conversation_defaults(self, db_session, workspace, user):
        """Test that conversation has correct default values"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_defaults"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.status == ConversationStatus.ACTIVE
        assert conversation.title is None
        assert conversation.conversation_metadata == {}
        assert conversation.archived_at is None
        assert conversation.agent_swarm_instance_id is None


class TestConversationStatusEnum:
    """Test conversation status enumeration"""

    def test_status_active(self, db_session, workspace, user):
        """Test conversation with ACTIVE status"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_active",
            status=ConversationStatus.ACTIVE
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.status == ConversationStatus.ACTIVE
        assert conversation.status.value == "active"

    def test_status_archived(self, db_session, workspace, user):
        """Test conversation with ARCHIVED status"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_archived",
            status=ConversationStatus.ARCHIVED
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.status == ConversationStatus.ARCHIVED
        assert conversation.status.value == "archived"

    def test_status_deleted(self, db_session, workspace, user):
        """Test conversation with DELETED status"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_deleted",
            status=ConversationStatus.DELETED
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.status == ConversationStatus.DELETED
        assert conversation.status.value == "deleted"


class TestChannelConversationIdConstraint:
    """Test unique constraint on (channel, channel_conversation_id)"""

    def test_unique_constraint_on_channel_and_channel_conversation_id(self, db_session, workspace, user):
        """Test that (channel, channel_conversation_id) combination must be unique"""
        conversation1 = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_unique_123"
        )
        db_session.add(conversation1)
        db_session.commit()

        # Try to create another conversation with same channel + channel_conversation_id
        conversation2 = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_unique_123"
        )
        db_session.add(conversation2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_same_channel_conversation_id_different_channels_allowed(self, db_session, workspace, user):
        """Test that same channel_conversation_id is allowed for different channels"""
        conversation1 = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="conv_123"
        )
        conversation2 = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="telegram",
            channel_conversation_id="conv_123"
        )
        db_session.add(conversation1)
        db_session.add(conversation2)
        db_session.commit()

        # Both should be created successfully
        assert conversation1.id is not None
        assert conversation2.id is not None


class TestWorkspaceForeignKey:
    """Test workspace_id foreign key constraint"""

    def test_workspace_foreign_key_valid(self, db_session, workspace, user):
        """Test that valid workspace_id is accepted"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_fk_valid"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.workspace_id == workspace.id

    def test_workspace_foreign_key_invalid(self, db_session, user):
        """Test that invalid workspace_id is rejected"""
        invalid_workspace_id = uuid4()
        conversation = Conversation(
            workspace_id=invalid_workspace_id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_fk_invalid"
        )
        db_session.add(conversation)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_workspace_id_not_null(self, db_session, user):
        """Test that workspace_id cannot be null"""
        conversation = Conversation(
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_no_workspace"
        )
        db_session.add(conversation)

        with pytest.raises(IntegrityError):
            db_session.commit()


class TestUserForeignKey:
    """Test user_id foreign key constraint"""

    def test_user_foreign_key_valid(self, db_session, workspace, user):
        """Test that valid user_id is accepted"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_user_valid"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.user_id == user.id

    def test_user_foreign_key_invalid(self, db_session, workspace):
        """Test that invalid user_id is rejected"""
        invalid_user_id = uuid4()
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=invalid_user_id,
            channel="whatsapp",
            channel_conversation_id="wa_user_invalid"
        )
        db_session.add(conversation)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_user_id_not_null(self, db_session, workspace):
        """Test that user_id cannot be null"""
        conversation = Conversation(
            workspace_id=workspace.id,
            channel="whatsapp",
            channel_conversation_id="wa_no_user"
        )
        db_session.add(conversation)

        with pytest.raises(IntegrityError):
            db_session.commit()


class TestCascadeDeleteWorkspace:
    """Test CASCADE delete when workspace is deleted"""

    def test_cascade_delete_conversations_when_workspace_deleted(self, db_session, workspace, user):
        """Test that conversations are deleted when workspace is deleted"""
        conversation1 = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_cascade_1"
        )
        conversation2 = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="telegram",
            channel_conversation_id="tg_cascade_2"
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


class TestConversationRelationships:
    """Test conversation relationships with workspace and user"""

    def test_workspace_relationship(self, db_session, workspace, user):
        """Test that conversation has workspace relationship"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_rel_workspace"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        # Access workspace relationship
        assert conversation.workspace is not None
        assert conversation.workspace.id == workspace.id
        assert conversation.workspace.name == workspace.name

    def test_user_relationship(self, db_session, workspace, user):
        """Test that conversation has user relationship"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_rel_user"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        # Access user relationship
        assert conversation.user is not None
        assert conversation.user.id == user.id
        assert conversation.user.email == user.email


class TestTimestamps:
    """Test conversation timestamp fields"""

    def test_created_at_auto_generated(self, db_session, workspace, user):
        """Test that created_at is auto-generated"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_created_at"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.created_at is not None
        assert isinstance(conversation.created_at, datetime)

        # Should be within the last minute
        now = datetime.now(timezone.utc)
        time_diff = (now - conversation.created_at.replace(tzinfo=timezone.utc)).total_seconds()
        assert time_diff < 60

    def test_archived_at_null_by_default(self, db_session, workspace, user):
        """Test that archived_at is null by default"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_archived_at"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.archived_at is None

    def test_archived_at_can_be_set(self, db_session, workspace, user):
        """Test that archived_at can be set when archiving"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_archive_set"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        # Archive conversation
        now = datetime.now(timezone.utc)
        conversation.archived_at = now
        conversation.status = ConversationStatus.ARCHIVED
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.archived_at is not None
        assert isinstance(conversation.archived_at, datetime)
        assert conversation.status == ConversationStatus.ARCHIVED


class TestArchivalWorkflow:
    """Test conversation archival workflow"""

    def test_archive_method(self, db_session, workspace, user):
        """Test that archive() method works correctly"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_archive_method"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.status == ConversationStatus.ACTIVE
        assert conversation.archived_at is None

        # Archive conversation
        conversation.archive()
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.status == ConversationStatus.ARCHIVED
        assert conversation.archived_at is not None
        assert isinstance(conversation.archived_at, datetime)


class TestHelperMethods:
    """Test conversation helper methods"""

    def test_is_active_method(self, db_session, workspace, user):
        """Test that is_active() method returns correct boolean"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_is_active"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.is_active() is True

        # Archive conversation
        conversation.status = ConversationStatus.ARCHIVED
        assert conversation.is_active() is False


class TestConversationQuery:
    """Test conversation query operations"""

    def test_query_by_workspace(self, db_session, workspace, user):
        """Test querying conversations by workspace"""
        conversation1 = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_query_1"
        )
        conversation2 = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="telegram",
            channel_conversation_id="tg_query_2"
        )
        db_session.add(conversation1)
        db_session.add(conversation2)
        db_session.commit()

        # Query by workspace
        conversations = db_session.query(Conversation).filter(
            Conversation.workspace_id == workspace.id
        ).all()
        assert len(conversations) == 2

    def test_query_by_channel(self, db_session, workspace, user):
        """Test querying conversations by channel"""
        conversation1 = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_channel_1"
        )
        conversation2 = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_channel_2"
        )
        conversation3 = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="telegram",
            channel_conversation_id="tg_channel_3"
        )
        db_session.add(conversation1)
        db_session.add(conversation2)
        db_session.add(conversation3)
        db_session.commit()

        # Query by channel
        whatsapp_conversations = db_session.query(Conversation).filter(
            Conversation.channel == "whatsapp"
        ).all()
        assert len(whatsapp_conversations) == 2

    def test_query_by_status(self, db_session, workspace, user):
        """Test querying conversations by status"""
        conversation1 = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_status_1",
            status=ConversationStatus.ACTIVE
        )
        conversation2 = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="telegram",
            channel_conversation_id="tg_status_2",
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


class TestConversationRepr:
    """Test conversation string representation"""

    def test_conversation_repr(self, db_session, workspace, user):
        """Test that conversation has a meaningful string representation"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_repr"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        repr_str = repr(conversation)
        assert "Conversation" in repr_str
        assert "whatsapp" in repr_str or conversation.status.value in repr_str


class TestMetadataField:
    """Test conversation_metadata JSON field operations"""

    def test_metadata_empty_by_default(self, db_session, workspace, user):
        """Test that conversation_metadata defaults to empty dict"""
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="whatsapp",
            channel_conversation_id="wa_meta_empty"
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.conversation_metadata == {}

    def test_metadata_can_store_complex_data(self, db_session, workspace, user):
        """Test that conversation_metadata can store complex JSON structures"""
        meta_data = {
            "customer": {
                "name": "Jane Doe",
                "phone": "+9876543210"
            },
            "tags": ["support", "urgent", "vip"],
            "priority": 5,
            "notes": "Customer is a premium tier subscriber"
        }
        conversation = Conversation(
            workspace_id=workspace.id,
            user_id=user.id,
            channel="slack",
            channel_conversation_id="slack_complex_meta",
            conversation_metadata=meta_data
        )
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert conversation.conversation_metadata["customer"]["name"] == "Jane Doe"
        assert "urgent" in conversation.conversation_metadata["tags"]
        assert conversation.conversation_metadata["priority"] == 5
