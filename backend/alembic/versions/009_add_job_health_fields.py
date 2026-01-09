"""Add job health monitoring fields.

Revision ID: 009
Revises: 008
Create Date: 2026-01-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add last_heartbeat_at and timeout_seconds to jobs table
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "last_heartbeat_at",
                sa.DateTime(),
                nullable=True,
            ),
        )
        batch_op.add_column(
            sa.Column(
                "timeout_seconds",
                sa.Integer(),
                nullable=True,
            ),
        )
        batch_op.create_index("ix_jobs_last_heartbeat_at", ["last_heartbeat_at"])


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_index("ix_jobs_last_heartbeat_at")
        batch_op.drop_column("timeout_seconds")
        batch_op.drop_column("last_heartbeat_at")


