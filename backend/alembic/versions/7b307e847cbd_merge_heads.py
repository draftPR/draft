"""merge heads

Revision ID: 7b307e847cbd
Revises: add_agent_conversation_history, c3a8f1b2d4e5
Create Date: 2026-02-16 13:23:30.635840

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b307e847cbd'
down_revision: Union[str, None] = ('add_agent_conversation_history', 'c3a8f1b2d4e5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass


