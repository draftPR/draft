"""Add agent sessions and messages tables for conversation continuity and cost tracking.

Revision ID: 014
Revises: 013
Create Date: 2026-01-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '014'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name: str) -> bool:
    """Check if a table exists in SQLite."""
    from alembic import op
    conn = op.get_bind()
    result = conn.execute(
        sa.text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    )
    return result.fetchone() is not None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a SQLite table."""
    from alembic import op
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table_name})"))
    columns = [row[1] for row in result.fetchall()]
    return column_name in columns


def index_exists(index_name: str) -> bool:
    """Check if an index exists in SQLite."""
    from alembic import op
    conn = op.get_bind()
    result = conn.execute(
        sa.text(f"SELECT name FROM sqlite_master WHERE type='index' AND name='{index_name}'")
    )
    return result.fetchone() is not None


def upgrade() -> None:
    # Create agent_sessions table if it doesn't exist
    if not table_exists('agent_sessions'):
        op.create_table(
            'agent_sessions',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('ticket_id', sa.String(36), sa.ForeignKey('tickets.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('job_id', sa.String(36), sa.ForeignKey('jobs.id', ondelete='SET NULL'), nullable=True, index=True),
            
            # Agent identification
            sa.Column('agent_type', sa.String(50), nullable=False),
            sa.Column('agent_session_id', sa.String(255), nullable=True),  # External session ID
            
            # Session state
            sa.Column('is_active', sa.Boolean, default=True, nullable=False),
            sa.Column('turn_count', sa.Integer, default=0, nullable=False),
            
            # Token tracking
            sa.Column('total_input_tokens', sa.Integer, default=0, nullable=False),
            sa.Column('total_output_tokens', sa.Integer, default=0, nullable=False),
            sa.Column('estimated_cost_usd', sa.Float, default=0.0, nullable=False),
            
            # Context
            sa.Column('last_prompt', sa.Text, nullable=True),
            sa.Column('last_response_summary', sa.Text, nullable=True),
            sa.Column('metadata', sa.JSON, nullable=True),
            
            # Timestamps
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            sa.Column('ended_at', sa.DateTime, nullable=True),
        )
    
    # Create agent_messages table if it doesn't exist
    if not table_exists('agent_messages'):
        op.create_table(
            'agent_messages',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('session_id', sa.String(36), sa.ForeignKey('agent_sessions.id', ondelete='CASCADE'), nullable=False, index=True),
            
            # Message content
            sa.Column('role', sa.String(20), nullable=False),  # user, assistant, system, tool
            sa.Column('content', sa.Text, nullable=False),
            
            # Token counts
            sa.Column('input_tokens', sa.Integer, default=0, nullable=False),
            sa.Column('output_tokens', sa.Integer, default=0, nullable=False),
            
            # Tool tracking
            sa.Column('tool_name', sa.String(100), nullable=True),
            sa.Column('tool_input', sa.JSON, nullable=True),
            sa.Column('tool_output', sa.Text, nullable=True),
            
            # Metadata
            sa.Column('metadata', sa.JSON, nullable=True),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        )
    
    # Create cost_budgets table if it doesn't exist
    if not table_exists('cost_budgets'):
        op.create_table(
            'cost_budgets',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('goal_id', sa.String(36), sa.ForeignKey('goals.id', ondelete='CASCADE'), nullable=True, index=True),
            
            # Budget limits
            sa.Column('daily_budget', sa.Float, nullable=True),
            sa.Column('weekly_budget', sa.Float, nullable=True),
            sa.Column('monthly_budget', sa.Float, nullable=True),
            sa.Column('total_budget', sa.Float, nullable=True),
            
            # Alerts
            sa.Column('warning_threshold', sa.Float, default=0.8, nullable=False),  # 80%
            sa.Column('pause_on_exceed', sa.Boolean, default=False, nullable=False),
            
            # Timestamps
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )
    
    # Add agent_type column to jobs table if it doesn't exist
    if not column_exists('jobs', 'agent_type'):
        op.add_column('jobs', sa.Column('agent_type', sa.String(50), nullable=True))
    if not column_exists('jobs', 'agent_session_id'):
        op.add_column('jobs', sa.Column('agent_session_id', sa.String(36), nullable=True))
    
    # Add cost tracking to tickets if it doesn't exist
    if not column_exists('tickets', 'total_cost_usd'):
        op.add_column('tickets', sa.Column('total_cost_usd', sa.Float, default=0.0, nullable=True))
    
    # Create indexes for performance if they don't exist
    if not index_exists('ix_agent_sessions_created_at'):
        op.create_index('ix_agent_sessions_created_at', 'agent_sessions', ['created_at'])
    if not index_exists('ix_agent_sessions_agent_type'):
        op.create_index('ix_agent_sessions_agent_type', 'agent_sessions', ['agent_type'])


def downgrade() -> None:
    # Drop indexes if they exist
    if index_exists('ix_agent_sessions_agent_type'):
        op.drop_index('ix_agent_sessions_agent_type', 'agent_sessions')
    if index_exists('ix_agent_sessions_created_at'):
        op.drop_index('ix_agent_sessions_created_at', 'agent_sessions')
    
    # Drop columns from existing tables if they exist
    if column_exists('tickets', 'total_cost_usd'):
        op.drop_column('tickets', 'total_cost_usd')
    if column_exists('jobs', 'agent_session_id'):
        op.drop_column('jobs', 'agent_session_id')
    if column_exists('jobs', 'agent_type'):
        op.drop_column('jobs', 'agent_type')
    
    # Drop new tables if they exist
    if table_exists('cost_budgets'):
        op.drop_table('cost_budgets')
    if table_exists('agent_messages'):
        op.drop_table('agent_messages')
    if table_exists('agent_sessions'):
        op.drop_table('agent_sessions')
