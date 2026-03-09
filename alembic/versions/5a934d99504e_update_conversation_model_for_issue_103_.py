"""Update conversation model for Issue 103 multi-channel support

Revision ID: 5a934d99504e
Revises: a7b6395f71b7
Create Date: 2026-03-08 22:17:41.931279

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a934d99504e'
down_revision: Union[str, Sequence[str], None] = 'a7b6395f71b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema for Issue #103 - Multi-channel Conversation Support.

    Changes:
    - Rename agent_id to agent_swarm_instance_id (make nullable)
    - Make user_id NOT NULL (was nullable)
    - Add channel (required)
    - Add channel_conversation_id (required)
    - Add title (optional)
    - Add conversation_metadata (JSON, replaces old metadata pattern)
    - Add archived_at timestamp
    - Add updated_at timestamp
    - Remove old OpenClaw/ZeroDB fields
    - Add composite unique index on (channel, channel_conversation_id)
    """
    # Add new required channel fields (nullable first, then populate defaults)
    # Do this BEFORE dropping old columns so we can use them as defaults
    op.add_column('conversations', sa.Column('channel', sa.String(length=50), nullable=True))
    op.add_column('conversations', sa.Column('channel_conversation_id', sa.String(length=255), nullable=True))

    # Populate default values for existing rows (using old openclaw_session_key before it's dropped)
    op.execute("UPDATE conversations SET channel = 'whatsapp' WHERE channel IS NULL")
    op.execute("UPDATE conversations SET channel_conversation_id = COALESCE(openclaw_session_key, id::text) WHERE channel_conversation_id IS NULL")

    # Now make them NOT NULL
    op.alter_column('conversations', 'channel', nullable=False)
    op.alter_column('conversations', 'channel_conversation_id', nullable=False)

    # Drop old OpenClaw-specific fields (after we've used them for defaults)
    op.drop_column('conversations', 'openclaw_session_key')
    op.drop_column('conversations', 'zerodb_table_name')
    op.drop_column('conversations', 'zerodb_conversation_row_id')
    op.drop_column('conversations', 'started_at')
    op.drop_column('conversations', 'last_message_at')
    op.drop_column('conversations', 'message_count')

    # Rename agent_id to agent_swarm_instance_id and make nullable
    op.alter_column('conversations', 'agent_id',
                    new_column_name='agent_swarm_instance_id',
                    existing_type=sa.dialects.postgresql.UUID(),
                    nullable=True)

    # Make user_id NOT NULL (populate default for any NULL values)
    # Use workspace_id as a fallback for user_id if NULL
    op.execute("""
        UPDATE conversations
        SET user_id = workspace_id
        WHERE user_id IS NULL AND workspace_id IS NOT NULL
    """)
    # For any remaining NULLs, use a default UUID (should not happen in practice)
    op.execute("""
        UPDATE conversations
        SET user_id = '00000000-0000-0000-0000-000000000000'::uuid
        WHERE user_id IS NULL
    """)
    op.alter_column('conversations', 'user_id',
                    existing_type=sa.dialects.postgresql.UUID(),
                    nullable=False)

    # Add optional fields
    op.add_column('conversations', sa.Column('title', sa.String(length=500), nullable=True))
    op.add_column('conversations', sa.Column('conversation_metadata', sa.JSON(), nullable=False, server_default='{}'))

    # Add timestamps
    op.add_column('conversations', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('conversations', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('conversations', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))

    # Create composite unique index on (channel, channel_conversation_id)
    op.create_index('ix_conversations_channel_conversation_id', 'conversations', ['channel', 'channel_conversation_id'], unique=True)

    # Create individual indexes
    op.create_index(op.f('ix_conversations_channel'), 'conversations', ['channel'], unique=False)
    op.create_index(op.f('ix_conversations_channel_conversation_id_single'), 'conversations', ['channel_conversation_id'], unique=False)


def downgrade() -> None:
    """
    Downgrade schema - restore old OpenClaw-oriented conversation model.
    """
    # Drop new indexes
    op.drop_index('ix_conversations_channel_conversation_id', table_name='conversations')
    op.drop_index(op.f('ix_conversations_channel_conversation_id_single'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_channel'), table_name='conversations')

    # Drop new columns
    op.drop_column('conversations', 'archived_at')
    op.drop_column('conversations', 'updated_at')
    op.drop_column('conversations', 'created_at')
    op.drop_column('conversations', 'conversation_metadata')
    op.drop_column('conversations', 'title')
    op.drop_column('conversations', 'channel_conversation_id')
    op.drop_column('conversations', 'channel')

    # Make user_id nullable again
    op.alter_column('conversations', 'user_id',
                    existing_type=sa.dialects.postgresql.UUID(),
                    nullable=True)

    # Rename agent_swarm_instance_id back to agent_id and make NOT NULL
    op.alter_column('conversations', 'agent_swarm_instance_id',
                    new_column_name='agent_id',
                    existing_type=sa.dialects.postgresql.UUID(),
                    nullable=False)

    # Restore old OpenClaw fields
    op.add_column('conversations', sa.Column('message_count', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('conversations', sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('conversations', sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()')))
    op.add_column('conversations', sa.Column('zerodb_conversation_row_id', sa.String(length=255), nullable=True))
    op.add_column('conversations', sa.Column('zerodb_table_name', sa.String(length=100), server_default='messages'))
    op.add_column('conversations', sa.Column('openclaw_session_key', sa.String(length=255), nullable=True))

    # Recreate old unique index on openclaw_session_key
    op.create_index('ix_conversations_openclaw_session_key', 'conversations', ['openclaw_session_key'], unique=True)
