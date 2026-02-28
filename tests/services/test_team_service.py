"""
Team Service Unit Tests

Tests for team service business logic including:
- JWT token generation and validation
- Email uniqueness enforcement
- Role-based permission checks
- Member lifecycle management
"""

import pytest
import jwt
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import MagicMock
from sqlalchemy.exc import IntegrityError

from backend.services.team_service import TeamService, INVITE_TOKEN_EXPIRATION_DAYS, SECRET_KEY, TOKEN_ALGORITHM
from backend.models.team_member import TeamMember, TeamMemberRole, TeamMemberStatus
from backend.schemas.team import InviteMemberRequest


@pytest.fixture
def mock_db():
    """Create a mock database session"""
    return MagicMock()


@pytest.fixture
def service(mock_db):
    """Create TeamService instance with mock DB"""
    return TeamService(mock_db, current_user_id=uuid4())


class TestListMembers:
    """Tests for list_members method"""

    def test_returns_all_members_ordered_by_invite_date(self, service, mock_db):
        """
        GIVEN multiple team members
        WHEN list_members is called
        THEN it should return all members ordered by invited_at desc
        """
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [
            MagicMock(email="user1@example.com"),
            MagicMock(email="user2@example.com")
        ]

        result = service.list_members()

        assert len(result) == 2
        mock_db.query.assert_called_once_with(TeamMember)
        mock_query.order_by.assert_called_once()


class TestInviteMember:
    """Tests for invite_member method"""

    def test_successfully_invites_member_with_pending_status(self, service, mock_db):
        """
        GIVEN valid invitation request
        WHEN invite_member is called
        THEN it should create member with PENDING status and return token
        """
        request = InviteMemberRequest(
            email="newuser@example.com",
            name="New User",
            role="MEMBER"
        )

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        member, token = service.invite_member(request, inviter_role="ADMIN")

        assert mock_db.add.called
        assert mock_db.commit.called
        assert isinstance(token, str)
        assert len(token) > 0

    def test_rejects_invitation_from_non_admin(self, service, mock_db):
        """
        GIVEN inviter with MEMBER role
        WHEN invite_member is called
        THEN it should raise PermissionError
        """
        request = InviteMemberRequest(
            email="test@example.com",
            name="Test",
            role="MEMBER"
        )

        with pytest.raises(PermissionError, match="Only OWNER/ADMIN"):
            service.invite_member(request, inviter_role="MEMBER")

    def test_rejects_duplicate_email(self, service, mock_db):
        """
        GIVEN existing member with same email
        WHEN invite_member is called
        THEN it should raise ValueError
        """
        request = InviteMemberRequest(
            email="existing@example.com",
            name="Existing",
            role="MEMBER"
        )

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = MagicMock(email="existing@example.com")

        with pytest.raises(ValueError, match="already exists"):
            service.invite_member(request, inviter_role="ADMIN")

    def test_rejects_invalid_role(self, service, mock_db):
        """
        GIVEN invalid role
        WHEN invite_member is called
        THEN it should raise ValueError
        """
        request = InviteMemberRequest(
            email="test@example.com",
            name="Test",
            role="INVALID_ROLE"
        )

        with pytest.raises(ValueError, match="Invalid role"):
            service.invite_member(request, inviter_role="ADMIN")

    def test_handles_integrity_error_on_duplicate(self, service, mock_db):
        """
        GIVEN race condition with duplicate email
        WHEN invite_member commits
        THEN it should rollback and raise ValueError
        """
        request = InviteMemberRequest(
            email="race@example.com",
            name="Race",
            role="MEMBER"
        )

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        mock_db.commit.side_effect = IntegrityError("duplicate", "params", "orig")

        with pytest.raises(ValueError, match="already exists"):
            service.invite_member(request, inviter_role="ADMIN")

        assert mock_db.rollback.called


class TestRemoveMember:
    """Tests for remove_member method"""

    def test_successfully_removes_member(self, service, mock_db):
        """
        GIVEN valid member_id
        WHEN remove_member is called
        THEN it should delete the member
        """
        member_id = uuid4()
        mock_member = MagicMock()
        mock_member.role = TeamMemberRole.MEMBER

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_member

        result = service.remove_member(member_id, remover_role="ADMIN")

        assert result is True
        mock_db.delete.assert_called_once_with(mock_member)
        mock_db.commit.assert_called_once()

    def test_rejects_removal_from_non_admin(self, service, mock_db):
        """
        GIVEN remover with MEMBER role
        WHEN remove_member is called
        THEN it should raise PermissionError
        """
        with pytest.raises(PermissionError, match="Only OWNER/ADMIN"):
            service.remove_member(uuid4(), remover_role="MEMBER")

    def test_rejects_removal_of_nonexistent_member(self, service, mock_db):
        """
        GIVEN nonexistent member_id
        WHEN remove_member is called
        THEN it should raise ValueError
        """
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            service.remove_member(uuid4(), remover_role="ADMIN")

    def test_prevents_removing_owner(self, service, mock_db):
        """
        GIVEN member with OWNER role
        WHEN remove_member is called
        THEN it should raise ValueError
        """
        mock_member = MagicMock()
        mock_member.role = TeamMemberRole.OWNER

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_member

        with pytest.raises(ValueError, match="Cannot remove OWNER"):
            service.remove_member(uuid4(), remover_role="ADMIN")


