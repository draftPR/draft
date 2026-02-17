"""merge migration heads

Revision ID: 774dc335c679
Revises: 553340b7e26c, a1b2c3d4e5f6
Create Date: 2026-02-17 06:14:05.708067

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '774dc335c679'
down_revision: Union[str, None] = ('553340b7e26c', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass


