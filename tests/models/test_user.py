"""
Test User Model

Tests user creation, email uniqueness, foreign key constraints,
cascade deletes, and relationships following TDD principles.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from backend.db.base_class import Base
from backend.models.user import User
from backend.models.workspace import Workspace


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

    # Create tables needed for user tests
    from backend.models.workspace import Workspace
    from backend.models.conversation import Conversation

    Workspace.__table__.create(bind=engine, checkfirst=True)
    User.__table__.create(bind=engine, checkfirst=True)
    # Create conversations table to allow cascade deletes to work
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


class TestUserCreation:
    """Test user creation and basic attributes"""

    def test_create_user_with_required_fields(self, db_session, workspace):
        """Test creating a user with all required fields"""
        user = User(
            email="test@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.id is not None
        assert user.email == "test@example.com"
        assert user.workspace_id == workspace.id
        assert user.created_at is not None
        assert isinstance(user.created_at, datetime)

    def test_create_user_with_full_name(self, db_session, workspace):
        """Test creating a user with optional full_name field"""
        user = User(
            email="fullname@example.com",
            full_name="John Doe",
            workspace_id=workspace.id
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.full_name == "John Doe"

    def test_create_user_without_full_name(self, db_session, workspace):
        """Test that full_name is optional and defaults to None"""
        user = User(
            email="nofullname@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.full_name is None

    def test_user_id_is_uuid(self, db_session, workspace):
        """Test that user ID is generated as UUID"""
        user = User(
            email="uuid@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.id is not None
        # UUID should be a valid UUID object
        assert len(str(user.id)) == 36  # UUID string format

    def test_user_created_at_auto_generated(self, db_session, workspace):
        """Test that created_at timestamp is auto-generated"""
        user = User(
            email="timestamp@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.created_at is not None
        # Should be within the last minute
        now = datetime.now(timezone.utc)
        time_diff = (now - user.created_at.replace(tzinfo=timezone.utc)).total_seconds()
        assert time_diff < 60

    def test_user_updated_at_auto_generated_on_update(self, db_session, workspace):
        """Test that updated_at timestamp is auto-generated on update"""
        user = User(
            email="updated@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Initially updated_at should be None or equal to created_at
        original_updated_at = user.updated_at

        # Update the user
        user.full_name = "Updated Name"
        db_session.commit()
        db_session.refresh(user)

        # updated_at should now be set and different from original
        assert user.updated_at is not None
        if original_updated_at is not None:
            assert user.updated_at > original_updated_at

    def test_user_is_active_default_true(self, db_session, workspace):
        """Test that is_active defaults to True"""
        user = User(
            email="active@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.is_active is True

    def test_user_is_active_can_be_set_false(self, db_session, workspace):
        """Test that is_active can be explicitly set to False"""
        user = User(
            email="inactive@example.com",
            workspace_id=workspace.id,
            is_active=False
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.is_active is False


class TestUserEmailConstraints:
    """Test email uniqueness and constraints"""

    def test_email_unique_constraint(self, db_session, workspace):
        """Test that email must be unique"""
        user1 = User(
            email="unique@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user1)
        db_session.commit()

        # Try to create another user with same email
        user2 = User(
            email="unique@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_email_not_null_constraint(self, db_session, workspace):
        """Test that email cannot be null"""
        user = User(
            workspace_id=workspace.id
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_email_index_exists(self, db_engine):
        """Test that email column has an index"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        indexes = inspector.get_indexes("users")

        # Find index on email column
        email_indexed = any(
            "email" in idx.get("column_names", [])
            for idx in indexes
        )
        assert email_indexed, "Email column should have an index"


