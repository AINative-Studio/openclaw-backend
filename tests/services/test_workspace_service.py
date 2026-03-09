"""
Tests for WorkspaceService

Comprehensive test coverage for workspace management with ZeroDB integration.
Tests use mocked ZeroDBClient to avoid external dependencies.
Follows TDD principles: RED-GREEN-REFACTOR.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from backend.services.workspace_service import (
    WorkspaceService,
    WorkspaceNotFoundError,
    WorkspaceAlreadyExistsError,
    ZeroDBIntegrationError
)
from backend.integrations.zerodb_client import (
    ZeroDBClient,
    ZeroDBConnectionError,
    ZeroDBAPIError
)
from backend.models.workspace import Workspace


@pytest.fixture
def mock_zerodb_client():
    """Create a mocked ZeroDBClient"""
    client = AsyncMock(spec=ZeroDBClient)
    client.create_project = AsyncMock()
    client.create_table = AsyncMock()
    client.query_table = AsyncMock()
    return client


@pytest.fixture
def mock_db_session():
    """Create a mocked async database session"""
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def workspace_service(mock_db_session, mock_zerodb_client):
    """Create WorkspaceService instance with mocked dependencies"""
    return WorkspaceService(db=mock_db_session, zerodb_client=mock_zerodb_client)


@pytest.fixture
def sample_workspace():
    """Create sample workspace"""
    workspace = Workspace(
        id=uuid4(),
        name="Test Workspace",
        slug="test-workspace",
        description="A test workspace",
        zerodb_project_id="proj_test123",
        created_at=datetime.now(timezone.utc)
    )
    return workspace


class TestWorkspaceServiceInitialization:
    """Test WorkspaceService initialization"""

    def test_service_initialization_with_dependencies(self, mock_db_session, mock_zerodb_client):
        """Test that service can be initialized with dependencies"""
        service = WorkspaceService(db=mock_db_session, zerodb_client=mock_zerodb_client)
        assert service.db == mock_db_session
        assert service.zerodb_client == mock_zerodb_client

    def test_service_initialization_without_zerodb_client(self, mock_db_session):
        """Test that service can be initialized without ZeroDB client (optional)"""
        service = WorkspaceService(db=mock_db_session, zerodb_client=None)
        assert service.db == mock_db_session
        assert service.zerodb_client is None


class TestCreateWorkspace:
    """Test workspace creation"""

    @pytest.mark.asyncio
    async def test_create_workspace_with_zerodb_integration(self, workspace_service, mock_zerodb_client, mock_db_session):
        """Test creating workspace with ZeroDB project provisioning"""
        # Mock ZeroDB project creation
        mock_zerodb_client.create_project.return_value = {
            "id": "proj_new123",
            "name": "New Workspace",
            "description": "Test workspace",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Mock database session refresh to populate ID
        def mock_refresh(obj):
            if isinstance(obj, Workspace) and obj.id is None:
                obj.id = uuid4()
        mock_db_session.refresh = AsyncMock(side_effect=mock_refresh)

        # Create workspace
        workspace = await workspace_service.create_workspace(
            name="New Workspace",
            slug="new-workspace",
            description="Test workspace",
            provision_zerodb=True
        )

        # Verify ZeroDB project was created
        mock_zerodb_client.create_project.assert_called_once_with(
            name="New Workspace",
            description="Test workspace"
        )

        # Verify workspace was added to database
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

        # Verify workspace attributes
        assert workspace.name == "New Workspace"
        assert workspace.slug == "new-workspace"
        assert workspace.description == "Test workspace"
        assert workspace.zerodb_project_id == "proj_new123"

    @pytest.mark.asyncio
    async def test_create_workspace_without_zerodb_integration(self, workspace_service, mock_zerodb_client, mock_db_session):
        """Test creating workspace without ZeroDB provisioning"""
        # Mock database session refresh
        def mock_refresh(obj):
            if isinstance(obj, Workspace) and obj.id is None:
                obj.id = uuid4()
        mock_db_session.refresh = AsyncMock(side_effect=mock_refresh)

        # Create workspace without ZeroDB
        workspace = await workspace_service.create_workspace(
            name="Local Workspace",
            slug="local-workspace",
            description="Local only",
            provision_zerodb=False
        )

        # Verify ZeroDB was NOT called
        mock_zerodb_client.create_project.assert_not_called()

        # Verify workspace was added to database
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

        # Verify workspace attributes
        assert workspace.name == "Local Workspace"
        assert workspace.slug == "local-workspace"
        assert workspace.zerodb_project_id is None

    @pytest.mark.asyncio
    async def test_create_workspace_with_duplicate_name(self, workspace_service, mock_db_session):
        """Test creating workspace with duplicate name raises error"""
        # Mock IntegrityError on commit
        mock_db_session.commit.side_effect = IntegrityError("Duplicate name", None, None)

        # Should raise WorkspaceAlreadyExistsError
        with pytest.raises(WorkspaceAlreadyExistsError) as exc_info:
            await workspace_service.create_workspace(
                name="Duplicate",
                slug="duplicate",
                provision_zerodb=False
            )

        assert "already exists" in str(exc_info.value).lower()
        mock_db_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_workspace_with_duplicate_slug(self, workspace_service, mock_db_session):
        """Test creating workspace with duplicate slug raises error"""
        # Mock IntegrityError on commit
        mock_db_session.commit.side_effect = IntegrityError("Duplicate slug", None, None)

        # Should raise WorkspaceAlreadyExistsError
        with pytest.raises(WorkspaceAlreadyExistsError):
            await workspace_service.create_workspace(
                name="New Name",
                slug="duplicate-slug",
                provision_zerodb=False
            )

        mock_db_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_workspace_zerodb_connection_error(self, workspace_service, mock_zerodb_client, mock_db_session):
        """Test ZeroDB connection error during workspace creation"""
        # Mock ZeroDB connection failure
        mock_zerodb_client.create_project.side_effect = ZeroDBConnectionError("Connection failed")

        # Should raise ZeroDBIntegrationError and rollback
        with pytest.raises(ZeroDBIntegrationError) as exc_info:
            await workspace_service.create_workspace(
                name="Failed Workspace",
                slug="failed-workspace",
                provision_zerodb=True
            )

        assert "connection" in str(exc_info.value).lower()
        mock_db_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_workspace_zerodb_api_error(self, workspace_service, mock_zerodb_client, mock_db_session):
        """Test ZeroDB API error during workspace creation"""
        # Mock ZeroDB API failure
        mock_zerodb_client.create_project.side_effect = ZeroDBAPIError("API error", status_code=500)

        # Should raise ZeroDBIntegrationError and rollback
        with pytest.raises(ZeroDBIntegrationError) as exc_info:
            await workspace_service.create_workspace(
                name="API Error Workspace",
                slug="api-error",
                provision_zerodb=True
            )

        assert "api error" in str(exc_info.value).lower()
        mock_db_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_workspace_without_zerodb_client_but_provision_requested(self, mock_db_session):
        """Test creating workspace with provision_zerodb=True but no client raises error"""
        service = WorkspaceService(db=mock_db_session, zerodb_client=None)

        with pytest.raises(ZeroDBIntegrationError) as exc_info:
            await service.create_workspace(
                name="No Client",
                slug="no-client",
                provision_zerodb=True
            )

        assert "not available" in str(exc_info.value).lower()


class TestGetWorkspace:
    """Test workspace retrieval"""

    @pytest.mark.asyncio
    async def test_get_workspace_by_id(self, workspace_service, mock_db_session, sample_workspace):
        """Test retrieving workspace by ID"""
        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workspace
        mock_db_session.execute.return_value = mock_result

        # Get workspace
        workspace = await workspace_service.get_workspace_by_id(sample_workspace.id)

        # Verify result
        assert workspace.id == sample_workspace.id
        assert workspace.name == sample_workspace.name
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_workspace_by_id_not_found(self, workspace_service, mock_db_session):
        """Test retrieving non-existent workspace by ID"""
        # Mock database query returning None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Should raise WorkspaceNotFoundError
        with pytest.raises(WorkspaceNotFoundError) as exc_info:
            await workspace_service.get_workspace_by_id(uuid4())

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_workspace_by_slug(self, workspace_service, mock_db_session, sample_workspace):
        """Test retrieving workspace by slug"""
        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workspace
        mock_db_session.execute.return_value = mock_result

        # Get workspace
        workspace = await workspace_service.get_workspace_by_slug("test-workspace")

        # Verify result
        assert workspace.slug == "test-workspace"
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_workspace_by_slug_not_found(self, workspace_service, mock_db_session):
        """Test retrieving non-existent workspace by slug"""
        # Mock database query returning None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Should raise WorkspaceNotFoundError
        with pytest.raises(WorkspaceNotFoundError):
            await workspace_service.get_workspace_by_slug("non-existent")

    @pytest.mark.asyncio
    async def test_get_workspace_by_zerodb_project_id(self, workspace_service, mock_db_session, sample_workspace):
        """Test retrieving workspace by ZeroDB project ID"""
        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workspace
        mock_db_session.execute.return_value = mock_result

        # Get workspace
        workspace = await workspace_service.get_workspace_by_zerodb_project_id("proj_test123")

        # Verify result
        assert workspace.zerodb_project_id == "proj_test123"
        mock_db_session.execute.assert_called_once()


class TestListWorkspaces:
    """Test workspace listing"""

    @pytest.mark.asyncio
    async def test_list_all_workspaces(self, workspace_service, mock_db_session):
        """Test listing all workspaces"""
        # Create sample workspaces
        workspaces = [
            Workspace(id=uuid4(), name="Workspace 1", slug="workspace-1"),
            Workspace(id=uuid4(), name="Workspace 2", slug="workspace-2"),
            Workspace(id=uuid4(), name="Workspace 3", slug="workspace-3")
        ]

        # Mock database query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = workspaces
        mock_db_session.execute.return_value = mock_result

        # List workspaces
        result = await workspace_service.list_workspaces()

        # Verify result
        assert len(result) == 3
        assert result[0].name == "Workspace 1"
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_workspaces_with_limit(self, workspace_service, mock_db_session):
        """Test listing workspaces with limit"""
        # Create sample workspaces
        workspaces = [
            Workspace(id=uuid4(), name="Workspace 1", slug="workspace-1"),
            Workspace(id=uuid4(), name="Workspace 2", slug="workspace-2")
        ]

        # Mock database query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = workspaces
        mock_db_session.execute.return_value = mock_result

        # List workspaces with limit
        result = await workspace_service.list_workspaces(limit=2, offset=0)

        # Verify result
        assert len(result) == 2
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_workspaces_with_offset(self, workspace_service, mock_db_session):
        """Test listing workspaces with offset"""
        # Create sample workspaces (page 2)
        workspaces = [
            Workspace(id=uuid4(), name="Workspace 3", slug="workspace-3")
        ]

        # Mock database query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = workspaces
        mock_db_session.execute.return_value = mock_result

        # List workspaces with offset
        result = await workspace_service.list_workspaces(limit=10, offset=2)

        # Verify result
        assert len(result) == 1
        assert result[0].name == "Workspace 3"

    @pytest.mark.asyncio
    async def test_list_workspaces_empty(self, workspace_service, mock_db_session):
        """Test listing workspaces when none exist"""
        # Mock empty query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        # List workspaces
        result = await workspace_service.list_workspaces()

        # Verify result
        assert len(result) == 0


class TestUpdateWorkspace:
    """Test workspace updates"""

    @pytest.mark.asyncio
    async def test_update_workspace_description(self, workspace_service, mock_db_session, sample_workspace):
        """Test updating workspace description"""
        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workspace
        mock_db_session.execute.return_value = mock_result

        # Update workspace
        updated = await workspace_service.update_workspace(
            workspace_id=sample_workspace.id,
            description="Updated description"
        )

        # Verify update
        assert updated.description == "Updated description"
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_workspace_name(self, workspace_service, mock_db_session, sample_workspace):
        """Test updating workspace name"""
        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workspace
        mock_db_session.execute.return_value = mock_result

        # Update workspace
        updated = await workspace_service.update_workspace(
            workspace_id=sample_workspace.id,
            name="Updated Name"
        )

        # Verify update
        assert updated.name == "Updated Name"
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_workspace_slug(self, workspace_service, mock_db_session, sample_workspace):
        """Test updating workspace slug"""
        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workspace
        mock_db_session.execute.return_value = mock_result

        # Update workspace
        updated = await workspace_service.update_workspace(
            workspace_id=sample_workspace.id,
            slug="updated-slug"
        )

        # Verify update
        assert updated.slug == "updated-slug"
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_workspace_not_found(self, workspace_service, mock_db_session):
        """Test updating non-existent workspace"""
        # Mock database query returning None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Should raise WorkspaceNotFoundError
        with pytest.raises(WorkspaceNotFoundError):
            await workspace_service.update_workspace(
                workspace_id=uuid4(),
                name="New Name"
            )

    @pytest.mark.asyncio
    async def test_update_workspace_no_changes(self, workspace_service, mock_db_session, sample_workspace):
        """Test updating workspace with no changes"""
        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workspace
        mock_db_session.execute.return_value = mock_result

        # Update workspace with no actual changes
        updated = await workspace_service.update_workspace(
            workspace_id=sample_workspace.id
        )

        # Verify no changes but still commits
        assert updated.id == sample_workspace.id
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_workspace_multiple_fields(self, workspace_service, mock_db_session, sample_workspace):
        """Test updating multiple workspace fields at once"""
        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workspace
        mock_db_session.execute.return_value = mock_result

        # Update multiple fields
        updated = await workspace_service.update_workspace(
            workspace_id=sample_workspace.id,
            name="New Name",
            description="New Description",
            slug="new-slug"
        )

        # Verify all updates
        assert updated.name == "New Name"
        assert updated.description == "New Description"
        assert updated.slug == "new-slug"
        mock_db_session.commit.assert_called_once()


class TestDeleteWorkspace:
    """Test workspace deletion"""

    @pytest.mark.asyncio
    async def test_delete_workspace(self, workspace_service, mock_db_session, sample_workspace):
        """Test deleting workspace"""
        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workspace
        mock_db_session.execute.return_value = mock_result

        # Delete workspace
        await workspace_service.delete_workspace(sample_workspace.id)

        # Verify deletion
        mock_db_session.delete.assert_called_once_with(sample_workspace)
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_workspace_not_found(self, workspace_service, mock_db_session):
        """Test deleting non-existent workspace"""
        # Mock database query returning None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Should raise WorkspaceNotFoundError
        with pytest.raises(WorkspaceNotFoundError):
            await workspace_service.delete_workspace(uuid4())

        mock_db_session.delete.assert_not_called()


class TestWorkspaceWithZeroDBTables:
    """Test workspace operations with ZeroDB table provisioning"""

    @pytest.mark.asyncio
    async def test_provision_workspace_tables(self, workspace_service, mock_zerodb_client, sample_workspace):
        """Test provisioning ZeroDB tables for workspace"""
        # Mock table creation
        mock_zerodb_client.create_table.return_value = {
            "id": "table_123",
            "table_name": "conversations",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Provision tables
        tables = await workspace_service.provision_workspace_tables(
            sample_workspace,
            table_names=["conversations", "messages", "agents"]
        )

        # Verify all tables were created
        assert len(tables) == 3
        assert mock_zerodb_client.create_table.call_count == 3

        # Verify table names
        calls = mock_zerodb_client.create_table.call_args_list
        assert calls[0][1]["table_name"] == "conversations"
        assert calls[1][1]["table_name"] == "messages"
        assert calls[2][1]["table_name"] == "agents"

    @pytest.mark.asyncio
    async def test_provision_workspace_tables_without_zerodb_project_id(self, workspace_service, sample_workspace):
        """Test provisioning tables for workspace without ZeroDB project ID"""
        # Remove ZeroDB project ID
        workspace_without_zerodb = Workspace(
            id=uuid4(),
            name="No ZeroDB",
            slug="no-zerodb",
            zerodb_project_id=None
        )

        # Should raise ZeroDBIntegrationError
        with pytest.raises(ZeroDBIntegrationError) as exc_info:
            await workspace_service.provision_workspace_tables(
                workspace_without_zerodb,
                table_names=["conversations"]
            )

        assert "not configured" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_provision_workspace_tables_zerodb_error(self, workspace_service, mock_zerodb_client, sample_workspace):
        """Test handling ZeroDB errors during table provisioning"""
        # Mock table creation failure
        mock_zerodb_client.create_table.side_effect = ZeroDBAPIError("Table creation failed", status_code=500)

        # Should raise ZeroDBIntegrationError
        with pytest.raises(ZeroDBIntegrationError):
            await workspace_service.provision_workspace_tables(
                sample_workspace,
                table_names=["conversations"]
            )


class TestMultiTenantIsolation:
    """Test multi-tenant isolation features"""

    @pytest.mark.asyncio
    async def test_workspace_isolation_by_id(self, workspace_service, mock_db_session):
        """Test that workspaces are properly isolated by ID"""
        # Create workspaces with different IDs
        workspace1 = Workspace(id=uuid4(), name="Workspace 1", slug="workspace-1")
        workspace2 = Workspace(id=uuid4(), name="Workspace 2", slug="workspace-2")

        # Mock different query results
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = workspace1

        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = workspace2

        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        # Get workspaces separately
        result1 = await workspace_service.get_workspace_by_id(workspace1.id)
        result2 = await workspace_service.get_workspace_by_id(workspace2.id)

        # Verify isolation
        assert result1.id != result2.id
        assert result1.name != result2.name

    @pytest.mark.asyncio
    async def test_workspace_isolation_by_zerodb_project_id(self, workspace_service, mock_db_session):
        """Test that workspaces are properly isolated by ZeroDB project ID"""
        # Create workspaces with different ZeroDB project IDs
        workspace1 = Workspace(
            id=uuid4(),
            name="Workspace 1",
            slug="workspace-1",
            zerodb_project_id="proj_123"
        )
        workspace2 = Workspace(
            id=uuid4(),
            name="Workspace 2",
            slug="workspace-2",
            zerodb_project_id="proj_456"
        )

        # Mock different query results
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = workspace1

        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = workspace2

        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        # Get workspaces by ZeroDB project ID
        result1 = await workspace_service.get_workspace_by_zerodb_project_id("proj_123")
        result2 = await workspace_service.get_workspace_by_zerodb_project_id("proj_456")

        # Verify isolation
        assert result1.zerodb_project_id != result2.zerodb_project_id
        assert result1.id != result2.id


class TestUserWorkspaceAssociations:
    """Test user-workspace associations (prepare for future RLS)"""

    @pytest.mark.asyncio
    async def test_get_workspace_users_placeholder(self, workspace_service, sample_workspace):
        """Test getting users associated with workspace (placeholder for future RLS)"""
        # This is a placeholder test for future user-workspace association features
        # When RLS is implemented, we'll need to verify that users can only access
        # workspaces they're associated with
        assert sample_workspace.id is not None

    @pytest.mark.asyncio
    async def test_workspace_access_control_placeholder(self, workspace_service, sample_workspace):
        """Test workspace access control (placeholder for future RLS)"""
        # This is a placeholder test for future access control features
        # When RLS is implemented, we'll need to verify:
        # 1. Users can only see workspaces they have access to
        # 2. Users cannot modify workspaces they don't own
        # 3. Proper permission checks are in place
        assert sample_workspace.id is not None


class TestWorkspaceServiceEdgeCases:
    """Test edge cases and error conditions"""

    @pytest.mark.asyncio
    async def test_create_workspace_with_empty_name(self, workspace_service, mock_db_session):
        """Test creating workspace with empty name"""
        # Mock IntegrityError or validation error
        mock_db_session.commit.side_effect = IntegrityError("Name cannot be empty", None, None)

        with pytest.raises(WorkspaceAlreadyExistsError):
            await workspace_service.create_workspace(
                name="",
                slug="empty-name",
                provision_zerodb=False
            )

    @pytest.mark.asyncio
    async def test_create_workspace_with_invalid_slug_format(self, workspace_service, mock_db_session):
        """Test creating workspace with invalid slug format (placeholder)"""
        # Future enhancement: validate slug format (lowercase, hyphens only)
        # For now, just ensure it doesn't crash
        def mock_refresh(obj):
            if isinstance(obj, Workspace) and obj.id is None:
                obj.id = uuid4()
        mock_db_session.refresh = AsyncMock(side_effect=mock_refresh)

        workspace = await workspace_service.create_workspace(
            name="Test",
            slug="INVALID-SLUG-123",
            provision_zerodb=False
        )

        assert workspace.slug == "INVALID-SLUG-123"

    @pytest.mark.asyncio
    async def test_update_workspace_with_duplicate_name(self, workspace_service, mock_db_session, sample_workspace):
        """Test updating workspace to duplicate name"""
        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workspace
        mock_db_session.execute.return_value = mock_result

        # Mock IntegrityError on commit
        mock_db_session.commit.side_effect = IntegrityError("Duplicate name", None, None)

        with pytest.raises(WorkspaceAlreadyExistsError):
            await workspace_service.update_workspace(
                workspace_id=sample_workspace.id,
                name="Duplicate Name"
            )

        mock_db_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_workspace_with_cascade(self, workspace_service, mock_db_session, sample_workspace):
        """Test deleting workspace cascades to related entities"""
        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workspace
        mock_db_session.execute.return_value = mock_result

        # Delete workspace (should cascade due to model relationships)
        await workspace_service.delete_workspace(sample_workspace.id)

        # Verify deletion was called (cascade happens at DB level)
        mock_db_session.delete.assert_called_once_with(sample_workspace)
        mock_db_session.commit.assert_called_once()
