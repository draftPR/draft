"""add_job_variant

Revision ID: add_job_variant_001
Revises: 3348e5cf54c1
Create Date: 2026-01-29

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'add_job_variant_001'
down_revision: str | None = '3348e5cf54c1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add variant column to jobs table
    op.add_column('jobs', sa.Column('variant', sa.String(length=20), nullable=True, server_default='default'))


def downgrade() -> None:
    # Remove variant column from jobs table
    op.drop_column('jobs', 'variant')
