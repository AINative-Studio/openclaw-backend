"""
Test Workspace Model

Tests workspace creation, unique constraints, ZeroDB integration,
timestamps, and relationships following TDD principles.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from backend.db.base_class import Base
from backend.models.workspace import Workspace


@pytest.fixture
def db_engine():
    """Create in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
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


class TestWorkspaceCreation:
    """Test workspace creation and basic attributes"""

    def test_create_workspace_with_required_fields_only(self, db_session):
        """Test creating a workspace with only required fields (name and slug)"""
        workspace = Workspace(
            name="Test Workspace",
            slug="test-workspace"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        assert workspace.id is not None
        assert workspace.name == "Test Workspace"
        assert workspace.slug == "test-workspace"
        assert workspace.created_at is not None
        assert isinstance(workspace.created_at, datetime)

    def test_create_workspace_with_all_fields(self, db_session):
        """Test creating a workspace with all fields including optional ones"""
        workspace = Workspace(
            name="Full Workspace",
            slug="full-workspace",
            description="A comprehensive workspace for testing",
            zerodb_project_id="zerodb_proj_12345"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        assert workspace.id is not None
        assert workspace.name == "Full Workspace"
        assert workspace.slug == "full-workspace"
        assert workspace.description == "A comprehensive workspace for testing"
        assert workspace.zerodb_project_id == "zerodb_proj_12345"
        assert workspace.created_at is not None
        assert workspace.updated_at is None  # Only set on update

    def test_workspace_id_is_uuid(self, db_session):
        """Test that workspace ID is generated as UUID"""
        workspace = Workspace(
            name="UUID Test",
            slug="uuid-test"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        assert workspace.id is not None
        assert len(str(workspace.id)) == 36  # UUID string format

    def test_workspace_created_at_auto_generated(self, db_session):
        """Test that created_at timestamp is auto-generated"""
        workspace = Workspace(
            name="Timestamp Test",
            slug="timestamp-test"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        assert workspace.created_at is not None
        now = datetime.now(timezone.utc)
        time_diff = (now - workspace.created_at.replace(tzinfo=timezone.utc)).total_seconds()
        assert time_diff < 60  # Should be within the last minute


class TestWorkspaceNameConstraints:
    """Test workspace name constraints"""

    def test_name_unique_constraint(self, db_session):
        """Test that workspace name must be unique"""
        workspace1 = Workspace(
            name="Unique Name",
            slug="unique-slug-1"
        )
        db_session.add(workspace1)
        db_session.commit()

        # Try to create another workspace with same name
        workspace2 = Workspace(
            name="Unique Name",
            slug="unique-slug-2"
        )
        db_session.add(workspace2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_name_not_null_constraint(self, db_session):
        """Test that name cannot be null"""
        workspace = Workspace(
            slug="no-name"
        )
        db_session.add(workspace)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_name_index_exists(self, db_engine):
        """Test that name column has an index"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        indexes = inspector.get_indexes("workspaces")

        # Find index on name column
        name_indexed = any(
            "name" in idx.get("column_names", [])
            for idx in indexes
        )
        assert name_indexed, "Name column should have an index"


class TestWorkspaceSlugConstraints:
    """Test workspace slug constraints"""

    def test_slug_unique_constraint(self, db_session):
        """Test that slug must be unique"""
        workspace1 = Workspace(
            name="Workspace 1",
            slug="same-slug"
        )
        db_session.add(workspace1)
        db_session.commit()

        # Try to create another workspace with same slug
        workspace2 = Workspace(
            name="Workspace 2",
            slug="same-slug"
        )
        db_session.add(workspace2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_slug_not_null_constraint(self, db_session):
        """Test that slug cannot be null"""
        workspace = Workspace(
            name="No Slug Workspace"
        )
        db_session.add(workspace)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_slug_index_exists(self, db_engine):
        """Test that slug column has an index and is unique"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        indexes = inspector.get_indexes("workspaces")

        # Find unique index on slug column
        slug_indexed = any(
            "slug" in idx.get("column_names", []) and idx.get("unique", False)
            for idx in indexes
        )
        assert slug_indexed, "Slug column should have a unique index"


class TestZeroDBProjectIdConstraints:
    """Test zerodb_project_id constraints and uniqueness"""

    def test_zerodb_project_id_optional(self, db_session):
        """Test that zerodb_project_id is optional (can be null)"""
        workspace = Workspace(
            name="No ZeroDB",
            slug="no-zerodb"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        assert workspace.zerodb_project_id is None

    def test_zerodb_project_id_unique_constraint(self, db_session):
        """Test that zerodb_project_id must be unique when set"""
        workspace1 = Workspace(
            name="Workspace 1",
            slug="workspace-1",
            zerodb_project_id="zerodb_same_id"
        )
        db_session.add(workspace1)
        db_session.commit()

        # Try to create another workspace with same zerodb_project_id
        workspace2 = Workspace(
            name="Workspace 2",
            slug="workspace-2",
            zerodb_project_id="zerodb_same_id"
        )
        db_session.add(workspace2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_zerodb_project_id_index_exists(self, db_engine):
        """Test that zerodb_project_id column has a unique index"""
        inspector = pytest.importorskip("sqlalchemy").inspect(db_engine)
        indexes = inspector.get_indexes("workspaces")

        # Find unique index on zerodb_project_id column
        zerodb_indexed = any(
            "zerodb_project_id" in idx.get("column_names", []) and idx.get("unique", False)
            for idx in indexes
        )
        assert zerodb_indexed, "ZeroDB project ID column should have a unique index"


class TestWorkspaceDescriptionField:
    """Test workspace description field"""

    def test_description_optional(self, db_session):
        """Test that description is optional (can be null)"""
        workspace = Workspace(
            name="No Description",
            slug="no-description"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        assert workspace.description is None

    def test_description_can_be_text(self, db_session):
        """Test that description can store long text"""
        long_description = "A" * 1000  # 1000 character description
        workspace = Workspace(
            name="Long Description",
            slug="long-description",
            description=long_description
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        assert workspace.description == long_description


class TestWorkspaceTimestamps:
    """Test workspace timestamp fields"""

    def test_created_at_set_on_creation(self, db_session):
        """Test that created_at is set when workspace is created"""
        workspace = Workspace(
            name="Created At Test",
            slug="created-at-test"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        assert workspace.created_at is not None
        assert isinstance(workspace.created_at, datetime)

    def test_updated_at_null_on_creation(self, db_session):
        """Test that updated_at is null on creation"""
        workspace = Workspace(
            name="Updated At Test",
            slug="updated-at-test"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        assert workspace.updated_at is None

    def test_updated_at_set_on_update(self, db_session):
        """Test that updated_at is set when workspace is updated"""
        import time

        workspace = Workspace(
            name="Update Test",
            slug="update-test"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        assert workspace.updated_at is None

        # Wait a moment to ensure updated_at will be different
        time.sleep(0.1)

        # Update workspace
        workspace.description = "Updated description"
        db_session.commit()
        db_session.refresh(workspace)

        assert workspace.updated_at is not None
        assert isinstance(workspace.updated_at, datetime)
        assert workspace.updated_at >= workspace.created_at


class TestWorkspaceRelationships:
    """Test workspace relationships with users, agents, and conversations"""

    def test_users_relationship_exists(self, db_session):
        """Test that workspace has users relationship"""
        workspace = Workspace(
            name="Relationship Test",
            slug="relationship-test"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        # Should have users relationship (empty list initially)
        assert hasattr(workspace, "users")
        assert isinstance(workspace.users, list)
        assert len(workspace.users) == 0

    def test_agents_relationship_placeholder(self, db_session):
        """Test that agents relationship will be added when needed"""
        workspace = Workspace(
            name="Agents Test",
            slug="agents-test"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        # Agents relationship is not yet implemented
        # This test is a placeholder for future implementation
        assert workspace.id is not None

    def test_conversations_relationship_placeholder(self, db_session):
        """Test that conversations relationship will be added when Conversation model exists"""
        workspace = Workspace(
            name="Conversations Test",
            slug="conversations-test"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        # Conversations relationship is not yet implemented
        # This test is a placeholder for future implementation
        assert workspace.id is not None


class TestWorkspaceQuery:
    """Test workspace query operations"""

    def test_query_workspace_by_name(self, db_session):
        """Test querying workspace by name"""
        workspace = Workspace(
            name="Query Test",
            slug="query-test"
        )
        db_session.add(workspace)
        db_session.commit()

        # Query by name
        found_workspace = db_session.query(Workspace).filter(
            Workspace.name == "Query Test"
        ).first()
        assert found_workspace is not None
        assert found_workspace.id == workspace.id

    def test_query_workspace_by_slug(self, db_session):
        """Test querying workspace by slug"""
        workspace = Workspace(
            name="Slug Query",
            slug="slug-query"
        )
        db_session.add(workspace)
        db_session.commit()

        # Query by slug
        found_workspace = db_session.query(Workspace).filter(
            Workspace.slug == "slug-query"
        ).first()
        assert found_workspace is not None
        assert found_workspace.id == workspace.id

    def test_query_workspace_by_zerodb_project_id(self, db_session):
        """Test querying workspace by zerodb_project_id"""
        workspace = Workspace(
            name="ZeroDB Query",
            slug="zerodb-query",
            zerodb_project_id="zerodb_query_123"
        )
        db_session.add(workspace)
        db_session.commit()

        # Query by zerodb_project_id
        found_workspace = db_session.query(Workspace).filter(
            Workspace.zerodb_project_id == "zerodb_query_123"
        ).first()
        assert found_workspace is not None
        assert found_workspace.id == workspace.id


class TestWorkspaceRepr:
    """Test workspace string representation"""

    def test_workspace_repr(self, db_session):
        """Test that workspace has a meaningful string representation"""
        workspace = Workspace(
            name="Repr Test",
            slug="repr-test"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        repr_str = repr(workspace)
        assert "Workspace" in repr_str
        assert "Repr Test" in repr_str
        assert "repr-test" in repr_str


class TestWorkspaceUpdate:
    """Test workspace update operations"""

    def test_update_workspace_description(self, db_session):
        """Test updating workspace description"""
        workspace = Workspace(
            name="Update Desc",
            slug="update-desc"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        # Update description
        workspace.description = "New description"
        db_session.commit()
        db_session.refresh(workspace)

        assert workspace.description == "New description"

    def test_update_workspace_zerodb_project_id(self, db_session):
        """Test updating workspace zerodb_project_id"""
        workspace = Workspace(
            name="Update ZeroDB",
            slug="update-zerodb"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        # Update zerodb_project_id
        workspace.zerodb_project_id = "zerodb_new_id"
        db_session.commit()
        db_session.refresh(workspace)

        assert workspace.zerodb_project_id == "zerodb_new_id"

    def test_update_workspace_name(self, db_session):
        """Test updating workspace name"""
        workspace = Workspace(
            name="Old Name",
            slug="old-name"
        )
        db_session.add(workspace)
        db_session.commit()
        db_session.refresh(workspace)

        # Update name
        workspace.name = "New Name"
        db_session.commit()
        db_session.refresh(workspace)

        assert workspace.name == "New Name"
        assert workspace.updated_at is not None


class TestWorkspaceDelete:
    """Test workspace deletion"""

    def test_delete_workspace(self, db_session):
        """Test deleting a workspace"""
        workspace = Workspace(
            name="Delete Test",
            slug="delete-test"
        )
        db_session.add(workspace)
        db_session.commit()
        workspace_id = workspace.id

        # Delete workspace
        db_session.delete(workspace)
        db_session.commit()

        # Verify deletion
        found_workspace = db_session.query(Workspace).filter(
            Workspace.id == workspace_id
        ).first()
        assert found_workspace is None
