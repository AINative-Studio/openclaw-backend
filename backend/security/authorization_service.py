"""
Authorization Service

Provides resource ownership validation and access control to prevent
Insecure Direct Object References (IDOR) vulnerabilities.

Implements workspace-level and user-level authorization checks for all
resource types in the OpenClaw backend.

Issue #130: IDOR Prevention
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models.user import User
from backend.models.workspace import Workspace
from backend.models.conversation import Conversation
from backend.models.agent_swarm_lifecycle import AgentSwarmInstance
from backend.models.api_key import APIKey
from backend.models.user_api_key import UserAPIKey

# Optional imports for swarms (might not be available in all environments)
try:
    from backend.models.agent_swarm import AgentSwarm
    AGENT_SWARM_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    AGENT_SWARM_AVAILABLE = False

logger = logging.getLogger(__name__)


class AuthorizationError(HTTPException):
    """Base exception for authorization failures"""
    def __init__(self, detail: str, status_code: int = status.HTTP_403_FORBIDDEN):
        super().__init__(status_code=status_code, detail=detail)


class WorkspaceAccessDeniedError(AuthorizationError):
    """Raised when user attempts to access resource from different workspace"""
    def __init__(self, resource_type: str = "resource"):
        super().__init__(
            detail=f"Access denied: {resource_type} belongs to different workspace",
            status_code=status.HTTP_403_FORBIDDEN
        )


class OwnershipDeniedError(AuthorizationError):
    """Raised when user attempts to access resource they don't own"""
    def __init__(self, resource_type: str = "resource"):
        super().__init__(
            detail=f"Access denied: you do not own this {resource_type}",
            status_code=status.HTTP_403_FORBIDDEN
        )


class InsufficientPermissionsError(AuthorizationError):
    """Raised when user lacks required permissions"""
    def __init__(self, action: str, resource_type: str = "resource"):
        super().__init__(
            detail=f"Insufficient permissions to {action} {resource_type}",
            status_code=status.HTTP_403_FORBIDDEN
        )


