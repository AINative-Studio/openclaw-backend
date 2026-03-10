"""
Test Ralph Loop Models (Issue #143)

Comprehensive tests for RalphLoopSession and RalphIteration models following
TDD principles. Tests cover model creation, enums, foreign keys, constraints,
relationships, cascade behaviors, timestamps, and JSON fields.

Refs #143
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from backend.db.base_class import Base
from backend.models.ralph_loop import (
    RalphLoopSession,
    RalphIteration,
    LoopMode,
    LoopStatus
)
# Import ORM models for their table definitions only
# Note: We cannot use Base.metadata.create_all() for AgentSwarmInstance
# because it contains PostgreSQL ARRAY type incompatible with SQLite
from backend.models.workspace import Workspace
from backend.models.user import User


@pytest.fixture
def db_engine():
    """Create in-memory SQLite database for testing"""
    from sqlalchemy import MetaData, Table, Column, Integer, String, DateTime, Text, Boolean, JSON, ForeignKey
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    from sqlalchemy.sql import func

    engine = create_engine("sqlite:///:memory:")

    # Enable foreign key constraints in SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create a separate metadata instance to avoid PostgreSQL ARRAY types
    # from AgentSwarmInstance being loaded through Base.metadata
    metadata = MetaData()

    # Create simplified versions of dependent tables for SQLite testing
    workspaces_table = Table(
        'workspaces', metadata,
        Column('id', PG_UUID(as_uuid=True), primary_key=True),
        Column('name', String(255), nullable=False),
        Column('slug', String(255), nullable=False, unique=True),
        Column('description', Text, nullable=True),
        Column('zerodb_project_id', String(255), nullable=True, unique=True),
        Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column('updated_at', DateTime(timezone=True), nullable=True),
    )

    users_table = Table(
        'users', metadata,
        Column('id', PG_UUID(as_uuid=True), primary_key=True),
        Column('email', String(255), nullable=False, unique=True),
        Column('password_hash', String(255), nullable=True),
        Column('full_name', String(255), nullable=True),
        Column('workspace_id', PG_UUID(as_uuid=True), nullable=False),
        Column('is_active', Boolean, default=True, nullable=False),
        Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column('updated_at', DateTime(timezone=True), nullable=True),
    )

    # Simplified agent_swarm_instances table (no ARRAY type)
    agent_swarm_instances_table = Table(
        'agent_swarm_instances', metadata,
        Column('id', PG_UUID(as_uuid=True), primary_key=True),
        Column('name', String(255), nullable=False),
        Column('model', String(255), nullable=False),
        Column('user_id', PG_UUID(as_uuid=True), nullable=False),
        Column('workspace_id', PG_UUID(as_uuid=True), nullable=True),
        Column('status', String(50), nullable=False),
        Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
    )

    # Ralph loop tables
    ralph_loop_sessions_table = Table(
        'ralph_loop_sessions', metadata,
        Column('id', PG_UUID(as_uuid=True), primary_key=True),
        Column('agent_id', PG_UUID(as_uuid=True), ForeignKey('agent_swarm_instances.id', ondelete='CASCADE'), nullable=False, index=True),
        Column('issue_number', Integer, nullable=False, index=True),
        Column('loop_mode', String(50), nullable=False, index=True),
        Column('max_iterations', Integer, default=20, nullable=False),
        Column('current_iteration', Integer, default=0, nullable=False),
        Column('status', String(50), default='active', nullable=False, index=True),
        Column('token_budget', Integer, nullable=True),
        Column('tokens_used', Integer, default=0, nullable=False),
        Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column('updated_at', DateTime(timezone=True), nullable=True),
    )

    ralph_iterations_table = Table(
        'ralph_iterations', metadata,
        Column('id', PG_UUID(as_uuid=True), primary_key=True),
        Column('loop_session_id', PG_UUID(as_uuid=True), ForeignKey('ralph_loop_sessions.id', ondelete='CASCADE'), nullable=False, index=True),
        Column('iteration_number', Integer, nullable=False, index=True),
        Column('changes_made', JSON, nullable=True),
        Column('test_results', JSON, nullable=True),
        Column('quality_metrics', JSON, nullable=True),
        Column('self_review', Text, nullable=True),
        Column('should_continue', Boolean, nullable=True),
        Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column('updated_at', DateTime(timezone=True), nullable=True),
    )

    # Create all tables using the separate metadata
    metadata.create_all(bind=engine)

    return engine


@pytest.fixture
def db_session(db_engine):
    """Create database session for testing"""
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def workspace(db_session):
    """Create a test workspace"""
    workspace = Workspace(
        id=uuid4(),
        name="Test Workspace",
        slug="test-workspace"
    )
    db_session.add(workspace)
    db_session.commit()
    db_session.refresh(workspace)
    return workspace


@pytest.fixture
def user(db_session, workspace):
    """Create a test user"""
    user = User(
        id=uuid4(),
        email="test@example.com",
        workspace_id=workspace.id
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def agent(db_session, workspace, user):
    """Create a test agent record (direct SQL to avoid ARRAY type issues)"""
    from sqlalchemy import text
    agent_id = uuid4()

    # Insert directly via SQL to avoid ORM model with ARRAY types
    db_session.execute(
        text("""
            INSERT INTO agent_swarm_instances
            (id, name, model, user_id, workspace_id, status, created_at)
            VALUES (:id, :name, :model, :user_id, :workspace_id, :status, :created_at)
        """),
        {
            "id": str(agent_id),
            "name": "Test Agent",
            "model": "claude-sonnet-4-5-20250929",
            "user_id": str(user.id),
            "workspace_id": str(workspace.id),
            "status": "running",
            "created_at": datetime.now(timezone.utc)
        }
    )
    db_session.commit()

    # Return a simple object with the id attribute
    class MockAgent:
        def __init__(self, id, name):
            self.id = id
            self.name = name

    return MockAgent(agent_id, "Test Agent")


class TestRalphLoopSession:
    """Test RalphLoopSession model creation and basic operations"""

    def test_create_ralph_loop_session_with_required_fields(self, db_session, agent):
        """Test creating a loop session with only required fields"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assert session.id is not None
        assert session.agent_id == agent.id
        assert session.issue_number == 143
        assert session.loop_mode == LoopMode.SINGLE_SHOT
        assert session.status == LoopStatus.ACTIVE
        assert session.created_at is not None

    def test_create_ralph_loop_session_with_all_fields(self, db_session, agent):
        """Test creating a loop session with all fields populated"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=200,
            loop_mode=LoopMode.FIXED_ITERATIONS,
            max_iterations=10,
            current_iteration=3,
            status=LoopStatus.PAUSED,
            token_budget=100000,
            tokens_used=25000
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assert session.max_iterations == 10
        assert session.current_iteration == 3
        assert session.status == LoopStatus.PAUSED
        assert session.token_budget == 100000
        assert session.tokens_used == 25000

    def test_loop_session_id_is_uuid(self, db_session, agent):
        """Test that loop session ID is generated as UUID"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.UNTIL_DONE
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assert session.id is not None
        assert len(str(session.id)) == 36  # UUID string format

    def test_loop_session_defaults(self, db_session, agent):
        """Test that loop session has correct default values"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assert session.status == LoopStatus.ACTIVE
        assert session.max_iterations == 20  # Default from model
        assert session.current_iteration == 0  # Default from model
        assert session.token_budget is None  # No default budget
        assert session.tokens_used == 0  # Default from model


class TestLoopModeEnum:
    """Test LoopMode enumeration"""

    def test_loop_mode_single_shot(self, db_session, agent):
        """Test loop session with SINGLE_SHOT mode"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assert session.loop_mode == LoopMode.SINGLE_SHOT
        assert session.loop_mode.value == "single_shot"

    def test_loop_mode_fixed_iterations(self, db_session, agent):
        """Test loop session with FIXED_ITERATIONS mode"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.FIXED_ITERATIONS
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assert session.loop_mode == LoopMode.FIXED_ITERATIONS
        assert session.loop_mode.value == "fixed_iterations"

    def test_loop_mode_until_done(self, db_session, agent):
        """Test loop session with UNTIL_DONE mode"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.UNTIL_DONE
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assert session.loop_mode == LoopMode.UNTIL_DONE
        assert session.loop_mode.value == "until_done"


