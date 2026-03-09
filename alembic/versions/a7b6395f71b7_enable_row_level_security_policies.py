"""enable_row_level_security_policies

Revision ID: a7b6395f71b7
Revises: 9e1c1d7ff273
Create Date: 2026-03-08 20:30:12.696401

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b6395f71b7'
down_revision: Union[str, Sequence[str], None] = '9e1c1d7ff273'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Enable Row-Level Security (RLS) on multi-tenant tables

    Security Requirements (Issue #120):
    1. Enable RLS on workspaces, conversations, agent_swarm_instances, tasks
    2. Create tenant isolation policies using app.current_tenant_id
    3. Enforce workspace_id matching for all DML operations
    4. Secure by default (no tenant context = no results)

    CRITICAL: Zero tolerance for data leaks between tenants
    """

    # Step 1: Add workspace_id to tasks table (for tenant isolation)
    # Note: Conversations and agent_swarm_instances already have workspace_id
    op.add_column('tasks', sa.Column('workspace_id', sa.UUID(), nullable=True))
    op.create_index('ix_tasks_workspace_id', 'tasks', ['workspace_id'])
    op.create_foreign_key(
        'fk_tasks_workspace_id',
        'tasks',
        'workspaces',
        ['workspace_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # Step 2: Enable RLS on multi-tenant tables
    # This ensures all queries are subject to RLS policies
    op.execute("ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE conversations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_swarm_instances ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tasks ENABLE ROW LEVEL SECURITY")

    # Step 3: Create RLS policies for tenant isolation
    # Each policy enforces workspace_id = current_setting('app.current_tenant_id')

    # Policy 1: Workspaces - user can only see their own workspace
    op.execute("""
        CREATE POLICY workspace_tenant_isolation ON workspaces
        FOR ALL
        USING (
            id::text = current_setting('app.current_tenant_id', TRUE)
        )
        WITH CHECK (
            id::text = current_setting('app.current_tenant_id', TRUE)
        )
    """)

    # Policy 2: Conversations - user can only see conversations in their workspace
    op.execute("""
        CREATE POLICY conversation_tenant_isolation ON conversations
        FOR ALL
        USING (
            workspace_id::text = current_setting('app.current_tenant_id', TRUE)
        )
        WITH CHECK (
            workspace_id::text = current_setting('app.current_tenant_id', TRUE)
        )
    """)

    # Policy 3: Agent Swarm Instances - user can only see agents in their workspace
    op.execute("""
        CREATE POLICY agent_tenant_isolation ON agent_swarm_instances
        FOR ALL
        USING (
            workspace_id::text = current_setting('app.current_tenant_id', TRUE)
        )
        WITH CHECK (
            workspace_id::text = current_setting('app.current_tenant_id', TRUE)
        )
    """)

    # Policy 4: Tasks - user can only see tasks in their workspace
    op.execute("""
        CREATE POLICY task_tenant_isolation ON tasks
        FOR ALL
        USING (
            workspace_id::text = current_setting('app.current_tenant_id', TRUE)
        )
        WITH CHECK (
            workspace_id::text = current_setting('app.current_tenant_id', TRUE)
        )
    """)

    # Step 4: Force RLS even for table owner (secure by default)
    # Without this, the application role could bypass RLS
    op.execute("ALTER TABLE workspaces FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE conversations FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_swarm_instances FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tasks FORCE ROW LEVEL SECURITY")

    # Note: Superuser can still bypass RLS with "SET row_security = off"
    # This is intentional for admin operations and data migrations


def downgrade() -> None:
    """
    Disable Row-Level Security and remove policies

    WARNING: This removes tenant isolation safeguards
    """

    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS workspace_tenant_isolation ON workspaces")
    op.execute("DROP POLICY IF EXISTS conversation_tenant_isolation ON conversations")
    op.execute("DROP POLICY IF EXISTS agent_tenant_isolation ON agent_swarm_instances")
    op.execute("DROP POLICY IF EXISTS task_tenant_isolation ON tasks")

    # Disable RLS on tables
    op.execute("ALTER TABLE workspaces DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE conversations DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_swarm_instances DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tasks DISABLE ROW LEVEL SECURITY")

    # Remove workspace_id from tasks table
    op.drop_constraint('fk_tasks_workspace_id', 'tasks', type_='foreignkey')
    op.drop_index('ix_tasks_workspace_id', 'tasks')
    op.drop_column('tasks', 'workspace_id')
