"""add_missing_indexes

Revision ID: 82ecd978cc70
Revises: 774dc335c679
Create Date: 2026-03-01 06:04:37.402741

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "82ecd978cc70"
down_revision: str | None = "015"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Add missing indexes for common query patterns.

    Note: ix_goals_board_id and ix_revisions_job_id already exist
    (created in migrations 012 and 007 respectively), so only the
    composite indexes that are genuinely missing are added here.
    """

    # Composite index for workspace cleanup queries
    # (find active/stale workspaces ordered by creation)
    op.create_index(
        "ix_workspaces_cleanup",
        "workspaces",
        ["cleaned_up_at", "created_at"],
        unique=False,
    )

    # Composite index for rate limit lookups
    # (find entries by client_key that haven't expired)
    op.create_index(
        "ix_rate_limit_entries_lookup",
        "rate_limit_entries",
        ["client_key", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove added indexes."""
    op.drop_index("ix_rate_limit_entries_lookup", table_name="rate_limit_entries")
    op.drop_index("ix_workspaces_cleanup", table_name="workspaces")
