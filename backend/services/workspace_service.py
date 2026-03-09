"""
WorkspaceService - Multi-tenant workspace management with ZeroDB integration

This service provides CRUD operations for workspaces with optional ZeroDB project
provisioning for chat persistence. Implements multi-tenant isolation patterns and
prepares for future Row-Level Security (RLS).

Usage:
    async with ZeroDBClient() as zerodb_client:
        service = WorkspaceService(db=session, zerodb_client=zerodb_client)

        # Create workspace with ZeroDB provisioning
        workspace = await service.create_workspace(
            name="My Workspace",
            slug="my-workspace",
            provision_zerodb=True
        )

        # List workspaces with pagination
        workspaces = await service.list_workspaces(limit=10, offset=0)
"""

from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.models.workspace import Workspace
from backend.integrations.zerodb_client import (
    ZeroDBClient,
    ZeroDBConnectionError,
    ZeroDBAPIError
)


class WorkspaceNotFoundError(Exception):
    """
    Raised when a workspace is not found in the database.

    This error indicates that the requested workspace does not exist,
    either by ID, slug, or ZeroDB project ID.
    """

    def __init__(self, message: str):
        """
        Initialize WorkspaceNotFoundError.

        Args:
            message: Error description
        """
        super().__init__(message)


class WorkspaceAlreadyExistsError(Exception):
    """
    Raised when attempting to create a workspace with duplicate name or slug.

    This error indicates a unique constraint violation during workspace creation
    or update operations.
    """

    def __init__(self, message: str):
        """
        Initialize WorkspaceAlreadyExistsError.

        Args:
            message: Error description
        """
        super().__init__(message)


class ZeroDBIntegrationError(Exception):
    """
    Raised when ZeroDB integration fails during workspace operations.

    This includes connection errors, API errors, and configuration issues.
    """

    def __init__(self, message: str):
        """
        Initialize ZeroDBIntegrationError.

        Args:
            message: Error description
        """
        super().__init__(message)


