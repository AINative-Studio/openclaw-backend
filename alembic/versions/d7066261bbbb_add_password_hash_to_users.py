"""add_password_hash_to_users

Revision ID: d7066261bbbb
Revises: ecc6fff0d50d
Create Date: 2026-03-09 12:12:34.735371

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7066261bbbb'
down_revision: Union[str, Sequence[str], None] = 'ecc6fff0d50d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add password_hash column to users table (idempotent)."""
    from sqlalchemy import inspect

    # Get connection and check if column already exists
    connection = op.get_bind()
    inspector = inspect(connection)
    existing_columns = {col['name'] for col in inspector.get_columns('users')}

    # Add password_hash column if it doesn't exist
    if 'password_hash' not in existing_columns:
        op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema: Remove password_hash column from users table."""
    op.drop_column('users', 'password_hash')
