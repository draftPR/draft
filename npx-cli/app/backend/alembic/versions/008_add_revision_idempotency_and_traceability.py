"""Add revision idempotency constraint and job source_revision_id for traceability.

Revision ID: 008
Revises: 007
Create Date: 2026-01-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add unique constraint on (ticket_id, job_id) for revision idempotency
    # This prevents duplicate revisions if the same job is retried
    # Use batch mode for SQLite compatibility
    with op.batch_alter_table("revisions") as batch_op:
        batch_op.create_unique_constraint(
            "uq_revision_ticket_job",
            ["ticket_id", "job_id"],
        )

    # Add source_revision_id to jobs for traceability
    # When a job is triggered by review feedback, this tracks which revision is being addressed
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_revision_id",
                sa.String(36),
                nullable=True,
            ),
        )
        batch_op.create_index("ix_jobs_source_revision_id", ["source_revision_id"])
        # Note: SQLite doesn't support FK constraints after table creation via ALTER
        # The FK is defined in the model but not enforced at DB level for existing tables


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_index("ix_jobs_source_revision_id")
        batch_op.drop_column("source_revision_id")
    with op.batch_alter_table("revisions") as batch_op:
        batch_op.drop_constraint("uq_revision_ticket_job", type_="unique")
