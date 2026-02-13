"""add_repos_and_board_repos

Revision ID: add_repos_001
Revises: 357c780ee445
Create Date: 2026-01-29 22:00:00.000000

"""
from typing import Sequence, Union
import uuid
from pathlib import Path

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


# revision identifiers, used by Alembic.
revision: str = 'add_repos_001'
down_revision: Union[str, None] = '357c780ee445'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create repos table
    op.create_table('repos',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('path', sa.String(length=1024), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('setup_script', sa.Text(), nullable=True),
        sa.Column('cleanup_script', sa.Text(), nullable=True),
        sa.Column('dev_server_script', sa.Text(), nullable=True),
        sa.Column('default_branch', sa.String(length=255), nullable=True),
        sa.Column('remote_url', sa.String(length=1024), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('path', name='uq_repo_path')
    )
    op.create_index(op.f('ix_repos_path'), 'repos', ['path'], unique=True)

    # Create board_repos junction table
    op.create_table('board_repos',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('board_id', sa.String(length=36), nullable=False),
        sa.Column('repo_id', sa.String(length=36), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('custom_setup_script', sa.Text(), nullable=True),
        sa.Column('custom_cleanup_script', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['board_id'], ['boards.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['repo_id'], ['repos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('board_id', 'repo_id', name='uq_board_repo')
    )
    op.create_index(op.f('ix_board_repos_board_id'), 'board_repos', ['board_id'], unique=False)
    op.create_index(op.f('ix_board_repos_repo_id'), 'board_repos', ['repo_id'], unique=False)

    # Migrate existing boards.repo_root to new structure
    # Note: This is a data migration, so we need to use SQLAlchemy core

    # Define table structures for data migration
    boards = table('boards',
        column('id', sa.String),
        column('repo_root', sa.String),
        column('default_branch', sa.String)
    )

    repos_table = table('repos',
        column('id', sa.String),
        column('path', sa.String),
        column('name', sa.String),
        column('display_name', sa.String),
        column('default_branch', sa.String)
    )

    board_repos_table = table('board_repos',
        column('id', sa.String),
        column('board_id', sa.String),
        column('repo_id', sa.String),
        column('is_primary', sa.Boolean)
    )

    # Get connection
    conn = op.get_bind()

    # Fetch all boards with repo_root
    result = conn.execute(sa.select(boards.c.id, boards.c.repo_root, boards.c.default_branch))
    board_data = result.fetchall()

    # For each board, create a repo and link it
    for board_id, repo_root, default_branch in board_data:
        if not repo_root:
            continue

        # Generate repo ID
        repo_id = str(uuid.uuid4())

        # Extract repo name from path
        try:
            repo_name = Path(repo_root).name
        except Exception:
            repo_name = "repository"

        # Insert repo
        conn.execute(
            repos_table.insert().values(
                id=repo_id,
                path=repo_root,
                name=repo_name,
                display_name=repo_name,
                default_branch=default_branch
            )
        )

        # Link board to repo (as primary)
        board_repo_id = str(uuid.uuid4())
        conn.execute(
            board_repos_table.insert().values(
                id=board_repo_id,
                board_id=board_id,
                repo_id=repo_id,
                is_primary=True
            )
        )

    # Make repo_root nullable (backwards compatibility - keep for now)
    # In a future migration, we can remove it entirely
    with op.batch_alter_table('boards', schema=None) as batch_op:
        batch_op.alter_column('repo_root',
                   existing_type=sa.String(length=1024),
                   nullable=True)


def downgrade() -> None:
    # Drop board_repos table
    op.drop_index(op.f('ix_board_repos_repo_id'), table_name='board_repos')
    op.drop_index(op.f('ix_board_repos_board_id'), table_name='board_repos')
    op.drop_table('board_repos')

    # Drop repos table
    op.drop_index(op.f('ix_repos_path'), table_name='repos')
    op.drop_table('repos')

    # Restore repo_root to non-nullable
    with op.batch_alter_table('boards', schema=None) as batch_op:
        batch_op.alter_column('repo_root',
                   existing_type=sa.String(length=1024),
                   nullable=False)
