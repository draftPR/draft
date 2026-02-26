"""add_merge_checklist_table

Revision ID: 3348e5cf54c1
Revises: 8f3e2bd8ea3b
Create Date: 2026-01-29 12:40:59.627310

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3348e5cf54c1"
down_revision: str | None = "8f3e2bd8ea3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create merge_checklists table
    op.create_table(
        "merge_checklists",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("goal_id", sa.String(length=36), nullable=False),
        sa.Column("all_tests_passed", sa.Boolean(), nullable=False),
        sa.Column("total_files_changed", sa.Integer(), nullable=False),
        sa.Column("total_lines_changed", sa.Integer(), nullable=False),
        sa.Column("total_cost_usd", sa.Float(), nullable=True),
        sa.Column("budget_exceeded", sa.Boolean(), nullable=False),
        sa.Column("code_reviewed", sa.Boolean(), nullable=False),
        sa.Column("no_sensitive_data", sa.Boolean(), nullable=False),
        sa.Column("rollback_plan_understood", sa.Boolean(), nullable=False),
        sa.Column("documentation_updated", sa.Boolean(), nullable=False),
        sa.Column("rollback_plan_json", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("ready_to_merge", sa.Boolean(), nullable=False),
        sa.Column("merged_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_merge_checklists_goal_id"),
        "merge_checklists",
        ["goal_id"],
        unique=False,
    )


def downgrade() -> None:
    # Drop merge_checklists table
    op.drop_index(op.f("ix_merge_checklists_goal_id"), table_name="merge_checklists")
    op.drop_table("merge_checklists")
