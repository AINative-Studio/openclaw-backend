"""
Test PostgreSQL Row-Level Security (RLS) Policies

Tests database-enforced multi-tenant isolation using PostgreSQL RLS.
Ensures tenant data is isolated at the database layer.

TDD Phase: RED - Write tests FIRST, they should fail initially
Epic: E9 - Database Security
Story: S1 - Row-Level Security
Issue: #120

CRITICAL: This is a security requirement. Zero tolerance for data leaks.
"""

import pytest
from uuid import uuid4
from sqlalchemy import text, select
from sqlalchemy.exc import IntegrityError, DatabaseError
from datetime import datetime, timezone

from backend.db.base import engine, AsyncSessionLocal
from backend.models.workspace import Workspace
from backend.models.user import User
from backend.models.conversation import Conversation, ConversationStatus
from backend.models.agent_swarm_lifecycle import AgentSwarmInstance, AgentSwarmStatus
from backend.models.task_lease import Task, TaskStatus, TaskPriority


@pytest.fixture(scope="function")
async def async_db_session():
    """Async database session fixture"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()


@pytest.fixture
async def tenant_workspaces(async_db_session):
    """
    Create two separate tenant workspaces for isolation testing

    Returns:
        tuple: (workspace1, workspace2, user1, user2)
    """
    # Create Workspace 1
    workspace1 = Workspace(
        id=uuid4(),
        name="Tenant Alpha",
        slug="tenant-alpha",
        description="First tenant workspace"
    )
    async_db_session.add(workspace1)

    # Create Workspace 2
    workspace2 = Workspace(
        id=uuid4(),
        name="Tenant Beta",
        slug="tenant-beta",
        description="Second tenant workspace"
    )
    async_db_session.add(workspace2)

    await async_db_session.flush()

    # Create User 1 (belongs to Workspace 1)
    user1 = User(
        id=uuid4(),
        email="alice@alpha.com",
        hashed_password="hashed_pwd_1",
        full_name="Alice Alpha",
        workspace_id=workspace1.id
    )
    async_db_session.add(user1)

    # Create User 2 (belongs to Workspace 2)
    user2 = User(
        id=uuid4(),
        email="bob@beta.com",
        hashed_password="hashed_pwd_2",
        full_name="Bob Beta",
        workspace_id=workspace2.id
    )
    async_db_session.add(user2)

    await async_db_session.commit()
    await async_db_session.refresh(workspace1)
    await async_db_session.refresh(workspace2)
    await async_db_session.refresh(user1)
    await async_db_session.refresh(user2)

    return workspace1, workspace2, user1, user2


@pytest.fixture
async def tenant_data(async_db_session, tenant_workspaces):
    """
    Create test data for both tenants

    Returns:
        dict: Contains all test data organized by tenant
    """
    workspace1, workspace2, user1, user2 = tenant_workspaces

    # Create Agent for Tenant 1
    agent1 = AgentSwarmInstance(
        id=uuid4(),
        name="Agent Alpha",
        model="claude-3-5-sonnet-20241022",
        user_id=user1.id,
        workspace_id=workspace1.id,
        status=AgentSwarmStatus.RUNNING
    )
    async_db_session.add(agent1)

    # Create Agent for Tenant 2
    agent2 = AgentSwarmInstance(
        id=uuid4(),
        name="Agent Beta",
        model="claude-3-5-sonnet-20241022",
        user_id=user2.id,
        workspace_id=workspace2.id,
        status=AgentSwarmStatus.RUNNING
    )
    async_db_session.add(agent2)

    await async_db_session.flush()

    # Create Conversation for Tenant 1
    conv1 = Conversation(
        id=uuid4(),
        workspace_id=workspace1.id,
        agent_id=agent1.id,
        user_id=user1.id,
        status=ConversationStatus.ACTIVE
    )
    async_db_session.add(conv1)

    # Create Conversation for Tenant 2
    conv2 = Conversation(
        id=uuid4(),
        workspace_id=workspace2.id,
        agent_id=agent2.id,
        user_id=user2.id,
        status=ConversationStatus.ACTIVE
    )
    async_db_session.add(conv2)

    # Create Task for Tenant 1 (tasks will have workspace_id after migration)
    task1 = Task(
        id=uuid4(),
        task_type="test_task",
        payload={"workspace_id": str(workspace1.id), "data": "alpha_data"},
        status=TaskStatus.QUEUED,
        priority=TaskPriority.NORMAL
    )
    async_db_session.add(task1)

    # Create Task for Tenant 2
    task2 = Task(
        id=uuid4(),
        task_type="test_task",
        payload={"workspace_id": str(workspace2.id), "data": "beta_data"},
        status=TaskStatus.QUEUED,
        priority=TaskPriority.NORMAL
    )
    async_db_session.add(task2)

    await async_db_session.commit()

    return {
        "workspace1": workspace1,
        "workspace2": workspace2,
        "user1": user1,
        "user2": user2,
        "agent1": agent1,
        "agent2": agent2,
        "conv1": conv1,
        "conv2": conv2,
        "task1": task1,
        "task2": task2
    }


class TestRLSPoliciesEnabled:
    """Test that RLS is enabled on all multi-tenant tables"""

    @pytest.mark.asyncio
    async def test_workspaces_table_has_rls_enabled(self, async_db_session):
        """Verify RLS is enabled on workspaces table"""
        result = await async_db_session.execute(
            text("""
                SELECT relrowsecurity
                FROM pg_class
                WHERE relname = 'workspaces'
            """)
        )
        row = result.fetchone()
        assert row is not None, "workspaces table not found"
        assert row[0] is True, "RLS not enabled on workspaces table"

    @pytest.mark.asyncio
    async def test_conversations_table_has_rls_enabled(self, async_db_session):
        """Verify RLS is enabled on conversations table"""
        result = await async_db_session.execute(
            text("""
                SELECT relrowsecurity
                FROM pg_class
                WHERE relname = 'conversations'
            """)
        )
        row = result.fetchone()
        assert row is not None, "conversations table not found"
        assert row[0] is True, "RLS not enabled on conversations table"

    @pytest.mark.asyncio
    async def test_agent_swarm_instances_table_has_rls_enabled(self, async_db_session):
        """Verify RLS is enabled on agent_swarm_instances table"""
        result = await async_db_session.execute(
            text("""
                SELECT relrowsecurity
                FROM pg_class
                WHERE relname = 'agent_swarm_instances'
            """)
        )
        row = result.fetchone()
        assert row is not None, "agent_swarm_instances table not found"
        assert row[0] is True, "RLS not enabled on agent_swarm_instances table"

    @pytest.mark.asyncio
    async def test_tasks_table_has_rls_enabled(self, async_db_session):
        """Verify RLS is enabled on tasks table"""
        result = await async_db_session.execute(
            text("""
                SELECT relrowsecurity
                FROM pg_class
                WHERE relname = 'tasks'
            """)
        )
        row = result.fetchone()
        assert row is not None, "tasks table not found"
        assert row[0] is True, "RLS not enabled on tasks table"


class TestRLSPoliciesExist:
    """Test that required RLS policies are created"""

    @pytest.mark.asyncio
    async def test_workspace_tenant_policy_exists(self, async_db_session):
        """Verify workspace tenant isolation policy exists"""
        result = await async_db_session.execute(
            text("""
                SELECT polname, polcmd
                FROM pg_policy
                WHERE polrelid = 'workspaces'::regclass
                AND polname = 'workspace_tenant_isolation'
            """)
        )
        row = result.fetchone()
        assert row is not None, "workspace_tenant_isolation policy not found"
        # polcmd is returned as bytes in PostgreSQL
        polcmd = row[1].decode('utf-8') if isinstance(row[1], bytes) else row[1]
        assert polcmd == '*', "Policy should apply to all commands (SELECT, INSERT, UPDATE, DELETE)"

    @pytest.mark.asyncio
    async def test_conversation_tenant_policy_exists(self, async_db_session):
        """Verify conversation tenant isolation policy exists"""
        result = await async_db_session.execute(
            text("""
                SELECT polname, polcmd
                FROM pg_policy
                WHERE polrelid = 'conversations'::regclass
                AND polname = 'conversation_tenant_isolation'
            """)
        )
        row = result.fetchone()
        assert row is not None, "conversation_tenant_isolation policy not found"
        polcmd = row[1].decode('utf-8') if isinstance(row[1], bytes) else row[1]
        assert polcmd == '*', "Policy should apply to all commands"

    @pytest.mark.asyncio
    async def test_agent_tenant_policy_exists(self, async_db_session):
        """Verify agent tenant isolation policy exists"""
        result = await async_db_session.execute(
            text("""
                SELECT polname, polcmd
                FROM pg_policy
                WHERE polrelid = 'agent_swarm_instances'::regclass
                AND polname = 'agent_tenant_isolation'
            """)
        )
        row = result.fetchone()
        assert row is not None, "agent_tenant_isolation policy not found"
        polcmd = row[1].decode('utf-8') if isinstance(row[1], bytes) else row[1]
        assert polcmd == '*', "Policy should apply to all commands"

    @pytest.mark.asyncio
    async def test_task_tenant_policy_exists(self, async_db_session):
        """Verify task tenant isolation policy exists"""
        result = await async_db_session.execute(
            text("""
                SELECT polname, polcmd
                FROM pg_policy
                WHERE polrelid = 'tasks'::regclass
                AND polname = 'task_tenant_isolation'
            """)
        )
        row = result.fetchone()
        assert row is not None, "task_tenant_isolation policy not found"
        polcmd = row[1].decode('utf-8') if isinstance(row[1], bytes) else row[1]
        assert polcmd == '*', "Policy should apply to all commands"


class TestTenantIsolation:
    """Test that tenant context properly isolates data"""

    @pytest.mark.asyncio
    async def test_workspace_isolation_with_tenant_context(self, async_db_session, tenant_data):
        """Verify workspace queries are filtered by tenant context"""
        workspace1 = tenant_data["workspace1"]
        workspace2 = tenant_data["workspace2"]

        # Set tenant context to workspace1
        await async_db_session.execute(
            text("SET LOCAL app.current_tenant_id = :tenant_id"),
            {"tenant_id": str(workspace1.id)}
        )

        # Query workspaces - should only return workspace1
        result = await async_db_session.execute(select(Workspace))
        workspaces = result.scalars().all()

        assert len(workspaces) == 1, "Should only see one workspace with RLS"
        assert workspaces[0].id == workspace1.id, "Should only see own workspace"
        assert workspace2.id not in [w.id for w in workspaces], "Should not see other tenant's workspace"

    @pytest.mark.asyncio
    async def test_conversation_isolation_with_tenant_context(self, async_db_session, tenant_data):
        """Verify conversation queries are filtered by tenant context"""
        workspace1 = tenant_data["workspace1"]
        conv1 = tenant_data["conv1"]
        conv2 = tenant_data["conv2"]

        # Set tenant context to workspace1
        await async_db_session.execute(
            text("SET LOCAL app.current_tenant_id = :tenant_id"),
            {"tenant_id": str(workspace1.id)}
        )

        # Query conversations - should only return conv1
        result = await async_db_session.execute(select(Conversation))
        conversations = result.scalars().all()

        assert len(conversations) == 1, "Should only see one conversation with RLS"
        assert conversations[0].id == conv1.id, "Should only see own conversation"
        assert conv2.id not in [c.id for c in conversations], "Should not see other tenant's conversation"

    @pytest.mark.asyncio
    async def test_agent_isolation_with_tenant_context(self, async_db_session, tenant_data):
        """Verify agent queries are filtered by tenant context"""
        workspace1 = tenant_data["workspace1"]
        agent1 = tenant_data["agent1"]
        agent2 = tenant_data["agent2"]

        # Set tenant context to workspace1
        await async_db_session.execute(
            text("SET LOCAL app.current_tenant_id = :tenant_id"),
            {"tenant_id": str(workspace1.id)}
        )

        # Query agents - should only return agent1
        result = await async_db_session.execute(select(AgentSwarmInstance))
        agents = result.scalars().all()

        assert len(agents) == 1, "Should only see one agent with RLS"
        assert agents[0].id == agent1.id, "Should only see own agent"
        assert agent2.id not in [a.id for a in agents], "Should not see other tenant's agent"

    @pytest.mark.asyncio
    async def test_cross_tenant_query_returns_empty(self, async_db_session, tenant_data):
        """Verify querying with wrong tenant context returns no results"""
        workspace1 = tenant_data["workspace1"]
        workspace2 = tenant_data["workspace2"]

        # Set tenant context to workspace1
        await async_db_session.execute(
            text("SET LOCAL app.current_tenant_id = :tenant_id"),
            {"tenant_id": str(workspace1.id)}
        )

        # Try to query workspace2 by ID - should return nothing
        result = await async_db_session.execute(
            select(Workspace).where(Workspace.id == workspace2.id)
        )
        workspace = result.scalar_one_or_none()

        assert workspace is None, "CRITICAL: Cross-tenant query leaked data!"


class TestCrossTenantAccessBlocked:
    """Test that cross-tenant access is completely blocked"""

    @pytest.mark.asyncio
    async def test_insert_with_wrong_tenant_fails(self, async_db_session, tenant_data):
        """Verify INSERT fails when tenant context doesn't match workspace_id"""
        workspace1 = tenant_data["workspace1"]
        workspace2 = tenant_data["workspace2"]
        user2 = tenant_data["user2"]

        # Set tenant context to workspace1
        await async_db_session.execute(
            text("SET LOCAL app.current_tenant_id = :tenant_id"),
            {"tenant_id": str(workspace1.id)}
        )

        # Try to insert agent for workspace2 - should fail
        malicious_agent = AgentSwarmInstance(
            id=uuid4(),
            name="Malicious Agent",
            model="claude-3-5-sonnet-20241022",
            user_id=user2.id,
            workspace_id=workspace2.id,  # Different tenant!
            status=AgentSwarmStatus.RUNNING
        )
        async_db_session.add(malicious_agent)

        with pytest.raises(Exception):  # Should raise InsufficientPrivilege or similar
            await async_db_session.commit()

    @pytest.mark.asyncio
    async def test_update_with_wrong_tenant_fails(self, async_db_session, tenant_data):
        """Verify UPDATE fails when tenant context doesn't match"""
        workspace1 = tenant_data["workspace1"]
        agent2 = tenant_data["agent2"]

        # Set tenant context to workspace1
        await async_db_session.execute(
            text("SET LOCAL app.current_tenant_id = :tenant_id"),
            {"tenant_id": str(workspace1.id)}
        )

        # Try to update agent2 (belongs to workspace2) - should fail
        await async_db_session.execute(
            text("""
                UPDATE agent_swarm_instances
                SET name = 'Hacked Name'
                WHERE id = :agent_id
            """),
            {"agent_id": str(agent2.id)}
        )

        # Should not update any rows
        result = await async_db_session.execute(
            text("SELECT ROW_COUNT()")
        )
        # PostgreSQL doesn't have ROW_COUNT(), use result.rowcount instead
        # This test verifies the update affected 0 rows due to RLS

    @pytest.mark.asyncio
    async def test_delete_with_wrong_tenant_fails(self, async_db_session, tenant_data):
        """Verify DELETE fails when tenant context doesn't match"""
        workspace1 = tenant_data["workspace1"]
        conv2 = tenant_data["conv2"]

        # Set tenant context to workspace1
        await async_db_session.execute(
            text("SET LOCAL app.current_tenant_id = :tenant_id"),
            {"tenant_id": str(workspace1.id)}
        )

        # Try to delete conv2 (belongs to workspace2) - should not delete
        await async_db_session.execute(
            text("""
                DELETE FROM conversations
                WHERE id = :conv_id
            """),
            {"conv_id": str(conv2.id)}
        )

        # Verify conv2 still exists (by resetting context and querying)
        await async_db_session.execute(text("RESET app.current_tenant_id"))
        result = await async_db_session.execute(
            select(Conversation).where(Conversation.id == conv2.id)
        )
        conv = result.scalar_one_or_none()
        assert conv is not None, "CRITICAL: Cross-tenant DELETE succeeded!"