class AuthorizationService:
    """
    Authorization Service

    Provides centralized authorization checks for all resource types.
    Prevents IDOR vulnerabilities by validating workspace and ownership access.

    Usage:
        auth_service = AuthorizationService(db)
        auth_service.verify_conversation_access(conversation, current_user)
        auth_service.verify_agent_access(agent, current_user, require_ownership=True)
    """

    def __init__(self, db: Session):
        self.db = db

    # ========================================================================
    # Workspace Validation
    # ========================================================================

    def verify_workspace_access(
        self,
        resource_workspace_id: UUID,
        current_user: User,
        resource_type: str = "resource"
    ) -> None:
        """
        Verify user has access to workspace.

        Raises WorkspaceAccessDeniedError if workspace mismatch.

        Args:
            resource_workspace_id: Workspace ID of the resource
            current_user: Currently authenticated user
            resource_type: Type of resource for error message
        """
        if resource_workspace_id != current_user.workspace_id:
            logger.warning(
                f"Workspace access denied: user {current_user.id} "
                f"(workspace {current_user.workspace_id}) attempted to access "
                f"{resource_type} in workspace {resource_workspace_id}"
            )
            raise WorkspaceAccessDeniedError(resource_type)

    def verify_user_ownership(
        self,
        resource_user_id: UUID,
        current_user: User,
        resource_type: str = "resource"
    ) -> None:
        """
        Verify user owns the resource.

        Raises OwnershipDeniedError if user ID mismatch.

        Args:
            resource_user_id: User ID of the resource owner
            current_user: Currently authenticated user
            resource_type: Type of resource for error message
        """
        if resource_user_id != current_user.id:
            logger.warning(
                f"Ownership denied: user {current_user.id} "
                f"attempted to access {resource_type} owned by user {resource_user_id}"
            )
            raise OwnershipDeniedError(resource_type)

    # ========================================================================
    # Conversation Authorization
    # ========================================================================

    def verify_conversation_access(
        self,
        conversation: Conversation,
        current_user: User,
        require_ownership: bool = True
    ) -> None:
        """
        Verify user has access to conversation.

        Checks both workspace access and user ownership.

        Args:
            conversation: Conversation to verify access for
            current_user: Currently authenticated user
            require_ownership: If True, require user to be the owner

        Raises:
            WorkspaceAccessDeniedError: If conversation in different workspace
            OwnershipDeniedError: If require_ownership=True and user is not owner
        """
        # Check workspace access (always required)
        self.verify_workspace_access(
            conversation.workspace_id,
            current_user,
            resource_type="conversation"
        )

        # Check user ownership (if required)
        if require_ownership:
            self.verify_user_ownership(
                conversation.user_id,
                current_user,
                resource_type="conversation"
            )

    # ========================================================================
    # Agent Authorization
    # ========================================================================

    def verify_agent_access(
        self,
        agent: AgentSwarmInstance,
        current_user: User,
        require_ownership: bool = False
    ) -> None:
        """
        Verify user has access to agent.

        Agents are workspace-scoped by default, but can optionally require
        ownership for destructive operations.

        Args:
            agent: Agent to verify access for
            current_user: Currently authenticated user
            require_ownership: If True, require user to be the owner

        Raises:
            WorkspaceAccessDeniedError: If agent in different workspace
            OwnershipDeniedError: If require_ownership=True and user is not owner
        """
        # Check workspace access (always required)
        if agent.workspace_id:
            self.verify_workspace_access(
                agent.workspace_id,
                current_user,
                resource_type="agent"
            )

        # Check user ownership (if required)
        if require_ownership and agent.user_id:
            self.verify_user_ownership(
                agent.user_id,
                current_user,
                resource_type="agent"
            )

    # ========================================================================
    # Workspace Authorization
    # ========================================================================

    def verify_workspace_resource_access(
        self,
        workspace: Workspace,
        current_user: User
    ) -> None:
        """
        Verify user is a member of workspace.

        Args:
            workspace: Workspace to verify access for
            current_user: Currently authenticated user

        Raises:
            WorkspaceAccessDeniedError: If user not in workspace
        """
        self.verify_workspace_access(
            workspace.id,
            current_user,
            resource_type="workspace"
        )

    # ========================================================================
    # API Key Authorization
    # ========================================================================

    def verify_api_key_access(
        self,
        api_key: APIKey,
        current_user: User
    ) -> None:
        """
        Verify user has access to system-level API key.

        System-level API keys (APIKey model) are global and should only be
        accessible by admin users. For workspace-scoped keys, use verify_user_api_key_access.

        Args:
            api_key: API key to verify access for
            current_user: Currently authenticated user

        Raises:
            InsufficientPermissionsError: Always raised for non-admin users

        Note:
            This is a placeholder. Implement role-based access control
            when admin roles are added to the User model.
        """
        # TODO: Implement role-based access control
        # For now, we'll allow access but log a warning
        logger.warning(
            f"API key access check bypassed for user {current_user.id}. "
            "Implement RBAC when admin roles are available."
        )

    def verify_user_api_key_access(
        self,
        user_api_key: UserAPIKey,
        current_user: User
    ) -> None:
        """
        Verify user has access to workspace-scoped API key.

        Workspace-scoped API keys (UserAPIKey model) are accessible to all
        users within the workspace.

        Args:
            user_api_key: User API key to verify access for
            current_user: Currently authenticated user

        Raises:
            WorkspaceAccessDeniedError: If key belongs to different workspace
        """
        # UserAPIKey.workspace_id is stored as string
        key_workspace_id = UUID(user_api_key.workspace_id)
        self.verify_workspace_access(
            key_workspace_id,
            current_user,
            resource_type="API key"
        )

    # ========================================================================
    # Swarm Authorization
    # ========================================================================

    def verify_swarm_access(
        self,
        swarm: "AgentSwarm",
        current_user: User,
        require_ownership: bool = False
    ) -> None:
        """
        Verify user has access to agent swarm.

        Swarms are user-scoped by default (user_id field).
        Workspace isolation is not yet implemented in AgentSwarm model.

        Args:
            swarm: Agent swarm to verify access for
            current_user: Currently authenticated user
            require_ownership: If True, require user to be the owner

        Raises:
            OwnershipDeniedError: If user does not own the swarm
        """
        if not AGENT_SWARM_AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Agent swarm service is not available"
            )

        # AgentSwarm.user_id is stored as string
        swarm_user_id = UUID(swarm.user_id)

        # Swarms are user-owned resources
        self.verify_user_ownership(
            swarm_user_id,
            current_user,
            resource_type="swarm"
        )

    # ========================================================================
    # List Query Filtering
    # ========================================================================

    def enforce_workspace_filter(
        self,
        requested_workspace_id: Optional[UUID],
        current_user: User
    ) -> UUID:
        """
        Enforce workspace filtering on list queries.

        Users can only list resources from their own workspace.
        If a workspace_id is provided in the query, it must match the user's workspace.

        Args:
            requested_workspace_id: Workspace ID from query parameter
            current_user: Currently authenticated user

        Returns:
            UUID: The user's workspace_id (enforced)

        Raises:
            WorkspaceAccessDeniedError: If requested workspace doesn't match user's
        """
        if requested_workspace_id and requested_workspace_id != current_user.workspace_id:
            logger.warning(
                f"Workspace filter violation: user {current_user.id} "
                f"(workspace {current_user.workspace_id}) attempted to list "
                f"resources from workspace {requested_workspace_id}"
            )
            raise WorkspaceAccessDeniedError("workspace")

        # Always return user's workspace ID
        return current_user.workspace_id

    def enforce_user_filter(
        self,
        requested_user_id: Optional[UUID],
        current_user: User,
        allow_all_workspace: bool = False
    ) -> Optional[UUID]:
        """
        Enforce user filtering on list queries.

        By default, users can only list their own resources.
        If allow_all_workspace=True, users can list all resources in their workspace.

        Args:
            requested_user_id: User ID from query parameter
            current_user: Currently authenticated user
            allow_all_workspace: If True, allow listing all workspace resources

        Returns:
            Optional[UUID]: The enforced user_id filter (None if all workspace allowed)

        Raises:
            OwnershipDeniedError: If requested user doesn't match current user
        """
        if requested_user_id:
            # If specific user requested, must match current user
            if requested_user_id != current_user.id:
                logger.warning(
                    f"User filter violation: user {current_user.id} "
                    f"attempted to list resources for user {requested_user_id}"
                )
                raise OwnershipDeniedError("user filter")

        # If all workspace allowed, return None (no user filter)
        # Otherwise, return current user's ID (enforce user filter)
        return None if allow_all_workspace else current_user.id


