"""add_skill_history_tables

Revision ID: 9e1c1d7ff273
Revises: 4f5e6d7c8b9a
Create Date: 2026-03-07 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9e1c1d7ff273'
down_revision: Union[str, Sequence[str], None] = '4f5e6d7c8b9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add skill installation and execution history tables."""

    # Create skill_installation_history table
    op.create_table(
        'skill_installation_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('skill_name', sa.String(length=255), nullable=False),
        sa.Column('agent_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('method', sa.String(length=50), nullable=True),
        sa.Column('package_name', sa.String(length=255), nullable=True),
        sa.Column('binary_path', sa.String(length=500), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agent_swarm_instances.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for skill_installation_history
    op.create_index('idx_skill_install_history_skill', 'skill_installation_history', ['skill_name'])
    op.create_index('idx_skill_install_history_agent', 'skill_installation_history', ['agent_id'])
    op.create_index('idx_skill_install_history_status', 'skill_installation_history', ['status'])

    # Create skill_execution_history table
    op.create_table(
        'skill_execution_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('execution_id', sa.UUID(), nullable=False),
        sa.Column('skill_name', sa.String(length=255), nullable=False),
        sa.Column('agent_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agent_swarm_instances.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('execution_id', name='uix_execution_id')
    )

    # Create indexes for skill_execution_history
    op.create_index('idx_skill_exec_history_skill', 'skill_execution_history', ['skill_name'])
    op.create_index('idx_skill_exec_history_agent', 'skill_execution_history', ['agent_id'])
    op.create_index('idx_skill_exec_history_status', 'skill_execution_history', ['status'])
    op.create_index('idx_skill_exec_history_started', 'skill_execution_history', ['started_at'], postgresql_ops={'started_at': 'DESC'})


def downgrade() -> None:
    """Downgrade schema - Drop skill history tables."""

    # Drop skill_execution_history table and indexes
    op.drop_index('idx_skill_exec_history_started', table_name='skill_execution_history')
    op.drop_index('idx_skill_exec_history_status', table_name='skill_execution_history')
    op.drop_index('idx_skill_exec_history_agent', table_name='skill_execution_history')
    op.drop_index('idx_skill_exec_history_skill', table_name='skill_execution_history')
    op.drop_table('skill_execution_history')

    # Drop skill_installation_history table and indexes
    op.drop_index('idx_skill_install_history_status', table_name='skill_installation_history')
    op.drop_index('idx_skill_install_history_agent', table_name='skill_installation_history')
    op.drop_index('idx_skill_install_history_skill', table_name='skill_installation_history')
    op.drop_table('skill_installation_history')
