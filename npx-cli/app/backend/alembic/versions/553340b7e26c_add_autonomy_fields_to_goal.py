"""add autonomy fields to goal

Revision ID: 553340b7e26c
Revises: 7b307e847cbd
Create Date: 2026-02-16 13:31:00.783226

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "553340b7e26c"
down_revision: str | None = "7b307e847cbd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "goals",
        sa.Column("autonomy_enabled", sa.Boolean(), server_default="0", nullable=False),
    )
    op.add_column(
        "goals",
        sa.Column(
            "auto_approve_tickets", sa.Boolean(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "goals",
        sa.Column(
            "auto_approve_revisions", sa.Boolean(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "goals",
        sa.Column("auto_merge", sa.Boolean(), server_default="0", nullable=False),
    )
    op.add_column(
        "goals",
        sa.Column(
            "auto_approve_followups", sa.Boolean(), server_default="0", nullable=False
        ),
    )
    op.add_column("goals", sa.Column("max_auto_approvals", sa.Integer(), nullable=True))
    op.add_column(
        "goals",
        sa.Column(
            "auto_approval_count", sa.Integer(), server_default="0", nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("goals", "auto_approval_count")
    op.drop_column("goals", "max_auto_approvals")
    op.drop_column("goals", "auto_approve_followups")
    op.drop_column("goals", "auto_merge")
    op.drop_column("goals", "auto_approve_revisions")
    op.drop_column("goals", "auto_approve_tickets")
    op.drop_column("goals", "autonomy_enabled")
