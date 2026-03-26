"""Add agent teams for multi-agent collaboration.

Revision ID: 017
Revises: 016
Create Date: 2026-03-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Agent teams (1:1 with board)
    op.create_table(
        "agent_teams",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "board_id",
            sa.String(36),
            sa.ForeignKey("boards.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "name", sa.String(255), nullable=False, server_default="Default Team"
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_agent_teams_board_id", "agent_teams", ["board_id"])

    # Agent team members (N per team)
    op.create_table(
        "agent_team_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "team_id",
            sa.String(36),
            sa.ForeignKey("agent_teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column(
            "executor_type", sa.String(50), nullable=False, server_default="claude"
        ),
        sa.Column("behavior_prompt", sa.Text, nullable=True),
        sa.Column(
            "receive_mode", sa.String(20), nullable=False, server_default="mentions"
        ),
        sa.Column("is_required", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_agent_team_members_team_id", "agent_team_members", ["team_id"])

    # Running agent sessions (per ticket execution)
    op.create_table(
        "team_agent_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.String(36),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_member_id",
            sa.String(36),
            sa.ForeignKey("agent_team_members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tmux_session_name", sa.String(255), nullable=False, unique=True),
        sa.Column("session_uuid", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("log_path", sa.String(1024), nullable=True),
        sa.Column("last_pulse_status", sa.String(500), nullable=True),
        sa.Column("last_pulse_summary", sa.String(500), nullable=True),
        sa.Column("last_pulse_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_team_agent_sessions_ticket_id", "team_agent_sessions", ["ticket_id"]
    )
    op.create_index(
        "ix_team_agent_sessions_team_member_id",
        "team_agent_sessions",
        ["team_member_id"],
    )
    op.create_index("ix_team_agent_sessions_job_id", "team_agent_sessions", ["job_id"])

    # Message board for inter-agent communication
    op.create_table(
        "board_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "board_id",
            sa.String(36),
            sa.ForeignKey("boards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ticket_id",
            sa.String(36),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sender_session_id", sa.String(36), nullable=False),
        sa.Column("sender_role", sa.String(255), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_board_messages_board_id", "board_messages", ["board_id"])
    op.create_index("ix_board_messages_ticket_id", "board_messages", ["ticket_id"])

    # Cursor tracking for message reads
    op.create_table(
        "board_message_cursors",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("board_id", sa.String(36), nullable=False),
        sa.Column("ticket_id", sa.String(36), nullable=False),
        sa.Column("last_read_id", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_board_message_cursors_session_id",
        "board_message_cursors",
        ["session_id"],
    )
    op.create_index(
        "ix_board_message_cursors_lookup",
        "board_message_cursors",
        ["session_id", "board_id", "ticket_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_board_message_cursors_lookup", table_name="board_message_cursors")
    op.drop_index(
        "ix_board_message_cursors_session_id", table_name="board_message_cursors"
    )
    op.drop_table("board_message_cursors")

    op.drop_index("ix_board_messages_ticket_id", table_name="board_messages")
    op.drop_index("ix_board_messages_board_id", table_name="board_messages")
    op.drop_table("board_messages")

    op.drop_index("ix_team_agent_sessions_job_id", table_name="team_agent_sessions")
    op.drop_index(
        "ix_team_agent_sessions_team_member_id", table_name="team_agent_sessions"
    )
    op.drop_index("ix_team_agent_sessions_ticket_id", table_name="team_agent_sessions")
    op.drop_table("team_agent_sessions")

    op.drop_index("ix_agent_team_members_team_id", table_name="agent_team_members")
    op.drop_table("agent_team_members")

    op.drop_index("ix_agent_teams_board_id", table_name="agent_teams")
    op.drop_table("agent_teams")
