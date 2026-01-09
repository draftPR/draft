"""Add analysis_cache table for caching codebase analysis results.

Revision ID: 011
Revises: 010
Create Date: 2026-01-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create analysis_cache table."""
    op.create_table(
        "analysis_cache",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )

    # Index for cleanup queries
    op.create_index(
        "ix_analysis_cache_expires_at",
        "analysis_cache",
        ["expires_at"],
    )


def downgrade() -> None:
    """Drop analysis_cache table."""
    op.drop_index("ix_analysis_cache_expires_at", table_name="analysis_cache")
    op.drop_table("analysis_cache")