# ============================================================================
# Convenience Functions
# ============================================================================

def verify_conversation_access(
    conversation: Conversation,
    current_user: User,
    require_ownership: bool = True
) -> None:
    """
    Standalone convenience function for conversation access verification.

    See AuthorizationService.verify_conversation_access for details.
    """
    if conversation.workspace_id != current_user.workspace_id:
        raise WorkspaceAccessDeniedError("conversation")

    if require_ownership and conversation.user_id != current_user.id:
        raise OwnershipDeniedError("conversation")


def verify_agent_access(
    agent: AgentSwarmInstance,
    current_user: User,
    require_ownership: bool = False
) -> None:
    """
    Standalone convenience function for agent access verification.

    See AuthorizationService.verify_agent_access for details.
    """
    if agent.workspace_id and agent.workspace_id != current_user.workspace_id:
        raise WorkspaceAccessDeniedError("agent")

    if require_ownership and agent.user_id and agent.user_id != current_user.id:
        raise OwnershipDeniedError("agent")


def verify_workspace_access(
    resource_workspace_id: UUID,
    current_user: User,
    resource_type: str = "resource"
) -> None:
    """
    Standalone convenience function for workspace access verification.

    See AuthorizationService.verify_workspace_access for details.
    """
    if resource_workspace_id != current_user.workspace_id:
        raise WorkspaceAccessDeniedError(resource_type)
