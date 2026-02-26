"""Add config column to boards table

Revision ID: 9d17f0698d3b
Revises: add_repos_001
Create Date: 2026-02-03 17:11:54.526459

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9d17f0698d3b'
down_revision: str | None = 'add_repos_001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add config JSON column to boards table
    # This allows board-level configuration overrides for smartkanban.yaml settings
    op.add_column('boards', sa.Column('config', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Remove config column
    op.drop_column('boards', 'config')