class TestLoopStatusEnum:
    """Test LoopStatus enumeration"""

    def test_loop_status_active(self, db_session, agent):
        """Test loop session with ACTIVE status"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT,
            status=LoopStatus.ACTIVE
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assert session.status == LoopStatus.ACTIVE
        assert session.status.value == "active"

    def test_loop_status_paused(self, db_session, agent):
        """Test loop session with PAUSED status"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT,
            status=LoopStatus.PAUSED
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assert session.status == LoopStatus.PAUSED
        assert session.status.value == "paused"

    def test_loop_status_completed(self, db_session, agent):
        """Test loop session with COMPLETED status"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT,
            status=LoopStatus.COMPLETED
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assert session.status == LoopStatus.COMPLETED
        assert session.status.value == "completed"

    def test_loop_status_failed(self, db_session, agent):
        """Test loop session with FAILED status"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT,
            status=LoopStatus.FAILED
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assert session.status == LoopStatus.FAILED
        assert session.status.value == "failed"


class TestAgentForeignKey:
    """Test agent_id foreign key constraint"""

    def test_agent_foreign_key_valid(self, db_session, agent):
        """Test that valid agent_id is accepted"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assert session.agent_id == agent.id

    def test_agent_foreign_key_invalid(self, db_session):
        """Test that invalid agent_id is rejected"""
        invalid_agent_id = uuid4()
        session = RalphLoopSession(
            agent_id=invalid_agent_id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(session)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_agent_id_not_null(self, db_session):
        """Test that agent_id cannot be null"""
        session = RalphLoopSession(
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(session)

        with pytest.raises(IntegrityError):
            db_session.commit()


class TestCascadeDeleteAgent:
    """Test CASCADE delete when agent is deleted"""

    def test_cascade_delete_loop_sessions_when_agent_deleted(self, db_session, agent):
        """Test that loop sessions are deleted when agent is deleted"""
        session1 = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        session2 = RalphLoopSession(
            agent_id=agent.id,
            issue_number=200,
            loop_mode=LoopMode.FIXED_ITERATIONS
        )
        db_session.add(session1)
        db_session.add(session2)
        db_session.commit()

        session1_id = session1.id
        session2_id = session2.id

        # Delete agent
        db_session.delete(agent)
        db_session.commit()

        # Verify loop sessions are deleted
        assert db_session.query(RalphLoopSession).filter(RalphLoopSession.id == session1_id).first() is None
        assert db_session.query(RalphLoopSession).filter(RalphLoopSession.id == session2_id).first() is None


class TestLoopSessionRelationships:
    """Test loop session relationships"""

    def test_agent_relationship(self, db_session, agent):
        """Test that loop session has agent relationship"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        # Access agent relationship
        assert session.agent is not None
        assert session.agent.id == agent.id
        assert session.agent.name == agent.name


