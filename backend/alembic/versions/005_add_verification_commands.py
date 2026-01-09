"""Add verification_commands column to tickets.

Revision ID: 005
Revises: 004
Create Date: 2026-01-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add verification_commands_json column to tickets
    # Stores JSON array of verification command strings
    op.add_column(
        "tickets",
        sa.Column("verification_commands_json", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tickets", "verification_commands_json")


