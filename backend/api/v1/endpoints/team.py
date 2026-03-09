"""
Team Management API Endpoints

REST API endpoints for team member management:
- List team members
- Invite new members
- Remove members
- Update member roles
- Accept invitations
"""

import logging
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from backend.security.auth_dependencies import get_current_active_user
from backend.models.user import User
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.services.team_service import TeamService
from backend.schemas.team import (
    InviteMemberRequest,
    UpdateRoleRequest,
    TeamMembersListResponse,
    TeamMemberResponse,
    InviteMemberResponse,
    RemoveMemberResponse,
    AcceptInviteResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Team Management"])


def _serialize_member(member) -> dict:
    """Convert TeamMember ORM instance to response dict"""
    return {
        "id": str(member.id),
        "email": member.email,
        "name": member.name,
        "role": member.role.value,
        "status": member.status.value,
        "invited_by": str(member.invited_by) if member.invited_by else None,
        "invited_at": member.invited_at.isoformat() if member.invited_at else None,
        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
    }


@router.get(
    "/team/members",
    response_model=TeamMembersListResponse,
    status_code=status.HTTP_200_OK,
    summary="List team members",
    description="Get a list of all team members with their roles and status"
)
async def list_team_members(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> TeamMembersListResponse:
    """
    List all team members

    Returns:
        List of team members with roles and status
    """
    try:
        service = TeamService(db)
        members = service.list_members()

        return TeamMembersListResponse(
            members=[_serialize_member(m) for m in members]
        )
    except Exception as e:
        logger.error(f"Failed to list team members: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list team members: {str(e)}"
        )


@router.post(
    "/team/members/invite",
    response_model=InviteMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite team member",
    description="Invite a new team member with specified role. Requires OWNER or ADMIN role."
)
async def invite_member(
    request: InviteMemberRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> InviteMemberResponse:
    """
    Invite a new team member

    Args:
        request: Invitation details (email, name, role)

    Returns:
        Created member and invite token

    Raises:
        409: Email already exists
        403: Insufficient permissions
        422: Invalid role
    """
    # TODO: Extract current user role from authentication
    # For now, allow all invitations for development
    inviter_role = "ADMIN"  # Replace with: current_user.role

    try:
        service = TeamService(db)
        member, invite_token = service.invite_member(request, inviter_role=inviter_role)

        return InviteMemberResponse(
            member=_serialize_member(member),
            invite_token=invite_token,
            message="Invitation sent successfully"
        )
    except PermissionError as e:
        logger.warning(f"Permission denied for invite: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        if "already exists" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to invite member: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to invite member: {str(e)}"
        )


@router.delete(
    "/team/members/{member_id}",
    response_model=RemoveMemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove team member",
    description="Remove a team member. Requires OWNER or ADMIN role. Cannot remove OWNER."
)
async def remove_member(
    member_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> RemoveMemberResponse:
    """
    Remove a team member

    Args:
        member_id: UUID of member to remove

    Returns:
        Success message

    Raises:
        404: Member not found
        403: Insufficient permissions
        400: Cannot remove OWNER
    """
    # TODO: Extract current user role from authentication
    remover_role = "ADMIN"  # Replace with: current_user.role

    try:
        member_uuid = UUID(member_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid member ID format"
        )

    try:
        service = TeamService(db)
        service.remove_member(member_uuid, remover_role=remover_role)

        return RemoveMemberResponse(
            message=f"Member {member_id} removed successfully"
        )
    except PermissionError as e:
        logger.warning(f"Permission denied for remove: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to remove member: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove member: {str(e)}"
        )


@router.put(
    "/team/members/{member_id}/role",
    response_model=TeamMemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Update member role",
    description="Update a team member's role. Requires OWNER or ADMIN role. Cannot change OWNER role."
)
async def update_member_role(
    member_id: str,
    request: UpdateRoleRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> TeamMemberResponse:
    """
    Update a team member's role

    Args:
        member_id: UUID of member to update
        request: New role

    Returns:
        Updated member

    Raises:
        404: Member not found
        403: Insufficient permissions
        400: Cannot change OWNER role
        422: Invalid role
    """
    # TODO: Extract current user role from authentication
    updater_role = "ADMIN"  # Replace with: current_user.role

    try:
        member_uuid = UUID(member_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid member ID format"
        )

    try:
        service = TeamService(db)
        updated_member = service.update_member_role(
            member_uuid,
            request.role,
            updater_role=updater_role
        )

        return _serialize_member(updated_member)
    except PermissionError as e:
        logger.warning(f"Permission denied for role update: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        elif "invalid role" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to update member role: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update member role: {str(e)}"
        )


@router.post(
    "/team/members/accept-invite/{token}",
    response_model=AcceptInviteResponse,
    status_code=status.HTTP_200_OK,
    summary="Accept team invitation",
    description="Accept a team invitation using the invite token"
)
async def accept_invite(
    token: str,
    db: Session = Depends(get_db)
) -> AcceptInviteResponse:
    """
    Accept a team invitation

    Args:
        token: JWT invite token

    Returns:
        Activated member details

    Raises:
        400: Invalid or expired token
        409: Invite already accepted
    """
    try:
        service = TeamService(db)
        member = service.accept_invite(token)

        return AcceptInviteResponse(
            id=str(member.id),
            email=member.email,
            name=member.name,
            role=member.role.value,
            status=member.status.value,
            joined_at=member.joined_at.isoformat() if member.joined_at else None,
            message="Invitation accepted successfully"
        )
    except ValueError as e:
        if "already accepted" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to accept invite: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to accept invite: {str(e)}"
        )