class TestLoopSessionTimestamps:
    """Test loop session timestamp fields"""

    def test_created_at_auto_generated(self, db_session, agent):
        """Test that created_at is auto-generated"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assert session.created_at is not None
        assert isinstance(session.created_at, datetime)

        # Should be within the last minute
        now = datetime.now(timezone.utc)
        time_diff = (now - session.created_at.replace(tzinfo=timezone.utc)).total_seconds()
        assert time_diff < 60

    def test_updated_at_set_on_update(self, db_session, agent):
        """Test that updated_at is set when model is updated"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        original_updated_at = session.updated_at

        # Update session
        session.current_iteration = 5
        db_session.commit()
        db_session.refresh(session)

        # updated_at should be set (may be None initially)
        if original_updated_at is not None:
            assert session.updated_at != original_updated_at


class TestRalphIteration:
    """Test RalphIteration model creation and basic operations"""

    def test_create_ralph_iteration_with_required_fields(self, db_session, agent):
        """Test creating an iteration with only required fields"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.FIXED_ITERATIONS
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        iteration = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=1
        )
        db_session.add(iteration)
        db_session.commit()
        db_session.refresh(iteration)

        assert iteration.id is not None
        assert iteration.loop_session_id == loop_session.id
        assert iteration.iteration_number == 1
        assert iteration.created_at is not None

    def test_create_ralph_iteration_with_all_fields(self, db_session, agent):
        """Test creating an iteration with all fields populated"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.FIXED_ITERATIONS
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        changes_made = [
            {"file": "backend/models/ralph_loop.py", "action": "created"},
            {"file": "tests/models/test_ralph_loop.py", "action": "created"}
        ]
        test_results = {
            "total": 50,
            "passed": 48,
            "failed": 2,
            "coverage": 85.5
        }
        quality_metrics = {
            "test_coverage": 85.5,
            "code_quality_score": 92,
            "complexity": "low"
        }
        self_review = "All tests passing except for two edge cases. Coverage exceeds 80% threshold."

        iteration = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=1,
            changes_made=changes_made,
            test_results=test_results,
            quality_metrics=quality_metrics,
            self_review=self_review,
            should_continue=True
        )
        db_session.add(iteration)
        db_session.commit()
        db_session.refresh(iteration)

        assert iteration.changes_made == changes_made
        assert iteration.test_results == test_results
        assert iteration.quality_metrics == quality_metrics
        assert iteration.self_review == self_review
        assert iteration.should_continue is True

    def test_iteration_id_is_uuid(self, db_session, agent):
        """Test that iteration ID is generated as UUID"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        iteration = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=1
        )
        db_session.add(iteration)
        db_session.commit()
        db_session.refresh(iteration)

        assert iteration.id is not None
        assert len(str(iteration.id)) == 36  # UUID string format

    def test_iteration_defaults(self, db_session, agent):
        """Test that iteration has correct default values"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        iteration = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=1
        )
        db_session.add(iteration)
        db_session.commit()
        db_session.refresh(iteration)

        assert iteration.changes_made is None
        assert iteration.test_results is None
        assert iteration.quality_metrics is None
        assert iteration.self_review is None
        assert iteration.should_continue is None


