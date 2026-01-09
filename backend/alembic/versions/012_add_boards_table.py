"""Add boards table and board_id to goals/tickets/jobs/workspaces.

Revision ID: 012
Revises: 011
Create Date: 2026-01-08

The Board is the primary permission boundary in Smart Kanban:
- All goals, tickets, jobs, workspaces belong to a board
- board_id is the authorization check for all operations
- repo_root is a property of the board (single repo per board)
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # Create boards table
    op.create_table(
        "boards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("repo_root", sa.String(1024), nullable=False),
        sa.Column("default_branch", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Add board_id to goals (using batch mode for SQLite compatibility)
    with op.batch_alter_table("goals") as batch_op:
        batch_op.add_column(sa.Column("board_id", sa.String(36), nullable=True))
        batch_op.create_index("ix_goals_board_id", ["board_id"])
        batch_op.create_foreign_key(
            "fk_goals_board_id",
            "boards",
            ["board_id"], ["id"],
            ondelete="CASCADE"
        )
    
    # Add board_id to tickets
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.add_column(sa.Column("board_id", sa.String(36), nullable=True))
        batch_op.create_index("ix_tickets_board_id", ["board_id"])
        batch_op.create_foreign_key(
            "fk_tickets_board_id",
            "boards",
            ["board_id"], ["id"],
            ondelete="CASCADE"
        )
    
    # Add board_id to jobs
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("board_id", sa.String(36), nullable=True))
        batch_op.create_index("ix_jobs_board_id", ["board_id"])
        batch_op.create_foreign_key(
            "fk_jobs_board_id",
            "boards",
            ["board_id"], ["id"],
            ondelete="CASCADE"
        )
    
    # Add board_id to workspaces
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.add_column(sa.Column("board_id", sa.String(36), nullable=True))
        batch_op.create_index("ix_workspaces_board_id", ["board_id"])
        batch_op.create_foreign_key(
            "fk_workspaces_board_id",
            "boards",
            ["board_id"], ["id"],
            ondelete="CASCADE"
        )


def downgrade() -> None:
    # Drop foreign keys and columns in reverse order (using batch mode for SQLite)
    
    # workspaces
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_constraint("fk_workspaces_board_id", type_="foreignkey")
        batch_op.drop_index("ix_workspaces_board_id")
        batch_op.drop_column("board_id")
    
    # jobs
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint("fk_jobs_board_id", type_="foreignkey")
        batch_op.drop_index("ix_jobs_board_id")
        batch_op.drop_column("board_id")
    
    # tickets
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.drop_constraint("fk_tickets_board_id", type_="foreignkey")
        batch_op.drop_index("ix_tickets_board_id")
        batch_op.drop_column("board_id")
    
    # goals
    with op.batch_alter_table("goals") as batch_op:
        batch_op.drop_constraint("fk_goals_board_id", type_="foreignkey")
        batch_op.drop_index("ix_goals_board_id")
        batch_op.drop_column("board_id")
    
    # boards table
    op.drop_table("boards")

