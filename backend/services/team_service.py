"""
Team Management Service

Business logic for team member management including:
- Member invitation with JWT tokens
- Role-based access control
- Email uniqueness validation
- Invitation acceptance
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from uuid import UUID, uuid4

import jwt
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend.models.team_member import TeamMember, TeamMemberRole, TeamMemberStatus
from backend.schemas.team import InviteMemberRequest

logger = logging.getLogger(__name__)

# JWT secret from environment
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
TOKEN_ALGORITHM = "HS256"
INVITE_TOKEN_EXPIRATION_DAYS = 7


class TeamService:
    """Service for team member management operations"""

    def __init__(self, db: Session, current_user_id: Optional[UUID] = None):
        self.db = db
        self.current_user_id = current_user_id

    def list_members(self) -> list[TeamMember]:
        """
        List all team members

        Returns:
            List of TeamMember instances
        """
        return self.db.query(TeamMember).order_by(TeamMember.invited_at.desc()).all()

    def invite_member(
        self,
        request: InviteMemberRequest,
        inviter_role: Optional[str] = None
    ) -> Tuple[TeamMember, str]:
        """
        Invite a new team member

        Args:
            request: Invitation request with email, name, role
            inviter_role: Role of the user sending the invitation

        Returns:
            Tuple of (TeamMember, invite_token)

        Raises:
            PermissionError: If inviter is not OWNER or ADMIN
            ValueError: If email already exists or role is invalid
        """
        # Enforce role-based permissions
        if inviter_role and inviter_role not in ["OWNER", "ADMIN"]:
            raise PermissionError("Only OWNER/ADMIN can invite members")

        # Validate role
        try:
            role_enum = TeamMemberRole(request.role)
        except ValueError:
            raise ValueError(f"Invalid role: {request.role}")

        # Check email uniqueness
        existing_member = self.db.query(TeamMember).filter(
            TeamMember.email == request.email
        ).first()

        if existing_member:
            raise ValueError(f"Email already exists: {request.email}")

        # Create member with PENDING status
        member = TeamMember(
            id=uuid4(),
            email=request.email,
            name=request.name,
            role=role_enum,
            status=TeamMemberStatus.PENDING,
            invited_by=self.current_user_id,
            invited_at=datetime.now(timezone.utc),
            joined_at=None
        )

        try:
            self.db.add(member)
            self.db.commit()
            self.db.refresh(member)
        except IntegrityError as e:
            self.db.rollback()
            raise ValueError(f"Email already exists: {request.email}") from e

        # Generate invite token
        invite_token = self._generate_invite_token(
            member_id=str(member.id),
            email=member.email,
            role=member.role.value
        )

        logger.info(f"Member invited: {member.email} with role {member.role.value}")

        # TODO: Send invitation email via notification service
        # This should integrate with existing notification infrastructure
        # For now, return token for manual delivery

        return member, invite_token

    def remove_member(
        self,
        member_id: UUID,
        remover_role: Optional[str] = None
    ) -> bool:
        """
        Remove a team member

        Args:
            member_id: UUID of member to remove
            remover_role: Role of the user removing the member

        Returns:
            True if removed successfully

        Raises:
            PermissionError: If remover is not OWNER or ADMIN
            ValueError: If member not found or attempting to remove OWNER
        """
        # Enforce role-based permissions
        if remover_role and remover_role not in ["OWNER", "ADMIN"]:
            raise PermissionError("Only OWNER/ADMIN can remove members")

        member = self.db.query(TeamMember).filter(TeamMember.id == member_id).first()

        if not member:
            raise ValueError("Member not found")

        # Prevent removing OWNER
        if member.role == TeamMemberRole.OWNER:
            raise ValueError("Cannot remove OWNER")

        self.db.delete(member)
        self.db.commit()

        logger.info(f"Member removed: {member.email}")
        return True

    def update_member_role(
        self,
        member_id: UUID,
        new_role: str,
        updater_role: Optional[str] = None
    ) -> TeamMember:
        """
        Update a team member's role

        Args:
            member_id: UUID of member to update
            new_role: New role value
            updater_role: Role of the user updating the role

        Returns:
            Updated TeamMember instance

        Raises:
            PermissionError: If updater is not OWNER or ADMIN
            ValueError: If member not found, invalid role, or attempting to change OWNER
        """
        # Enforce role-based permissions
        if updater_role and updater_role not in ["OWNER", "ADMIN"]:
            raise PermissionError("Only OWNER/ADMIN can update roles")

        member = self.db.query(TeamMember).filter(TeamMember.id == member_id).first()

        if not member:
            raise ValueError("Member not found")

        # Prevent changing OWNER role
        if member.role == TeamMemberRole.OWNER:
            raise ValueError("Cannot change OWNER role")

        # Validate new role
        try:
            new_role_enum = TeamMemberRole(new_role)
        except ValueError:
            raise ValueError(f"Invalid role: {new_role}")

        member.role = new_role_enum
        self.db.commit()
        self.db.refresh(member)

        logger.info(f"Member role updated: {member.email} to {new_role}")
        return member

    def accept_invite(self, token: str) -> TeamMember:
        """
        Accept a team invitation using the invite token

        Args:
            token: JWT invite token

        Returns:
            Activated TeamMember instance

        Raises:
            ValueError: If token is invalid, expired, or already accepted
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[TOKEN_ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expired")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {str(e)}")

        member_id = payload.get("member_id")
        email = payload.get("email")

        if not member_id or not email:
            raise ValueError("Invalid token payload")

        member = self.db.query(TeamMember).filter(TeamMember.id == member_id).first()

        if not member:
            raise ValueError("Member not found")

        if member.email != email:
            raise ValueError("Token email mismatch")

        if member.status == TeamMemberStatus.ACTIVE:
            raise ValueError("Invite already accepted")

        # Activate member
        member.status = TeamMemberStatus.ACTIVE
        member.joined_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(member)

        logger.info(f"Member activated: {member.email}")
        return member

    def _generate_invite_token(
        self,
        member_id: str,
        email: str,
        role: str
    ) -> str:
        """
        Generate a JWT invite token with 7-day expiration

        Args:
            member_id: Member UUID
            email: Member email
            role: Member role

        Returns:
            JWT token string
        """
        expiration = datetime.now(timezone.utc) + timedelta(days=INVITE_TOKEN_EXPIRATION_DAYS)

        payload = {
            "member_id": member_id,
            "email": email,
            "role": role,
            "exp": expiration,
            "iat": datetime.now(timezone.utc),
            "type": "team_invite"
        }

        token = jwt.encode(payload, SECRET_KEY, algorithm=TOKEN_ALGORITHM)
        return token