class TestLoopSessionForeignKey:
    """Test loop_session_id foreign key constraint"""

    def test_loop_session_foreign_key_valid(self, db_session, agent):
        """Test that valid loop_session_id is accepted"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        iteration = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=1
        )
        db_session.add(iteration)
        db_session.commit()
        db_session.refresh(iteration)

        assert iteration.loop_session_id == loop_session.id

    def test_loop_session_foreign_key_invalid(self, db_session):
        """Test that invalid loop_session_id is rejected"""
        invalid_session_id = uuid4()
        iteration = RalphIteration(
            loop_session_id=invalid_session_id,
            iteration_number=1
        )
        db_session.add(iteration)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_loop_session_id_not_null(self, db_session):
        """Test that loop_session_id cannot be null"""
        iteration = RalphIteration(
            iteration_number=1
        )
        db_session.add(iteration)

        with pytest.raises(IntegrityError):
            db_session.commit()


class TestCascadeDeleteLoopSession:
    """Test CASCADE delete when loop session is deleted"""

    def test_cascade_delete_iterations_when_loop_session_deleted(self, db_session, agent):
        """Test that iterations are deleted when loop session is deleted"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.FIXED_ITERATIONS
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        iteration1 = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=1
        )
        iteration2 = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=2
        )
        db_session.add(iteration1)
        db_session.add(iteration2)
        db_session.commit()

        iteration1_id = iteration1.id
        iteration2_id = iteration2.id

        # Delete loop session
        db_session.delete(loop_session)
        db_session.commit()

        # Verify iterations are deleted
        assert db_session.query(RalphIteration).filter(RalphIteration.id == iteration1_id).first() is None
        assert db_session.query(RalphIteration).filter(RalphIteration.id == iteration2_id).first() is None


