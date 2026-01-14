"""Add ticket blocking/dependency support.

Revision ID: 013
Revises: 012
Create Date: 2026-01-11

Adds blocked_by_ticket_id to tickets table to support ticket dependencies.
When a ticket is blocked by another ticket, it cannot be queued for execution
until the blocking ticket is completed.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # Add blocked_by_ticket_id to tickets (self-referential FK)
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.add_column(
            sa.Column("blocked_by_ticket_id", sa.String(36), nullable=True)
        )
        batch_op.create_index("ix_tickets_blocked_by_ticket_id", ["blocked_by_ticket_id"])
        batch_op.create_foreign_key(
            "fk_tickets_blocked_by_ticket_id",
            "tickets",
            ["blocked_by_ticket_id"], ["id"],
            ondelete="SET NULL"  # If blocker is deleted, unblock this ticket
        )


def downgrade() -> None:
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.drop_constraint("fk_tickets_blocked_by_ticket_id", type_="foreignkey")
        batch_op.drop_index("ix_tickets_blocked_by_ticket_id")
        batch_op.drop_column("blocked_by_ticket_id")
