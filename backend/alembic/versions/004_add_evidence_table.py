"""Add evidence table for verification command results.

Revision ID: 004
Revises: 003
Create Date: 2026-01-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create evidence table
    op.create_table(
        "evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.String(36),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("command", sa.Text, nullable=False),
        sa.Column("exit_code", sa.Integer, nullable=False),
        sa.Column("stdout_path", sa.Text, nullable=True),
        sa.Column("stderr_path", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_evidence_ticket_id", "evidence", ["ticket_id"])
    op.create_index("ix_evidence_job_id", "evidence", ["job_id"])


def downgrade() -> None:
    op.drop_table("evidence")


