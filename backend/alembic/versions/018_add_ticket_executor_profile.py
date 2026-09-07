"""Add executor_profile to tickets.

Revision ID: 018_ticket_executor_profile
Revises: 017
Create Date: 2026-09-07

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "018_ticket_executor_profile"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tickets",
        sa.Column("executor_profile", sa.String(length=100), nullable=True),
    )


def downgrade():
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.drop_column("executor_profile")
