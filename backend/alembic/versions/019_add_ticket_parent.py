"""Add parent_ticket_id to tickets (sub-ticket split).

Revision ID: 019_ticket_parent
Revises: 018_ticket_executor_profile
Create Date: 2026-09-07

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "019_ticket_parent"
down_revision = "018_ticket_executor_profile"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.add_column(sa.Column("parent_ticket_id", sa.String(36), nullable=True))
        batch_op.create_index("ix_tickets_parent_ticket_id", ["parent_ticket_id"])
        batch_op.create_foreign_key(
            "fk_tickets_parent_ticket_id",
            "tickets",
            ["parent_ticket_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.drop_constraint("fk_tickets_parent_ticket_id", type_="foreignkey")
        batch_op.drop_index("ix_tickets_parent_ticket_id")
        batch_op.drop_column("parent_ticket_id")
