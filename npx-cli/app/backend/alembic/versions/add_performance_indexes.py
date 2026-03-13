"""Add performance indexes for hot paths.

Revision ID: perf_indexes_001
Revises: 8ef5054dc280
Create Date: 2026-01-28

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "perf_indexes_001"
down_revision = "8ef5054dc280"
branch_labels = None
depends_on = None


def upgrade():
    """Add performance indexes for frequently queried paths."""

    # Hot path: Get jobs by status and created_at (for queue status, watchdog)
    op.create_index(
        "idx_jobs_status_created",
        "jobs",
        ["status", "created_at"],
        unique=False,
    )

    # Hot path: Get tickets by state and priority (for board view)
    op.create_index(
        "idx_tickets_state_priority",
        "tickets",
        ["state", "priority"],
        unique=False,
    )

    # Hot path: Get open revisions for a ticket
    op.create_index(
        "idx_revisions_ticket_status",
        "revisions",
        ["ticket_id", "status"],
        unique=False,
    )

    # Hot path: Find evidence by job_id and kind (for diffs)
    op.create_index(
        "idx_evidence_job_kind",
        "evidence",
        ["job_id", "kind"],
        unique=False,
    )

    # Hot path: Job watchdog queries (find stale jobs by heartbeat)
    op.create_index(
        "idx_jobs_status_heartbeat",
        "jobs",
        ["status", "last_heartbeat_at"],
        unique=False,
    )

    # Hot path: Get jobs for a ticket (ordered by creation)
    op.create_index(
        "idx_jobs_ticket_created",
        "jobs",
        ["ticket_id", "created_at"],
        unique=False,
    )

    # Hot path: Get events for a ticket (audit log)
    op.create_index(
        "idx_ticket_events_ticket_created",
        "ticket_events",
        ["ticket_id", "created_at"],
        unique=False,
    )

    # Hot path: Rate limiting queries (count recent jobs by ticket/kind/time)
    op.create_index(
        "idx_jobs_ticket_kind_created",
        "jobs",
        ["ticket_id", "kind", "created_at"],
        unique=False,
    )


def downgrade():
    """Remove performance indexes."""
    op.drop_index("idx_jobs_ticket_kind_created", table_name="jobs")
    op.drop_index("idx_ticket_events_ticket_created", table_name="ticket_events")
    op.drop_index("idx_jobs_ticket_created", table_name="jobs")
    op.drop_index("idx_jobs_status_heartbeat", table_name="jobs")
    op.drop_index("idx_evidence_job_kind", table_name="evidence")
    op.drop_index("idx_revisions_ticket_status", table_name="revisions")
    op.drop_index("idx_tickets_state_priority", table_name="tickets")
    op.drop_index("idx_jobs_status_created", table_name="jobs")
