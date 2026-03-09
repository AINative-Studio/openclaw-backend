"""add_full_name_updated_at_is_active_to_users

Revision ID: 65b574494f2d
Revises: 5a934d99504e
Create Date: 2026-03-08 22:18:05.197015

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '65b574494f2d'
down_revision: Union[str, Sequence[str], None] = '5a934d99504e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add full_name, updated_at, and is_active columns to users table (idempotent)."""
    from sqlalchemy import inspect

    # Get connection and check which columns already exist
    connection = op.get_bind()
    inspector = inspect(connection)
    existing_columns = {col['name'] for col in inspector.get_columns('users')}

    # Add full_name column if it doesn't exist
    if 'full_name' not in existing_columns:
        op.add_column('users', sa.Column('full_name', sa.String(length=255), nullable=True))

    # Add updated_at column if it doesn't exist
    if 'updated_at' not in existing_columns:
        op.add_column('users', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))

    # Add is_active column if it doesn't exist (boolean, default True, not nullable)
    if 'is_active' not in existing_columns:
        op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))


def downgrade() -> None:
    """Downgrade schema: Remove full_name, updated_at, and is_active columns from users table."""
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'updated_at')
    op.drop_column('users', 'full_name')