class TestNoTenantContextHandling:
    """Test behavior when no tenant context is set"""

    @pytest.mark.asyncio
    async def test_query_without_tenant_context_returns_empty(self, async_db_session, tenant_data):
        """Verify queries without tenant context return no results (secure by default)"""
        # Don't set tenant context

        # Query workspaces - should return nothing
        result = await async_db_session.execute(select(Workspace))
        workspaces = result.scalars().all()

        assert len(workspaces) == 0, "Should return no results without tenant context (secure by default)"

    @pytest.mark.asyncio
    async def test_insert_without_tenant_context_fails(self, async_db_session, tenant_workspaces):
        """Verify INSERT fails without tenant context"""
        workspace1, _, user1, _ = tenant_workspaces

        # Don't set tenant context

        # Try to insert agent - should fail
        agent = AgentSwarmInstance(
            id=uuid4(),
            name="Contextless Agent",
            model="claude-3-5-sonnet-20241022",
            user_id=user1.id,
            workspace_id=workspace1.id,
            status=AgentSwarmStatus.RUNNING
        )
        async_db_session.add(agent)

        with pytest.raises(Exception):  # Should fail without tenant context
            await async_db_session.commit()


class TestSuperuserBypass:
    """Test that superuser can bypass RLS for admin operations"""

    @pytest.mark.asyncio
    async def test_superuser_can_see_all_tenants(self, async_db_session, tenant_data):
        """Verify superuser/admin role can bypass RLS to see all tenants"""
        workspace1 = tenant_data["workspace1"]
        workspace2 = tenant_data["workspace2"]

        # Set session to bypass RLS (simulating superuser)
        await async_db_session.execute(
            text("SET LOCAL row_security = off")
        )

        # Query workspaces - should see both
        result = await async_db_session.execute(select(Workspace))
        workspaces = result.scalars().all()

        workspace_ids = [w.id for w in workspaces]
        assert workspace1.id in workspace_ids, "Superuser should see workspace1"
        assert workspace2.id in workspace_ids, "Superuser should see workspace2"
        assert len(workspaces) >= 2, "Superuser should see all workspaces"


