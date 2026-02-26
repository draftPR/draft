"""merge_migration_heads

Revision ID: 8f3e2bd8ea3b
Revises: 03220f0b93ae, perf_indexes_001
Create Date: 2026-01-29 12:39:52.200213

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "8f3e2bd8ea3b"
down_revision: str | None = ("03220f0b93ae", "perf_indexes_001")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