class TestWorkspaceForeignKey:
    """Test workspace_id foreign key constraint"""

    def test_workspace_foreign_key_valid(self, db_session, workspace):
        """Test that valid workspace_id is accepted"""
        user = User(
            email="fk_valid@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.workspace_id == workspace.id

    def test_workspace_foreign_key_invalid(self, db_session):
        """Test that invalid workspace_id is rejected"""
        invalid_workspace_id = uuid4()
        user = User(
            email="fk_invalid@example.com",
            workspace_id=invalid_workspace_id
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_workspace_id_not_null(self, db_session):
        """Test that workspace_id cannot be null"""
        user = User(
            email="no_workspace@example.com"
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()


class TestCascadeDelete:
    """Test cascade delete when workspace is deleted"""

    @pytest.mark.skip(reason="Requires agent_swarm_instances table which has PostgreSQL-specific ARRAY types")
    def test_cascade_delete_users_when_workspace_deleted(self, db_session, workspace):
        """Test that users are deleted when workspace is deleted"""
        # NOTE: This test is skipped because deleting workspace cascades to conversations,
        # which reference agent_swarm_instances table that has PostgreSQL ARRAY types
        # that cannot be created in SQLite

        # Create multiple users in workspace
        user1 = User(
            email="cascade1@example.com",
            workspace_id=workspace.id
        )
        user2 = User(
            email="cascade2@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user1)
        db_session.add(user2)
        db_session.commit()

        user1_id = user1.id
        user2_id = user2.id

        # Delete workspace
        db_session.delete(workspace)
        db_session.commit()

        # Verify users are deleted
        assert db_session.query(User).filter(User.id == user1_id).first() is None
        assert db_session.query(User).filter(User.id == user2_id).first() is None


class TestUserRelationships:
    """Test user relationships with workspace, agents, and conversations"""

    def test_workspace_relationship(self, db_session, workspace):
        """Test that user has workspace relationship"""
        user = User(
            email="relationship@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Access workspace relationship
        assert user.workspace is not None
        assert user.workspace.id == workspace.id
        assert user.workspace.name == workspace.name

    def test_workspace_users_backref(self, db_session, workspace):
        """Test that workspace has users back-reference"""
        user1 = User(
            email="backref1@example.com",
            workspace_id=workspace.id
        )
        user2 = User(
            email="backref2@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user1)
        db_session.add(user2)
        db_session.commit()
        db_session.refresh(workspace)

        # Access users through workspace
        assert len(workspace.users) == 2
        emails = {u.email for u in workspace.users}
        assert "backref1@example.com" in emails
        assert "backref2@example.com" in emails

    # NOTE: Agents and Conversations relationship tests skipped
    # AgentSwarmInstance and Conversation tables have PostgreSQL-specific ARRAY types
    # that cannot be created in SQLite test database


class TestUserActiveStatus:
    """Test user is_active status filtering"""

    def test_query_active_users(self, db_session, workspace):
        """Test querying only active users"""
        active_user = User(
            email="active1@example.com",
            workspace_id=workspace.id,
            is_active=True
        )
        inactive_user = User(
            email="inactive1@example.com",
            workspace_id=workspace.id,
            is_active=False
        )
        db_session.add(active_user)
        db_session.add(inactive_user)
        db_session.commit()

        # Query only active users
        active_users = db_session.query(User).filter(User.is_active == True).all()
        assert len(active_users) == 1
        assert active_users[0].email == "active1@example.com"

    def test_deactivate_user(self, db_session, workspace):
        """Test deactivating a user"""
        user = User(
            email="deactivate@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.is_active is True

        # Deactivate user
        user.is_active = False
        db_session.commit()
        db_session.refresh(user)

        assert user.is_active is False


class TestUserQuery:
    """Test user query operations"""

    def test_query_user_by_email(self, db_session, workspace):
        """Test querying user by email"""
        user = User(
            email="query@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user)
        db_session.commit()

        # Query by email
        found_user = db_session.query(User).filter(User.email == "query@example.com").first()
        assert found_user is not None
        assert found_user.id == user.id

    def test_query_user_by_full_name(self, db_session, workspace):
        """Test querying user by full_name"""
        user = User(
            email="namequery@example.com",
            full_name="Jane Smith",
            workspace_id=workspace.id
        )
        db_session.add(user)
        db_session.commit()

        # Query by full_name
        found_user = db_session.query(User).filter(User.full_name == "Jane Smith").first()
        assert found_user is not None
        assert found_user.email == "namequery@example.com"

    def test_query_users_by_workspace(self, db_session, workspace):
        """Test querying all users in a workspace"""
        user1 = User(
            email="ws_query1@example.com",
            workspace_id=workspace.id
        )
        user2 = User(
            email="ws_query2@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user1)
        db_session.add(user2)
        db_session.commit()

        # Query users by workspace
        users = db_session.query(User).filter(User.workspace_id == workspace.id).all()
        assert len(users) == 2
        emails = {u.email for u in users}
        assert "ws_query1@example.com" in emails
        assert "ws_query2@example.com" in emails


class TestUserRepr:
    """Test user string representation"""

    def test_user_repr(self, db_session, workspace):
        """Test that user has a meaningful string representation"""
        user = User(
            email="repr@example.com",
            workspace_id=workspace.id
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        repr_str = repr(user)
        assert "User" in repr_str
        assert "repr@example.com" in repr_str
