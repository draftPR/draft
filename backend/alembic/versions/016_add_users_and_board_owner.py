"""Add users table and owner_id to boards.

Revision ID: 016
Revises: 0c2d89fff3b1
Create Date: 2026-03-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "016"
down_revision: str | None = "0c2d89fff3b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # Add owner_id to boards using batch mode (SQLite compat)
    with op.batch_alter_table("boards") as batch_op:
        batch_op.add_column(
            sa.Column("owner_id", sa.String(36), nullable=True)
        )
        batch_op.create_index("ix_boards_owner_id", ["owner_id"])
        batch_op.create_foreign_key(
            "fk_boards_owner_id",
            "users",
            ["owner_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("boards") as batch_op:
        batch_op.drop_constraint("fk_boards_owner_id", type_="foreignkey")
        batch_op.drop_index("ix_boards_owner_id")
        batch_op.drop_column("owner_id")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
