"""Add planner lock table.

Revision ID: 006
Revises: 005
Create Date: 2026-01-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create planner_locks table."""
    op.create_table(
        "planner_locks",
        sa.Column("lock_key", sa.String(50), primary_key=True),
        sa.Column(
            "acquired_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("owner_id", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    """Drop planner_locks table."""
    op.drop_table("planner_locks")


