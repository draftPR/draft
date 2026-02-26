"""add_pr_fields_to_ticket

Revision ID: 03220f0b93ae
Revises: 8ef5054dc280
Create Date: 2026-01-12 11:20:58.959405

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '03220f0b93ae'
down_revision: str | None = '8ef5054dc280'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add PR fields to tickets table
    op.add_column('tickets', sa.Column('pr_number', sa.Integer(), nullable=True))
    op.add_column('tickets', sa.Column('pr_url', sa.String(length=500), nullable=True))
    op.add_column('tickets', sa.Column('pr_state', sa.String(length=20), nullable=True))
    op.add_column('tickets', sa.Column('pr_created_at', sa.DateTime(), nullable=True))
    op.add_column('tickets', sa.Column('pr_merged_at', sa.DateTime(), nullable=True))
    op.add_column('tickets', sa.Column('pr_head_branch', sa.String(length=255), nullable=True))
    op.add_column('tickets', sa.Column('pr_base_branch', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_tickets_pr_number'), 'tickets', ['pr_number'], unique=False)


def downgrade() -> None:
    # Remove PR fields from tickets table
    op.drop_index(op.f('ix_tickets_pr_number'), table_name='tickets')
    op.drop_column('tickets', 'pr_base_branch')
    op.drop_column('tickets', 'pr_head_branch')
    op.drop_column('tickets', 'pr_merged_at')
    op.drop_column('tickets', 'pr_created_at')
    op.drop_column('tickets', 'pr_state')
    op.drop_column('tickets', 'pr_url')
    op.drop_column('tickets', 'pr_number')
