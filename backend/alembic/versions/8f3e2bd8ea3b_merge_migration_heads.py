"""merge_migration_heads

Revision ID: 8f3e2bd8ea3b
Revises: 03220f0b93ae, perf_indexes_001
Create Date: 2026-01-29 12:39:52.200213

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f3e2bd8ea3b'
down_revision: Union[str, None] = ('03220f0b93ae', 'perf_indexes_001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass


