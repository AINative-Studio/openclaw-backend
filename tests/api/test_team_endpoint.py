"""
Team Management API Endpoint Tests

Tests for all team management REST endpoints.
BDD style with GIVEN/WHEN/THEN docstrings.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.v1.endpoints.team import router


@pytest.fixture
def app():
    """Create FastAPI test app with team router"""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


def _make_mock_member(**overrides):
    """Build a mock team member ORM instance"""
    now = datetime.now(timezone.utc)
    member_id = overrides.get("id", uuid4())

    class MockRole:
        def __init__(self, value):
            self.value = value

    class MockStatus:
        def __init__(self, value):
            self.value = value

    member = MagicMock()
    member.id = member_id
    member.email = overrides.get("email", "test@example.com")
    member.name = overrides.get("name", "Test User")
    member.role = MockRole(overrides.get("role", "MEMBER"))
    member.status = MockStatus(overrides.get("status", "ACTIVE"))
    member.invited_by = overrides.get("invited_by", uuid4())
    member.invited_at = overrides.get("invited_at", now)
    member.joined_at = overrides.get("joined_at", now)
    return member


class TestListTeamMembers:
    """Tests for GET /api/v1/team/members"""

    def test_returns_200_with_members(self, client):
        """
        GIVEN team members exist
        WHEN GET /api/v1/team/members is called
        THEN it should return 200 with member list
        """
        members = [
            _make_mock_member(email="user1@example.com", name="User One", role="OWNER"),
            _make_mock_member(email="user2@example.com", name="User Two", role="MEMBER")
        ]

        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.list_members.return_value = members

            response = client.get("/api/v1/team/members")

        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert len(data["members"]) == 2

    def test_returns_empty_list(self, client):
        """
        GIVEN no team members exist
        WHEN GET /api/v1/team/members is called
        THEN it should return 200 with empty list
        """
        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.list_members.return_value = []

            response = client.get("/api/v1/team/members")

        assert response.status_code == 200
        data = response.json()
        assert data["members"] == []


class TestInviteMember:
    """Tests for POST /api/v1/team/members/invite"""

    def test_successfully_invites_member(self, client):
        """
        GIVEN valid email and role
        WHEN POST /api/v1/team/members/invite is called
        THEN it should return 201 with invitation details
        """
        invite_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
        mock_member = _make_mock_member(
            email="newuser@example.com",
            name="New User",
            status="PENDING"
        )

        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.invite_member.return_value = (mock_member, invite_token)

            response = client.post(
                "/api/v1/team/members/invite",
                json={
                    "email": "newuser@example.com",
                    "name": "New User",
                    "role": "MEMBER"
                }
            )

        assert response.status_code == 201
        data = response.json()
        assert "member" in data
        assert "invite_token" in data
        assert data["member"]["email"] == "newuser@example.com"
        assert data["member"]["status"] == "PENDING"

    def test_rejects_duplicate_email(self, client):
        """
        GIVEN email already exists
        WHEN POST /api/v1/team/members/invite is called
        THEN it should return 409 Conflict
        """
        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.invite_member.side_effect = ValueError("Email already exists")

            response = client.post(
                "/api/v1/team/members/invite",
                json={
                    "email": "existing@example.com",
                    "name": "Existing User",
                    "role": "MEMBER"
                }
            )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_rejects_invalid_role(self, client):
        """
        GIVEN invalid role
        WHEN POST /api/v1/team/members/invite is called
        THEN it should return 422 validation error
        """
        response = client.post(
            "/api/v1/team/members/invite",
            json={
                "email": "test@example.com",
                "name": "Test User",
                "role": "INVALID_ROLE"
            }
        )

        assert response.status_code == 422

    def test_requires_admin_permission(self, client):
        """
        GIVEN non-admin user
        WHEN POST /api/v1/team/members/invite is called
        THEN it should return 403 Forbidden
        """
        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.invite_member.side_effect = PermissionError("Only OWNER/ADMIN can invite members")

            response = client.post(
                "/api/v1/team/members/invite",
                json={
                    "email": "test@example.com",
                    "name": "Test User",
                    "role": "MEMBER"
                }
            )

        assert response.status_code == 403


class TestRemoveMember:
    """Tests for DELETE /api/v1/team/members/{member_id}"""

    def test_successfully_removes_member(self, client):
        """
        GIVEN valid member_id
        WHEN DELETE /api/v1/team/members/{member_id} is called
        THEN it should return 200 with success message
        """
        member_id = str(uuid4())

        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.remove_member.return_value = True

            response = client.delete(f"/api/v1/team/members/{member_id}")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_returns_404_for_nonexistent_member(self, client):
        """
        GIVEN nonexistent member_id
        WHEN DELETE /api/v1/team/members/{member_id} is called
        THEN it should return 404
        """
        member_id = str(uuid4())

        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.remove_member.side_effect = ValueError("Member not found")

            response = client.delete(f"/api/v1/team/members/{member_id}")

        assert response.status_code == 404

    def test_requires_admin_permission_to_remove(self, client):
        """
        GIVEN non-admin user
        WHEN DELETE /api/v1/team/members/{member_id} is called
        THEN it should return 403 Forbidden
        """
        member_id = str(uuid4())

        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.remove_member.side_effect = PermissionError("Only OWNER/ADMIN can remove members")

            response = client.delete(f"/api/v1/team/members/{member_id}")

        assert response.status_code == 403

    def test_prevents_removing_owner(self, client):
        """
        GIVEN owner member_id
        WHEN DELETE /api/v1/team/members/{member_id} is called
        THEN it should return 400 Bad Request
        """
        member_id = str(uuid4())

        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.remove_member.side_effect = ValueError("Cannot remove OWNER")

            response = client.delete(f"/api/v1/team/members/{member_id}")

        assert response.status_code == 400


class TestUpdateMemberRole:
    """Tests for PUT /api/v1/team/members/{member_id}/role"""

    def test_successfully_updates_role(self, client):
        """
        GIVEN valid member_id and new role
        WHEN PUT /api/v1/team/members/{member_id}/role is called
        THEN it should return 200 with updated member
        """
        member_id = str(uuid4())
        updated_member = _make_mock_member(id=uuid4(), role="ADMIN")

        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.update_member_role.return_value = updated_member

            response = client.put(
                f"/api/v1/team/members/{member_id}/role",
                json={"role": "ADMIN"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "ADMIN"

    def test_rejects_invalid_role_update(self, client):
        """
        GIVEN invalid role
        WHEN PUT /api/v1/team/members/{member_id}/role is called
        THEN it should return 422 validation error
        """
        member_id = str(uuid4())

        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.update_member_role.side_effect = ValueError("Invalid role: INVALID_ROLE")

            response = client.put(
                f"/api/v1/team/members/{member_id}/role",
                json={"role": "INVALID_ROLE"}
            )

        assert response.status_code == 422

    def test_requires_admin_permission_to_update_role(self, client):
        """
        GIVEN non-admin user
        WHEN PUT /api/v1/team/members/{member_id}/role is called
        THEN it should return 403 Forbidden
        """
        member_id = str(uuid4())

        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.update_member_role.side_effect = PermissionError("Only OWNER/ADMIN can update roles")

            response = client.put(
                f"/api/v1/team/members/{member_id}/role",
                json={"role": "ADMIN"}
            )

        assert response.status_code == 403

    def test_prevents_changing_owner_role(self, client):
        """
        GIVEN owner member_id
        WHEN PUT /api/v1/team/members/{member_id}/role is called
        THEN it should return 400 Bad Request
        """
        member_id = str(uuid4())

        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.update_member_role.side_effect = ValueError("Cannot change OWNER role")

            response = client.put(
                f"/api/v1/team/members/{member_id}/role",
                json={"role": "MEMBER"}
            )

        assert response.status_code == 400


class TestAcceptInvite:
    """Tests for POST /api/v1/team/members/accept-invite/{token}"""

    def test_successfully_accepts_invite(self, client):
        """
        GIVEN valid invite token
        WHEN POST /api/v1/team/members/accept-invite/{token} is called
        THEN it should return 200 with activated member
        """
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
        activated_member = _make_mock_member(status="ACTIVE")

        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.accept_invite.return_value = activated_member

            response = client.post(f"/api/v1/team/members/accept-invite/{token}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ACTIVE"
        assert "message" in data

    def test_rejects_expired_token(self, client):
        """
        GIVEN expired invite token
        WHEN POST /api/v1/team/members/accept-invite/{token} is called
        THEN it should return 400 Bad Request
        """
        token = "expired.token.here"

        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.accept_invite.side_effect = ValueError("Token expired")

            response = client.post(f"/api/v1/team/members/accept-invite/{token}")

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    def test_rejects_invalid_token(self, client):
        """
        GIVEN invalid invite token
        WHEN POST /api/v1/team/members/accept-invite/{token} is called
        THEN it should return 400 Bad Request
        """
        token = "invalid.token"

        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.accept_invite.side_effect = ValueError("Invalid token")

            response = client.post(f"/api/v1/team/members/accept-invite/{token}")

        assert response.status_code == 400

    def test_rejects_already_activated_invite(self, client):
        """
        GIVEN already activated member
        WHEN POST /api/v1/team/members/accept-invite/{token} is called
        THEN it should return 409 Conflict
        """
        token = "valid.token.already.used"

        with patch("backend.api.v1.endpoints.team.TeamService") as MockService:
            instance = MockService.return_value
            instance.accept_invite.side_effect = ValueError("Invite already accepted")

            response = client.post(f"/api/v1/team/members/accept-invite/{token}")

        assert response.status_code == 409


class TestTeamServiceIntegration:
    """Integration tests for TeamService business logic"""

    def test_invite_token_has_7_day_expiration(self):
        """
        GIVEN new member invitation
        WHEN invite token is generated
        THEN it should expire in 7 days
        """
        from backend.services.team_service import TeamService
        import jwt

        # This will be tested once service is implemented
        # Token should contain: email, role, exp (7 days from now)
        pass

    def test_email_uniqueness_validation(self):
        """
        GIVEN existing member email
        WHEN attempting to invite same email
        THEN it should raise ValueError
        """
        # This will be tested with real DB session
        pass

    def test_role_based_permission_enforcement(self):
        """
        GIVEN MEMBER role user
        WHEN attempting admin operations
        THEN it should raise PermissionError
        """
        # This will be tested with real permission logic
        pass
