"""add_current_conversation_id_to_agent_swarm_instance

Issue #104: Extend AgentSwarmInstance for Conversations (Epic E9, Sprint 2)

Adds current_conversation_id column to agent_swarm_instances table to track
the currently active conversation for each agent. This enables agents to
maintain context across multiple messages within a conversation.

Revision ID: ecc6fff0d50d
Revises: 65b574494f2d
Create Date: 2026-03-08 22:18:06.122461

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ecc6fff0d50d'
down_revision: Union[str, Sequence[str], None] = '65b574494f2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add current_conversation_id column to agent_swarm_instances table.

    This column is nullable to support agents that don't have an active
    conversation, and includes proper foreign key constraint to conversations
    table with SET NULL on delete.
    """
    # Add current_conversation_id column with foreign key to conversations
    op.add_column(
        'agent_swarm_instances',
        sa.Column(
            'current_conversation_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment='Current active conversation for this agent'
        )
    )

    # Create index on current_conversation_id for efficient lookups
    op.create_index(
        op.f('ix_agent_swarm_instances_current_conversation_id'),
        'agent_swarm_instances',
        ['current_conversation_id'],
        unique=False
    )

    # Add foreign key constraint to conversations table
    op.create_foreign_key(
        'fk_agent_swarm_instances_current_conversation_id_conversations',
        'agent_swarm_instances',
        'conversations',
        ['current_conversation_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """
    Remove current_conversation_id column from agent_swarm_instances table.

    This drops the foreign key constraint, index, and column in reverse order
    of creation.
    """
    # Drop foreign key constraint
    op.drop_constraint(
        'fk_agent_swarm_instances_current_conversation_id_conversations',
        'agent_swarm_instances',
        type_='foreignkey'
    )

    # Drop index
    op.drop_index(
        op.f('ix_agent_swarm_instances_current_conversation_id'),
        table_name='agent_swarm_instances'
    )

    # Drop column
    op.drop_column('agent_swarm_instances', 'current_conversation_id')
