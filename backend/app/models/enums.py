"""Shared enumerations for Alma Kanban models.

This file contains event types and other enums that are NOT part of the
ticket state machine. The state machine (TicketState, transitions) lives
in state_machine.py. Event types are audit log entries, not state rules.
"""

from enum import StrEnum


class EventType(StrEnum):
    """Enum representing types of ticket events.

    These are audit log event types, NOT state transition rules.
    State transitions are governed by state_machine.py.
    """

    # Core lifecycle events
    CREATED = "created"
    TRANSITIONED = "transitioned"
    UPDATED = "updated"
    COMMENT = "comment"

    # Merge lifecycle events
    MERGE_REQUESTED = "merge_requested"
    MERGE_SUCCEEDED = "merge_succeeded"
    MERGE_FAILED = "merge_failed"

    # Cleanup events (distinct types for clear analytics/UX)
    WORKTREE_CLEANED = "worktree_cleaned"
    WORKTREE_CLEANUP_FAILED = "worktree_cleanup_failed"


class ActorType(StrEnum):
    """Enum representing who performed an action."""

    HUMAN = "human"
    PLANNER = "planner"
    SYSTEM = "system"
    EXECUTOR = "executor"

