"""Add sort_order column to tickets for drag-and-drop ordering.

Revision ID: 015
Revises: 774dc335c679
Create Date: 2026-03-01

Adds a sort_order integer column to the tickets table so that users
can manually reorder tickets within a state column via drag-and-drop.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: str | None = "774dc335c679"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.add_column(sa.Column("sort_order", sa.Integer(), nullable=True))
        batch_op.create_index("ix_tickets_sort_order", ["sort_order"])


def downgrade() -> None:
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.drop_index("ix_tickets_sort_order")
        batch_op.drop_column("sort_order")
