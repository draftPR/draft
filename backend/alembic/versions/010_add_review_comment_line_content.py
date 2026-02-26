"""Add line_content to review_comments.

Revision ID: 010
Revises: 009
Create Date: 2026-01-07

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add line_content column to review_comments table
    with op.batch_alter_table("review_comments") as batch_op:
        batch_op.add_column(
            sa.Column(
                "line_content",
                sa.Text(),
                nullable=True,
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("review_comments") as batch_op:
        batch_op.drop_column("line_content")
