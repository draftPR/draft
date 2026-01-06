"""Add workspaces table for git worktree isolation.

Revision ID: 003
Revises: 002
Create Date: 2026-01-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create workspaces table
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.String(36),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("worktree_path", sa.Text, nullable=False),
        sa.Column("branch_name", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("cleaned_up_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_workspaces_ticket_id", "workspaces", ["ticket_id"])


def downgrade() -> None:
    op.drop_table("workspaces")

