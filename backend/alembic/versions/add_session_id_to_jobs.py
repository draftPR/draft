"""Add session_id column to jobs table for executor session resume.

Revision ID: a1b2c3d4e5f6
Revises: 7b307e847cbd
Create Date: 2026-02-16 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "7b307e847cbd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("session_id", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "session_id")
