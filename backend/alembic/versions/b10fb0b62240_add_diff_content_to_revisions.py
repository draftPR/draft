"""add_diff_content_to_revisions

Revision ID: b10fb0b62240
Revises: 9d17f0698d3b
Create Date: 2026-02-10 07:08:55.015460

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b10fb0b62240'
down_revision: Union[str, None] = '9d17f0698d3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add diff content columns to store diffs permanently in DB
    # This preserves diffs even after worktree/evidence cleanup
    op.add_column('revisions', sa.Column('diff_stat_content', sa.Text(), nullable=True))
    op.add_column('revisions', sa.Column('diff_patch_content', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove diff content columns
    op.drop_column('revisions', 'diff_patch_content')
    op.drop_column('revisions', 'diff_stat_content')


