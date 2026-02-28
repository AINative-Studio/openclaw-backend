"""
Team Management API Schemas

Pydantic v2 request/response models for the team management REST API.
"""

from typing import Optional
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime


class InviteMemberRequest(BaseModel):
    """Request body for POST /api/v1/team/members/invite"""
    email: EmailStr = Field(..., description="Member email address")
    name: str = Field(..., min_length=1, max_length=255, description="Member full name")
    role: str = Field(..., description="Member role (OWNER/ADMIN/MEMBER/VIEWER)")


class UpdateRoleRequest(BaseModel):
    """Request body for PUT /api/v1/team/members/{member_id}/role"""
    role: str = Field(..., description="New role (OWNER/ADMIN/MEMBER/VIEWER)")


class TeamMemberResponse(BaseModel):
    """Single team member response"""
    id: str
    email: str
    name: str
    role: str
    status: str
    invited_by: Optional[str] = None
    invited_at: str
    joined_at: Optional[str] = None

    class Config:
        from_attributes = True


class TeamMembersListResponse(BaseModel):
    """Team members list response"""
    members: list[TeamMemberResponse]


class InviteMemberResponse(BaseModel):
    """Invite member response with token"""
    member: TeamMemberResponse
    invite_token: str
    message: str = "Invitation sent successfully"


class RemoveMemberResponse(BaseModel):
    """Remove member response"""
    message: str


class AcceptInviteResponse(BaseModel):
    """Accept invite response"""
    id: str
    email: str
    name: str
    role: str
    status: str
    joined_at: str
    message: str = "Invitation accepted successfully"