class WorkspaceService:
    """
    Service for managing workspaces with ZeroDB integration.

    Provides CRUD operations for workspaces, ZeroDB project provisioning,
    and multi-tenant isolation. All methods are async for compatibility
    with FastAPI endpoints.

    Attributes:
        db: Async SQLAlchemy session for database operations
        zerodb_client: Optional ZeroDB client for project provisioning
    """

    def __init__(
        self,
        db: AsyncSession,
        zerodb_client: Optional[ZeroDBClient] = None
    ):
        """
        Initialize WorkspaceService.

        Args:
            db: Async SQLAlchemy session
            zerodb_client: Optional ZeroDB client for project provisioning
        """
        self.db = db
        self.zerodb_client = zerodb_client

    async def create_workspace(
        self,
        name: str,
        slug: str,
        description: Optional[str] = None,
        provision_zerodb: bool = False
    ) -> Workspace:
        """
        Create a new workspace with optional ZeroDB project provisioning.

        If provision_zerodb is True, creates a ZeroDB project and links it
        to the workspace for chat persistence.

        Args:
            name: Workspace name (must be unique)
            slug: Workspace slug (must be unique, URL-safe)
            description: Optional workspace description
            provision_zerodb: Whether to provision ZeroDB project

        Returns:
            Created Workspace instance with ID and timestamps

        Raises:
            WorkspaceAlreadyExistsError: If name or slug already exists
            ZeroDBIntegrationError: If ZeroDB provisioning fails

        Example:
            workspace = await service.create_workspace(
                name="AcmeCorp",
                slug="acmecorp",
                description="Acme Corporation workspace",
                provision_zerodb=True
            )
        """
        zerodb_project_id = None

        # Provision ZeroDB project if requested
        if provision_zerodb:
            if not self.zerodb_client:
                raise ZeroDBIntegrationError(
                    "ZeroDB client not available. Cannot provision ZeroDB project."
                )

            try:
                # Create ZeroDB project
                project = await self.zerodb_client.create_project(
                    name=name,
                    description=description or f"ZeroDB project for {name}"
                )
                zerodb_project_id = project.get("id")
            except ZeroDBConnectionError as e:
                await self.db.rollback()
                raise ZeroDBIntegrationError(
                    f"ZeroDB connection error: {str(e)}"
                )
            except ZeroDBAPIError as e:
                await self.db.rollback()
                raise ZeroDBIntegrationError(
                    f"ZeroDB API error: {str(e)}"
                )

        # Create workspace in database
        workspace = Workspace(
            name=name,
            slug=slug,
            description=description,
            zerodb_project_id=zerodb_project_id
        )

        try:
            self.db.add(workspace)
            await self.db.commit()
            await self.db.refresh(workspace)
            return workspace
        except IntegrityError as e:
            await self.db.rollback()
            raise WorkspaceAlreadyExistsError(
                f"Workspace with name '{name}' or slug '{slug}' already exists"
            )

    async def get_workspace_by_id(self, workspace_id: UUID) -> Workspace:
        """
        Retrieve workspace by ID.

        Args:
            workspace_id: UUID of workspace

        Returns:
            Workspace instance

        Raises:
            WorkspaceNotFoundError: If workspace not found

        Example:
            workspace = await service.get_workspace_by_id(uuid4())
        """
        stmt = select(Workspace).where(Workspace.id == workspace_id)
        result = await self.db.execute(stmt)
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise WorkspaceNotFoundError(
                f"Workspace with ID {workspace_id} not found"
            )

        return workspace

    async def get_workspace_by_slug(self, slug: str) -> Workspace:
        """
        Retrieve workspace by slug.

        Args:
            slug: Workspace slug

        Returns:
            Workspace instance

        Raises:
            WorkspaceNotFoundError: If workspace not found

        Example:
            workspace = await service.get_workspace_by_slug("acmecorp")
        """
        stmt = select(Workspace).where(Workspace.slug == slug)
        result = await self.db.execute(stmt)
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise WorkspaceNotFoundError(
                f"Workspace with slug '{slug}' not found"
            )

        return workspace

    async def get_workspace_by_zerodb_project_id(
        self,
        zerodb_project_id: str
    ) -> Workspace:
        """
        Retrieve workspace by ZeroDB project ID.

        Args:
            zerodb_project_id: ZeroDB project ID

        Returns:
            Workspace instance

        Raises:
            WorkspaceNotFoundError: If workspace not found

        Example:
            workspace = await service.get_workspace_by_zerodb_project_id("proj_123")
        """
        stmt = select(Workspace).where(
            Workspace.zerodb_project_id == zerodb_project_id
        )
        result = await self.db.execute(stmt)
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise WorkspaceNotFoundError(
                f"Workspace with ZeroDB project ID '{zerodb_project_id}' not found"
            )

        return workspace

    async def list_workspaces(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> List[Workspace]:
        """
        List workspaces with pagination.

        Args:
            limit: Maximum number of workspaces to return (default: 100)
            offset: Number of workspaces to skip (default: 0)

        Returns:
            List of Workspace instances

        Example:
            # Get first page
            workspaces = await service.list_workspaces(limit=10, offset=0)

            # Get second page
            workspaces = await service.list_workspaces(limit=10, offset=10)
        """
        stmt = (
            select(Workspace)
            .order_by(Workspace.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        workspaces = result.scalars().all()
        return list(workspaces)

    async def update_workspace(
        self,
        workspace_id: UUID,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        description: Optional[str] = None
    ) -> Workspace:
        """
        Update workspace attributes.

        Only provided fields are updated. None values are ignored.

        Args:
            workspace_id: UUID of workspace to update
            name: New workspace name (optional)
            slug: New workspace slug (optional)
            description: New workspace description (optional)

        Returns:
            Updated Workspace instance

        Raises:
            WorkspaceNotFoundError: If workspace not found
            WorkspaceAlreadyExistsError: If updated name/slug conflicts

        Example:
            workspace = await service.update_workspace(
                workspace_id=uuid4(),
                name="New Name",
                description="Updated description"
            )
        """
        # Fetch workspace
        workspace = await self.get_workspace_by_id(workspace_id)

        # Update fields if provided
        if name is not None:
            workspace.name = name
        if slug is not None:
            workspace.slug = slug
        if description is not None:
            workspace.description = description

        # Commit changes
        try:
            await self.db.commit()
            await self.db.refresh(workspace)
            return workspace
        except IntegrityError as e:
            await self.db.rollback()
            raise WorkspaceAlreadyExistsError(
                f"Workspace with name '{name}' or slug '{slug}' already exists"
            )

    async def delete_workspace(self, workspace_id: UUID) -> None:
        """
        Delete workspace by ID.

        Cascades to related users, agents, and conversations based on
        model relationships defined in Workspace model.

        Args:
            workspace_id: UUID of workspace to delete

        Raises:
            WorkspaceNotFoundError: If workspace not found

        Example:
            await service.delete_workspace(uuid4())
        """
        # Fetch workspace
        workspace = await self.get_workspace_by_id(workspace_id)

        # Delete workspace (cascade happens at DB level)
        await self.db.delete(workspace)
        await self.db.commit()

    async def provision_workspace_tables(
        self,
        workspace: Workspace,
        table_names: List[str]
    ) -> List[dict]:
        """
        Provision ZeroDB tables for workspace.

        Creates specified tables in the workspace's ZeroDB project.
        Useful for setting up chat persistence infrastructure.

        Args:
            workspace: Workspace instance with zerodb_project_id
            table_names: List of table names to create

        Returns:
            List of created table metadata dicts

        Raises:
            ZeroDBIntegrationError: If ZeroDB provisioning fails

        Example:
            tables = await service.provision_workspace_tables(
                workspace=workspace,
                table_names=["conversations", "messages", "agents"]
            )
        """
        if not workspace.zerodb_project_id:
            raise ZeroDBIntegrationError(
                f"Workspace '{workspace.name}' is not configured with ZeroDB project"
            )

        if not self.zerodb_client:
            raise ZeroDBIntegrationError(
                "ZeroDB client not available. Cannot provision tables."
            )

        created_tables = []

        try:
            for table_name in table_names:
                table = await self.zerodb_client.create_table(
                    project_id=workspace.zerodb_project_id,
                    table_name=table_name
                )
                created_tables.append(table)

            return created_tables
        except (ZeroDBConnectionError, ZeroDBAPIError) as e:
            raise ZeroDBIntegrationError(
                f"Failed to provision ZeroDB tables: {str(e)}"
            )