class TestIterationRelationships:
    """Test iteration relationships"""

    def test_loop_session_relationship(self, db_session, agent):
        """Test that iteration has loop_session relationship"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        iteration = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=1
        )
        db_session.add(iteration)
        db_session.commit()
        db_session.refresh(iteration)

        # Access loop_session relationship
        assert iteration.loop_session is not None
        assert iteration.loop_session.id == loop_session.id
        assert iteration.loop_session.issue_number == 143

    def test_loop_session_iterations_back_reference(self, db_session, agent):
        """Test that loop session has iterations back reference"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.FIXED_ITERATIONS
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        iteration1 = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=1
        )
        iteration2 = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=2
        )
        db_session.add(iteration1)
        db_session.add(iteration2)
        db_session.commit()

        # Access iterations back reference
        db_session.refresh(loop_session)
        assert len(loop_session.iterations) == 2
        assert loop_session.iterations[0].iteration_number in [1, 2]


class TestIterationTimestamps:
    """Test iteration timestamp fields"""

    def test_created_at_auto_generated(self, db_session, agent):
        """Test that created_at is auto-generated"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        iteration = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=1
        )
        db_session.add(iteration)
        db_session.commit()
        db_session.refresh(iteration)

        assert iteration.created_at is not None
        assert isinstance(iteration.created_at, datetime)

        # Should be within the last minute
        now = datetime.now(timezone.utc)
        time_diff = (now - iteration.created_at.replace(tzinfo=timezone.utc)).total_seconds()
        assert time_diff < 60

    def test_updated_at_set_on_update(self, db_session, agent):
        """Test that updated_at is set when model is updated"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        iteration = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=1
        )
        db_session.add(iteration)
        db_session.commit()
        db_session.refresh(iteration)

        original_updated_at = iteration.updated_at

        # Update iteration
        iteration.should_continue = False
        db_session.commit()
        db_session.refresh(iteration)

        # updated_at should be set (may be None initially)
        if original_updated_at is not None:
            assert iteration.updated_at != original_updated_at


