"""add_agent_skill_configurations_table

Revision ID: 4f5e6d7c8b9a
Revises: 8cd88863aba6
Create Date: 2026-03-04 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f5e6d7c8b9a'
down_revision: Union[str, Sequence[str], None] = '8cd88863aba6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create agent_skill_configurations table
    op.create_table(
        'agent_skill_configurations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('agent_id', sa.UUID(), nullable=False),
        sa.Column('skill_name', sa.String(length=255), nullable=False),
        sa.Column('credentials', sa.Text(), nullable=True),
        sa.Column('config', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agent_swarm_instances.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agent_id', 'skill_name', name='uix_agent_skill')
    )

    # Create index
    op.create_index('idx_agent_skill_config', 'agent_skill_configurations', ['agent_id', 'skill_name'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop index
    op.drop_index('idx_agent_skill_config', table_name='agent_skill_configurations')

    # Drop table
    op.drop_table('agent_skill_configurations')