class TestUpdateMemberRole:
    """Tests for update_member_role method"""

    def test_successfully_updates_role(self, service, mock_db):
        """
        GIVEN valid member and new role
        WHEN update_member_role is called
        THEN it should update the role
        """
        member_id = uuid4()
        mock_member = MagicMock()
        mock_member.role = TeamMemberRole.MEMBER

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_member

        result = service.update_member_role(member_id, "ADMIN", updater_role="OWNER")

        assert mock_member.role == TeamMemberRole.ADMIN
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_member)

    def test_rejects_update_from_non_admin(self, service, mock_db):
        """
        GIVEN updater with MEMBER role
        WHEN update_member_role is called
        THEN it should raise PermissionError
        """
        with pytest.raises(PermissionError, match="Only OWNER/ADMIN"):
            service.update_member_role(uuid4(), "ADMIN", updater_role="VIEWER")

    def test_rejects_changing_owner_role(self, service, mock_db):
        """
        GIVEN member with OWNER role
        WHEN update_member_role is called
        THEN it should raise ValueError
        """
        mock_member = MagicMock()
        mock_member.role = TeamMemberRole.OWNER

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_member

        with pytest.raises(ValueError, match="Cannot change OWNER role"):
            service.update_member_role(uuid4(), "ADMIN", updater_role="ADMIN")


class TestAcceptInvite:
    """Tests for accept_invite method"""

    def test_successfully_accepts_valid_token(self, service, mock_db):
        """
        GIVEN valid invite token
        WHEN accept_invite is called
        THEN it should activate the member
        """
        member_id = str(uuid4())
        email = "test@example.com"

        # Generate valid token
        token = jwt.encode({
            "member_id": member_id,
            "email": email,
            "role": "MEMBER",
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
            "iat": datetime.now(timezone.utc),
            "type": "team_invite"
        }, SECRET_KEY, algorithm=TOKEN_ALGORITHM)

        mock_member = MagicMock()
        mock_member.id = member_id
        mock_member.email = email
        mock_member.status = TeamMemberStatus.PENDING

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_member

        result = service.accept_invite(token)

        assert mock_member.status == TeamMemberStatus.ACTIVE
        assert mock_member.joined_at is not None
        mock_db.commit.assert_called_once()

    def test_rejects_expired_token(self, service, mock_db):
        """
        GIVEN expired invite token
        WHEN accept_invite is called
        THEN it should raise ValueError
        """
        token = jwt.encode({
            "member_id": str(uuid4()),
            "email": "test@example.com",
            "exp": datetime.now(timezone.utc) - timedelta(days=1),
            "iat": datetime.now(timezone.utc) - timedelta(days=8)
        }, SECRET_KEY, algorithm=TOKEN_ALGORITHM)

        with pytest.raises(ValueError, match="expired"):
            service.accept_invite(token)

    def test_rejects_invalid_token(self, service, mock_db):
        """
        GIVEN invalid token
        WHEN accept_invite is called
        THEN it should raise ValueError
        """
        with pytest.raises(ValueError, match="Invalid token"):
            service.accept_invite("invalid.token.here")

    def test_rejects_already_activated_member(self, service, mock_db):
        """
        GIVEN already activated member
        WHEN accept_invite is called
        THEN it should raise ValueError
        """
        member_id = str(uuid4())
        email = "test@example.com"

        token = jwt.encode({
            "member_id": member_id,
            "email": email,
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
            "iat": datetime.now(timezone.utc)
        }, SECRET_KEY, algorithm=TOKEN_ALGORITHM)

        mock_member = MagicMock()
        mock_member.id = member_id
        mock_member.email = email
        mock_member.status = TeamMemberStatus.ACTIVE

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_member

        with pytest.raises(ValueError, match="already accepted"):
            service.accept_invite(token)


class TestGenerateInviteToken:
    """Tests for _generate_invite_token method"""

    def test_generates_valid_jwt_with_7_day_expiration(self, service):
        """
        GIVEN member details
        WHEN _generate_invite_token is called
        THEN it should return JWT with 7-day expiration
        """
        member_id = str(uuid4())
        email = "test@example.com"
        role = "MEMBER"

        token = service._generate_invite_token(member_id, email, role)

        # Decode and verify
        payload = jwt.decode(token, SECRET_KEY, algorithms=[TOKEN_ALGORITHM])

        assert payload["member_id"] == member_id
        assert payload["email"] == email
        assert payload["role"] == role
        assert payload["type"] == "team_invite"

        # Verify expiration is ~7 days from now
        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        days_until_expiry = (exp_time - now).days

        assert days_until_expiry >= 6  # Account for test execution time
        assert days_until_expiry <= 7

    def test_token_contains_all_required_claims(self, service):
        """
        GIVEN member details
        WHEN _generate_invite_token is called
        THEN token should contain all required claims
        """
        token = service._generate_invite_token(
            str(uuid4()),
            "test@example.com",
            "ADMIN"
        )

        payload = jwt.decode(token, SECRET_KEY, algorithms=[TOKEN_ALGORITHM])

        required_claims = ["member_id", "email", "role", "exp", "iat", "type"]
        for claim in required_claims:
            assert claim in payload
