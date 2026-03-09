"""
Shared fixtures for chat persistence integration tests

Provides:
- Async database session with all tables
- Mock ZeroDB client with realistic responses
- FastAPI test client with dependency overrides
- Sample data factories for workspaces, users, and agents
"""

import pytest
import pytest_asyncio
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4, UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from backend.db.base_class import Base
from backend.models.workspace import Workspace
from backend.models.user import User
from backend.models.agent_swarm_lifecycle import AgentSwarmInstance, AgentSwarmStatus
from backend.models.conversation import Conversation, ConversationStatus
from backend.integrations.zerodb_client import ZeroDBClient


@pytest.fixture(scope="function")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Create an event loop for async tests.

    Function-scoped to ensure clean state between tests.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    """
    Create async SQLite engine for testing.

    Uses in-memory database with StaticPool for connection reuse.
    Note: Only creates tables compatible with SQLite (excludes tables with ARRAY types).
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )

    # Create only tables compatible with SQLite (exclude agent_swarm_instances with ARRAY)
    async with engine.begin() as conn:
        # Create tables individually, skipping those with ARRAY types
        from backend.models.workspace import Workspace
        from backend.models.user import User
        from backend.models.conversation import Conversation

        await conn.run_sync(lambda conn: Workspace.__table__.create(conn, checkfirst=True))
        await conn.run_sync(lambda conn: User.__table__.create(conn, checkfirst=True))

        # Create agent table with ARRAY columns excluded for SQLite
        # Use raw SQL instead of SQLAlchemy Table to avoid metadata conflicts
        def create_agent_table(conn):
            conn.execute(sqlalchemy.text("""
                CREATE TABLE IF NOT EXISTS agent_swarm_instances (
                    id TEXT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    persona TEXT,
                    model VARCHAR(255) NOT NULL,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
                    status VARCHAR(50) DEFAULT 'provisioning' NOT NULL,
                    openclaw_session_key VARCHAR(255) UNIQUE,
                    openclaw_agent_id VARCHAR(255),
                    heartbeat_enabled BOOLEAN DEFAULT 0 NOT NULL,
                    heartbeat_interval VARCHAR(50),
                    heartbeat_checklist TEXT,
                    last_heartbeat_at TIMESTAMP,
                    next_heartbeat_at TIMESTAMP,
                    configuration TEXT,
                    error_message TEXT,
                    error_count INTEGER DEFAULT 0 NOT NULL,
                    last_error_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    provisioned_at TIMESTAMP,
                    paused_at TIMESTAMP,
                    stopped_at TIMESTAMP
                )
            """))

        import sqlalchemy
        await conn.run_sync(create_agent_table)
        await conn.run_sync(lambda conn: Conversation.__table__.create(conn, checkfirst=True))

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        def drop_tables(conn):
            conn.execute(sqlalchemy.text("DROP TABLE IF EXISTS conversations"))
            conn.execute(sqlalchemy.text("DROP TABLE IF EXISTS agent_swarm_instances"))
            conn.execute(sqlalchemy.text("DROP TABLE IF EXISTS users"))
            conn.execute(sqlalchemy.text("DROP TABLE IF EXISTS workspaces"))

        await conn.run_sync(drop_tables)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create async database session for tests.

    Provides a fresh session for each test with automatic rollback.
    """
    async_session_maker = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture
def zerodb_client_mock() -> MagicMock:
    """
    Create mock ZeroDBClient with realistic responses.

    Mocks all ZeroDB operations:
    - Project creation
    - Table creation
    - Row insertion (messages)
    - Memory creation (semantic search)
    - Table queries (pagination)
    - Memory search (semantic search)
    """
    mock = MagicMock(spec=ZeroDBClient)

    # Mock async context manager
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)

    # Mock project creation
    mock.create_project = AsyncMock(return_value={
        "id": "test_proj_123",
        "name": "Test Project",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    # Mock table creation
    mock.create_table = AsyncMock(return_value={
        "id": "table_messages",
        "project_id": "test_proj_123",
        "table_name": "messages",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    # Mock row insertion (messages) - returns incremental IDs
    row_counter = {"count": 0}

    def create_row_side_effect(project_id, table_name, row_data):
        row_counter["count"] += 1
        return {
            "id": f"msg_{row_counter['count']:03d}",
            "project_id": project_id,
            "table_name": table_name,
            "data": row_data,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

    mock.create_table_row = AsyncMock(side_effect=create_row_side_effect)

    # Mock memory creation
    memory_counter = {"count": 0}

    def create_memory_side_effect(title, content, type, tags, metadata):
        memory_counter["count"] += 1
        return {
            "id": f"mem_{memory_counter['count']:03d}",
            "title": title,
            "content": content,
            "type": type,
            "tags": tags,
            "metadata": metadata,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

    mock.create_memory = AsyncMock(side_effect=create_memory_side_effect)

    # Mock table query (pagination)
    stored_rows = []

    def query_table_side_effect(project_id, table_name, limit=10, skip=0):
        return stored_rows[skip:skip + limit]

    mock.query_table = AsyncMock(side_effect=query_table_side_effect)

    # Store rows for query testing
    mock._stored_rows = stored_rows

    # Mock memory search
    stored_memories = []

    def search_memories_side_effect(query, limit=10, type=None):
        filtered = stored_memories
        if type:
            filtered = [m for m in filtered if m.get("type") == type]

        # Add similarity scores
        results = [
            {**m, "score": 0.95 - (i * 0.1)}
            for i, m in enumerate(filtered[:limit])
        ]

        return {
            "results": results,
            "total": len(results),
            "query": query
        }

    mock.search_memories = AsyncMock(side_effect=search_memories_side_effect)

    # Store memories for search testing
    mock._stored_memories = stored_memories

    return mock


@pytest_asyncio.fixture
async def sample_workspace(db: AsyncSession) -> Workspace:
    """Create a sample workspace with ZeroDB project ID."""
    workspace = Workspace(
        id=uuid4(),
        name="Test Workspace",
        slug="test-workspace",
        description="Test workspace for integration tests",
        zerodb_project_id="test_proj_123"
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    return workspace


@pytest_asyncio.fixture
async def sample_user(db: AsyncSession, sample_workspace: Workspace) -> User:
    """Create a sample user in the workspace."""
    user = User(
        id=uuid4(),
        email="test@example.com",
        workspace_id=sample_workspace.id
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def sample_agent(
    db: AsyncSession,
    sample_workspace: Workspace,
    sample_user: User
) -> AgentSwarmInstance:
    """Create a sample agent in the workspace."""
    agent = AgentSwarmInstance(
        id=uuid4(),
        name="Test Agent",
        persona="Helpful assistant",
        model="claude-3-5-sonnet-20241022",
        user_id=sample_user.id,
        workspace_id=sample_workspace.id,
        status=AgentSwarmStatus.RUNNING,
        openclaw_session_key="whatsapp:test:session123",
        openclaw_agent_id="agent_test_001"
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


@pytest_asyncio.fixture
async def sample_conversation(
    db: AsyncSession,
    sample_workspace: Workspace,
    sample_agent: AgentSwarmInstance,
    sample_user: User
) -> Conversation:
    """Create a sample conversation."""
    conversation = Conversation(
        id=uuid4(),
        workspace_id=sample_workspace.id,
        agent_id=sample_agent.id,
        user_id=sample_user.id,
        openclaw_session_key="whatsapp:test:session123",
        zerodb_table_name="messages",
        status=ConversationStatus.ACTIVE,
        message_count=0
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@pytest.fixture
def fastapi_test_client(db: AsyncSession, zerodb_client_mock: MagicMock):
    """
    Create FastAPI test client with dependency overrides.

    Overrides:
    - Database session (uses test db)
    - ZeroDB client (uses mock)
    """
    from backend.main import app
    from backend.db.base import get_db

    # Override database dependency
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    # Create test client
    client = TestClient(app)

    yield client

    # Clean up overrides
    app.dependency_overrides.clear()


# ============================================================================
# Additional Fixtures for E2E Integration Tests (Issue #109)
# ============================================================================


@pytest_asyncio.fixture
async def multiple_users(db: AsyncSession, sample_workspace: Workspace):
    """
    Create multiple users for multi-user isolation tests.

    Returns list of 5 users in the same workspace.
    """
    users = []
    for i in range(5):
        user = User(
            id=uuid4(),
            email=f"user{i}@example.com",
            workspace_id=sample_workspace.id
        )
        db.add(user)
        users.append(user)

    await db.commit()

    for user in users:
        await db.refresh(user)

    return users


@pytest_asyncio.fixture
async def multiple_workspaces(db: AsyncSession):
    """
    Create multiple workspaces for workspace isolation tests.

    Returns list of 3 workspaces with different ZeroDB projects.
    """
    workspaces = []
    for i in range(3):
        workspace = Workspace(
            id=uuid4(),
            name=f"Test Workspace {i}",
            slug=f"test-workspace-{i}",
            description=f"Workspace {i} for integration tests",
            zerodb_project_id=f"test_proj_{i}"
        )
        db.add(workspace)
        workspaces.append(workspace)

    await db.commit()

    for workspace in workspaces:
        await db.refresh(workspace)

    return workspaces


@pytest_asyncio.fixture
async def multiple_agents(
    db: AsyncSession,
    sample_workspace: Workspace,
    sample_user: User
):
    """
    Create multiple agents for agent switching tests.

    Returns list of 3 agents in the same workspace.
    """
    agents = []
    for i in range(3):
        agent = AgentSwarmInstance(
            id=uuid4(),
            name=f"Test Agent {i}",
            persona=f"Assistant persona {i}",
            model="claude-3-5-sonnet-20241022",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id,
            status=AgentSwarmStatus.RUNNING,
            openclaw_session_key=f"whatsapp:agent{i}:session",
            openclaw_agent_id=f"agent_{i:03d}"
        )
        db.add(agent)
        agents.append(agent)

    await db.commit()

    for agent in agents:
        await db.refresh(agent)

    return agents


@pytest_asyncio.fixture
async def conversation_with_messages(
    db: AsyncSession,
    zerodb_client_mock: MagicMock,
    sample_conversation: Conversation
):
    """
    Create a conversation pre-populated with messages.

    Returns tuple of (conversation, messages_list).
    Useful for testing context loading and pagination.
    """
    from backend.services.conversation_service import ConversationService

    service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

    # Add 20 messages
    messages = []
    for i in range(20):
        msg = await service.add_message(
            conversation_id=sample_conversation.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i}",
            metadata={
                "index": i,
                "timestamp": (datetime.now(timezone.utc) + timedelta(seconds=i)).isoformat()
            }
        )
        messages.append(msg)

    await db.refresh(sample_conversation)

    return sample_conversation, messages


@pytest.fixture
def performance_timer():
    """
    Context manager for performance timing assertions.

    Usage:
        with performance_timer(max_duration=0.5) as timer:
            # code to time
            pass
        assert timer.elapsed < 0.5
    """
    class Timer:
        def __init__(self, max_duration: float = None):
            self.max_duration = max_duration
            self.start_time = None
            self.end_time = None
            self.elapsed = None

        def __enter__(self):
            self.start_time = datetime.now(timezone.utc)
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.end_time = datetime.now(timezone.utc)
            self.elapsed = (self.end_time - self.start_time).total_seconds()

            if self.max_duration and self.elapsed > self.max_duration:
                raise AssertionError(
                    f"Performance test failed: took {self.elapsed:.3f}s, "
                    f"expected < {self.max_duration:.3f}s"
                )

    return Timer


@pytest.fixture
def mock_openclaw_bridge():
    """
    Create a fully configured mock OpenClaw bridge for integration tests.

    Returns mock with common behaviors pre-configured:
    - Connection management
    - Message sending with realistic delays
    - Error injection support
    """
    mock = MagicMock()
    mock.is_connected = True
    mock.connect = AsyncMock()
    mock.disconnect = AsyncMock()

    # Default successful response
    mock.send_to_agent = AsyncMock(return_value={
        "id": f"response_{uuid4().hex[:8]}",
        "result": {
            "response": "Test response from agent",
            "model": "claude-3-5-sonnet-20241022",
            "tokens_used": 100
        }
    })

    # Methods for error injection
    def inject_connection_error():
        mock.is_connected = False
        mock.send_to_agent = AsyncMock(
            side_effect=Exception("Connection lost")
        )

    def inject_timeout_error():
        mock.send_to_agent = AsyncMock(
            side_effect=asyncio.TimeoutError("Request timeout")
        )

    def restore_normal_behavior():
        mock.is_connected = True
        mock.send_to_agent = AsyncMock(return_value={
            "id": f"response_{uuid4().hex[:8]}",
            "result": {
                "response": "Test response from agent",
                "model": "claude-3-5-sonnet-20241022",
                "tokens_used": 100
            }
        })

    mock.inject_connection_error = inject_connection_error
    mock.inject_timeout_error = inject_timeout_error
    mock.restore_normal_behavior = restore_normal_behavior

    return mock


@pytest.fixture
def zerodb_client_with_failures():
    """
    Create ZeroDB client mock with configurable failure modes.

    Supports:
    - Connection failures
    - API errors
    - Partial failures (table write succeeds, memory write fails)
    - Retry simulation
    """
    mock = MagicMock(spec=ZeroDBClient)

    # Counter for retry simulation
    attempt_counter = {"table_row": 0, "memory": 0}

    def reset_counters():
        attempt_counter["table_row"] = 0
        attempt_counter["memory"] = 0

    # Normal behavior
    def create_row_normal(project_id, table_name, row_data):
        attempt_counter["table_row"] += 1
        return {
            "id": f"msg_{attempt_counter['table_row']:03d}",
            "project_id": project_id,
            "table_name": table_name,
            "data": row_data,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

    def create_memory_normal(title, content, type, tags, metadata):
        attempt_counter["memory"] += 1
        return {
            "id": f"mem_{attempt_counter['memory']:03d}",
            "content": content,
            "type": type,
            "tags": tags,
            "metadata": metadata
        }

    # Failure modes
    def fail_after_n_attempts(n: int, operation: str):
        """Configure to fail for first N attempts, then succeed"""
        if operation == "table_row":
            def create_row_with_failures(project_id, table_name, row_data):
                attempt_counter["table_row"] += 1
                if attempt_counter["table_row"] <= n:
                    raise ZeroDBConnectionError(f"Connection failed (attempt {attempt_counter['table_row']})")
                return create_row_normal(project_id, table_name, row_data)

            mock.create_table_row = AsyncMock(side_effect=create_row_with_failures)

        elif operation == "memory":
            def create_memory_with_failures(title, content, type, tags, metadata):
                attempt_counter["memory"] += 1
                if attempt_counter["memory"] <= n:
                    raise ZeroDBAPIError(f"API error (attempt {attempt_counter['memory']})")
                return create_memory_normal(title, content, type, tags, metadata)

            mock.create_memory = AsyncMock(side_effect=create_memory_with_failures)

    def partial_failure_mode():
        """Table write succeeds, memory write fails"""
        mock.create_table_row = AsyncMock(side_effect=create_row_normal)
        mock.create_memory = AsyncMock(side_effect=ZeroDBAPIError("Memory write failed"))

    # Setup default behavior
    mock.create_table_row = AsyncMock(side_effect=create_row_normal)
    mock.create_memory = AsyncMock(side_effect=create_memory_normal)
    mock.query_table = AsyncMock(return_value=[])
    mock.search_memories = AsyncMock(return_value={"results": [], "total": 0})

    # Attach helper methods
    mock.reset_counters = reset_counters
    mock.fail_after_n_attempts = fail_after_n_attempts
    mock.partial_failure_mode = partial_failure_mode

    return mock