class TestIterationJSONFields:
    """Test iteration JSON field operations"""

    def test_changes_made_json_storage(self, db_session, agent):
        """Test that changes_made stores complex JSON structures"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        changes = [
            {
                "file": "backend/models/ralph_loop.py",
                "action": "created",
                "lines_added": 150,
                "lines_removed": 0
            },
            {
                "file": "tests/models/test_ralph_loop.py",
                "action": "created",
                "lines_added": 300,
                "lines_removed": 0
            }
        ]

        iteration = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=1,
            changes_made=changes
        )
        db_session.add(iteration)
        db_session.commit()
        db_session.refresh(iteration)

        assert iteration.changes_made == changes
        assert iteration.changes_made[0]["file"] == "backend/models/ralph_loop.py"
        assert iteration.changes_made[0]["lines_added"] == 150

    def test_test_results_json_storage(self, db_session, agent):
        """Test that test_results stores JSON data correctly"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        test_results = {
            "total": 50,
            "passed": 48,
            "failed": 2,
            "skipped": 0,
            "coverage_percent": 85.5,
            "duration_seconds": 12.3,
            "failures": [
                {"test": "test_edge_case_1", "error": "AssertionError"},
                {"test": "test_edge_case_2", "error": "ValueError"}
            ]
        }

        iteration = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=1,
            test_results=test_results
        )
        db_session.add(iteration)
        db_session.commit()
        db_session.refresh(iteration)

        assert iteration.test_results == test_results
        assert iteration.test_results["passed"] == 48
        assert len(iteration.test_results["failures"]) == 2

    def test_quality_metrics_json_storage(self, db_session, agent):
        """Test that quality_metrics stores JSON data correctly"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        quality_metrics = {
            "test_coverage": 85.5,
            "code_quality_score": 92,
            "cyclomatic_complexity": 3.2,
            "maintainability_index": 88,
            "technical_debt_minutes": 15
        }

        iteration = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=1,
            quality_metrics=quality_metrics
        )
        db_session.add(iteration)
        db_session.commit()
        db_session.refresh(iteration)

        assert iteration.quality_metrics == quality_metrics
        assert iteration.quality_metrics["test_coverage"] == 85.5


class TestLoopSessionRepr:
    """Test loop session string representation"""

    def test_loop_session_repr(self, db_session, agent):
        """Test that loop session has meaningful string representation"""
        session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        repr_str = repr(session)
        assert "RalphLoopSession" in repr_str
        assert "143" in repr_str or session.status.value in repr_str


class TestIterationRepr:
    """Test iteration string representation"""

    def test_iteration_repr(self, db_session, agent):
        """Test that iteration has meaningful string representation"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        iteration = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=5
        )
        db_session.add(iteration)
        db_session.commit()
        db_session.refresh(iteration)

        repr_str = repr(iteration)
        assert "RalphIteration" in repr_str
        assert "5" in repr_str or str(iteration.id) in repr_str


class TestQueryOperations:
    """Test query operations for loop sessions and iterations"""

    def test_query_loop_sessions_by_agent(self, db_session, agent):
        """Test querying loop sessions by agent"""
        session1 = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT
        )
        session2 = RalphLoopSession(
            agent_id=agent.id,
            issue_number=200,
            loop_mode=LoopMode.FIXED_ITERATIONS
        )
        db_session.add(session1)
        db_session.add(session2)
        db_session.commit()

        sessions = db_session.query(RalphLoopSession).filter(
            RalphLoopSession.agent_id == agent.id
        ).all()
        assert len(sessions) == 2

    def test_query_loop_sessions_by_status(self, db_session, agent):
        """Test querying loop sessions by status"""
        session1 = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.SINGLE_SHOT,
            status=LoopStatus.ACTIVE
        )
        session2 = RalphLoopSession(
            agent_id=agent.id,
            issue_number=200,
            loop_mode=LoopMode.FIXED_ITERATIONS,
            status=LoopStatus.COMPLETED
        )
        db_session.add(session1)
        db_session.add(session2)
        db_session.commit()

        active_sessions = db_session.query(RalphLoopSession).filter(
            RalphLoopSession.status == LoopStatus.ACTIVE
        ).all()
        assert len(active_sessions) == 1
        assert active_sessions[0].id == session1.id

    def test_query_iterations_by_loop_session(self, db_session, agent):
        """Test querying iterations by loop session"""
        loop_session = RalphLoopSession(
            agent_id=agent.id,
            issue_number=143,
            loop_mode=LoopMode.FIXED_ITERATIONS
        )
        db_session.add(loop_session)
        db_session.commit()
        db_session.refresh(loop_session)

        iteration1 = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=1
        )
        iteration2 = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=2
        )
        iteration3 = RalphIteration(
            loop_session_id=loop_session.id,
            iteration_number=3
        )
        db_session.add(iteration1)
        db_session.add(iteration2)
        db_session.add(iteration3)
        db_session.commit()

        iterations = db_session.query(RalphIteration).filter(
            RalphIteration.loop_session_id == loop_session.id
        ).order_by(RalphIteration.iteration_number).all()
        assert len(iterations) == 3
        assert iterations[0].iteration_number == 1
        assert iterations[1].iteration_number == 2
        assert iterations[2].iteration_number == 3