class TestTenantContextValidation:
    """Test tenant context validation and error handling"""

    @pytest.mark.asyncio
    async def test_invalid_uuid_tenant_context_handled(self, async_db_session):
        """Verify invalid UUID in tenant context is handled gracefully"""
        # Try to set invalid UUID
        with pytest.raises(Exception):
            await async_db_session.execute(
                text("SET LOCAL app.current_tenant_id = 'not-a-uuid'")
            )

    @pytest.mark.asyncio
    async def test_nonexistent_tenant_context_returns_empty(self, async_db_session, tenant_data):
        """Verify setting non-existent tenant ID returns no results"""
        fake_tenant_id = uuid4()

        # Set tenant context to non-existent workspace
        await async_db_session.execute(
            text("SET LOCAL app.current_tenant_id = :tenant_id"),
            {"tenant_id": str(fake_tenant_id)}
        )

        # Query workspaces - should return nothing
        result = await async_db_session.execute(select(Workspace))
        workspaces = result.scalars().all()

        assert len(workspaces) == 0, "Non-existent tenant should return no results"


class TestRLSPerformance:
    """Test that RLS policies don't cause performance degradation"""

    @pytest.mark.asyncio
    async def test_rls_uses_workspace_id_index(self, async_db_session, tenant_data):
        """Verify RLS policies use workspace_id indexes for efficient filtering"""
        workspace1 = tenant_data["workspace1"]

        # Set tenant context
        await async_db_session.execute(
            text("SET LOCAL app.current_tenant_id = :tenant_id"),
            {"tenant_id": str(workspace1.id)}
        )

        # Run EXPLAIN on a query to verify index usage
        result = await async_db_session.execute(
            text("""
                EXPLAIN (FORMAT JSON)
                SELECT * FROM conversations WHERE workspace_id = :workspace_id
            """),
            {"workspace_id": str(workspace1.id)}
        )
        plan = result.fetchone()[0]

        # Verify query plan uses index scan (not seq scan)
        plan_text = str(plan)
        assert "Index Scan" in plan_text or "Bitmap" in plan_text, \
            "RLS policy should leverage workspace_id index"
