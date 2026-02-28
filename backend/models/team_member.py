"""
Team Member Model

Manages team member invitations, roles, and status.
Supports role-based access control and invitation workflows.
"""

from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column,
    String,
    ForeignKey,
    DateTime,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4
from backend.db.base_class import Base
from sqlalchemy.sql import func


class TeamMemberRole(str, Enum):
    """Team member role enumeration"""
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


class TeamMemberStatus(str, Enum):
    """Team member status enumeration"""
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class TeamMember(Base):
    """
    Team Member Model

    Represents a team member with role-based permissions,
    invitation tracking, and status management.
    """
    __tablename__ = "team_members"

    # Primary identification
    id = Column(UUID(), primary_key=True, default=uuid4)
    email = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)

    # Role and status
    role = Column(
        SQLEnum(
            TeamMemberRole,
            name="team_member_role",
            native_enum=True,
            create_constraint=True,
            values_callable=lambda x: [e.value for e in x]
        ),
        default=TeamMemberRole.MEMBER,
        nullable=False,
        index=True
    )

    status = Column(
        SQLEnum(
            TeamMemberStatus,
            name="team_member_status",
            native_enum=True,
            create_constraint=True,
            values_callable=lambda x: [e.value for e in x]
        ),
        default=TeamMemberStatus.PENDING,
        nullable=False,
        index=True
    )

    # Invitation tracking
    invited_by = Column(UUID(), nullable=True)
    invited_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    joined_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<TeamMember {self.email} ({self.role.value})>"
