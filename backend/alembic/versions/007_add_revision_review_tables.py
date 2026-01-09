"""Add revision and review tables for PR-like human review loop.

Revision ID: 007
Revises: 006
Create Date: 2026-01-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create revisions table
    op.create_table(
        "revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.String(36),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column(
            "diff_stat_evidence_id",
            sa.String(36),
            sa.ForeignKey("evidence.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "diff_patch_evidence_id",
            sa.String(36),
            sa.ForeignKey("evidence.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("ticket_id", "number", name="uq_revision_ticket_number"),
    )
    op.create_index("ix_revisions_ticket_id", "revisions", ["ticket_id"])
    op.create_index("ix_revisions_job_id", "revisions", ["job_id"])
    op.create_index("ix_revisions_status", "revisions", ["status"])

    # Create review_comments table
    op.create_table(
        "review_comments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "revision_id",
            sa.String(36),
            sa.ForeignKey("revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("anchor", sa.String(40), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("author_type", sa.String(20), nullable=False, server_default="human"),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_review_comments_revision_id", "review_comments", ["revision_id"])
    op.create_index("ix_review_comments_anchor", "review_comments", ["anchor"])
    op.create_index(
        "ix_review_comments_revision_resolved",
        "review_comments",
        ["revision_id", "resolved"],
    )

    # Create review_summaries table
    op.create_table(
        "review_summaries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "revision_id",
            sa.String(36),
            sa.ForeignKey("revisions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_review_summaries_revision_id", "review_summaries", ["revision_id"])


def downgrade() -> None:
    op.drop_table("review_summaries")
    op.drop_table("review_comments")
    op.drop_table("revisions")

