"""add_agent_channel_credentials_table

Revision ID: 8cd88863aba6
Revises: 3cba02be23a6
Create Date: 2026-03-04 20:52:08.456787

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8cd88863aba6'
down_revision: Union[str, Sequence[str], None] = '3cba02be23a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create agent_channel_credentials table
    op.create_table(
        'agent_channel_credentials',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('agent_id', sa.UUID(), nullable=False),
        sa.Column('channel_type', sa.String(length=50), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('credentials', sa.Text(), nullable=True),
        sa.Column('channel_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agent_swarm_instances.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agent_id', 'channel_type', 'provider', name='uix_agent_channel_provider')
    )

    # Create indexes
    op.create_index('idx_agent_channel', 'agent_channel_credentials', ['agent_id', 'channel_type'])
    op.create_index('idx_channel_provider', 'agent_channel_credentials', ['channel_type', 'provider'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('idx_channel_provider', table_name='agent_channel_credentials')
    op.drop_index('idx_agent_channel', table_name='agent_channel_credentials')

    # Drop table
    op.drop_table('agent_channel_credentials')
