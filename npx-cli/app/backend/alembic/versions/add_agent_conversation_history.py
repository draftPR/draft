"""Add agent_conversation_history table for UDAR agent memory

Revision ID: add_agent_conversation_history
Revises: b10fb0b62240
Create Date: 2026-02-09 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_agent_conversation_history"
down_revision: str | None = "b10fb0b62240"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create agent_conversation_history table for UDAR agent memory.

    This table stores compressed conversation checkpoints (summaries, not full messages)
    to support UDAR agent state persistence across multiple invocations.
    """
    op.create_table(
        "agent_conversation_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("goal_id", sa.String(length=36), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=100), nullable=False),
        sa.Column(
            "messages_json", sa.Text(), nullable=True
        ),  # Empty by default (lean storage)
        sa.Column("metadata_json", sa.Text(), nullable=False),  # Compressed summary
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["goals.id"],
            name="fk_agent_conversation_history_goal_id",
            ondelete="CASCADE",  # Delete history when goal deleted
        ),
    )

    # Index for efficient lookup by goal_id
    op.create_index(
        "ix_agent_conversation_history_goal_id",
        "agent_conversation_history",
        ["goal_id"],
    )

    # Index for cleanup queries (find old checkpoints)
    op.create_index(
        "ix_agent_conversation_history_created_at",
        "agent_conversation_history",
        ["created_at"],
    )


def downgrade() -> None:
    """Drop agent_conversation_history table."""
    op.drop_index(
        "ix_agent_conversation_history_created_at",
        table_name="agent_conversation_history",
    )
    op.drop_index(
        "ix_agent_conversation_history_goal_id", table_name="agent_conversation_history"
    )
    op.drop_table("agent_conversation_history")
