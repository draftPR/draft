"""add_goal_status

Revision ID: 357c780ee445
Revises: add_job_variant_001
Create Date: 2026-01-29 19:58:09.271091

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "357c780ee445"
down_revision: str | None = "add_job_variant_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add status column to goals table
    op.add_column(
        "goals",
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="proposed"
        ),
    )


def downgrade() -> None:
    # Remove status column from goals table
    op.drop_column("goals", "status")
