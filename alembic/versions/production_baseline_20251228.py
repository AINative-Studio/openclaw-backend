"""production_baseline_20251228

This is a baseline migration representing the production database state as of 2025-12-28.
All tables that existed in production at this point are assumed to exist.

Revision ID: production_baseline_20251228
Revises: None
Create Date: 2025-12-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'production_baseline_20251228'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    No operations - this is a baseline migration.
    All tables are assumed to already exist in production.
    """
    pass


def downgrade() -> None:
    """
    No operations - this is a baseline migration.
    """
    pass
