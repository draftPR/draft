"""add_sqlite_backend_tables

Revision ID: c3a8f1b2d4e5
Revises: b10fb0b62240
Create Date: 2026-02-15 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3a8f1b2d4e5"
down_revision: str | None = "b10fb0b62240"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Job queue (replaces Celery broker)
    op.create_table(
        "job_queue",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("args_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="pending"
        ),
        sa.Column("claimed_by", sa.String(255), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_job_queue_status", "job_queue", ["status"])
    op.create_index(
        "ix_job_queue_claim_order",
        "job_queue",
        ["status", "priority", "created_at"],
    )

    # Idempotency cache (replaces Redis SETNX + result cache)
    op.create_table(
        "idempotency_cache",
        sa.Column("cache_key", sa.String(512), primary_key=True),
        sa.Column("lock_value", sa.Text(), nullable=True),
        sa.Column("result_value", sa.Text(), nullable=True),
        sa.Column("lock_expires_at", sa.DateTime(), nullable=True),
        sa.Column("result_expires_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Rate limit entries (replaces Redis sorted sets)
    op.create_table(
        "rate_limit_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("client_key", sa.String(255), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("recorded_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
    )
    op.create_index(
        "ix_rate_limit_entries_client_key",
        "rate_limit_entries",
        ["client_key"],
    )
    op.create_index(
        "ix_rate_limit_entries_expires_at",
        "rate_limit_entries",
        ["expires_at"],
    )

    # KV store (replaces Redis GET/SET for queued messages)
    op.create_table(
        "kv_store",
        sa.Column("key", sa.String(512), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("kv_store")
    op.drop_table("rate_limit_entries")
    op.drop_table("idempotency_cache")
    op.drop_table("job_queue")
