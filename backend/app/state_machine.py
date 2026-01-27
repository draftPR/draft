"""State machine implementation for ticket workflow.

This module contains the TicketState enum and state transition rules.
Event types and actor types are defined in models/enums.py but re-exported
here for backwards compatibility.
"""

from enum import Enum

# Re-export event types and actor types for backwards compatibility
# The canonical definitions are in models/enums.py
from app.models.enums import ActorType, EventType

__all__ = [
    "TicketState",
    "ActorType",
    "EventType",
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATES",
    "validate_transition",
    "get_allowed_transitions",
    "is_terminal_state",
]


class TicketState(str, Enum):
    """Enum representing valid ticket states."""

    PROPOSED = "proposed"
    PLANNED = "planned"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    NEEDS_HUMAN = "needs_human"
    BLOCKED = "blocked"
    DONE = "done"
    ABANDONED = "abandoned"


# Allowed state transitions map
# Key: current state, Value: list of valid next states
ALLOWED_TRANSITIONS: dict[TicketState, list[TicketState]] = {
    TicketState.PROPOSED: [
        TicketState.PLANNED,
        TicketState.ABANDONED,
    ],
    TicketState.PLANNED: [
        TicketState.PROPOSED,
        TicketState.EXECUTING,
        TicketState.BLOCKED,
        TicketState.ABANDONED,
    ],
    TicketState.EXECUTING: [
        TicketState.VERIFYING,
        TicketState.NEEDS_HUMAN,
        TicketState.BLOCKED,
    ],
    TicketState.VERIFYING: [
        TicketState.EXECUTING,  # Rework needed
        TicketState.NEEDS_HUMAN,  # Verification passed, awaiting human review
        TicketState.BLOCKED,  # Verification failed
    ],
    TicketState.NEEDS_HUMAN: [
        TicketState.EXECUTING,  # Human resolved, back to executing
        TicketState.PLANNED,  # Human replanned
        TicketState.DONE,  # Human approved revision
        TicketState.ABANDONED,
    ],
    TicketState.BLOCKED: [
        TicketState.PLANNED,  # Unblocked, back to planning
        TicketState.EXECUTING,  # Retry execution (e.g., after fixing blocker or retrying failed execution)
        TicketState.ABANDONED,
    ],
    TicketState.DONE: [
        TicketState.EXECUTING,  # Human requested changes on revision
    ],
    TicketState.ABANDONED: [],  # Terminal state
}


def validate_transition(from_state: TicketState, to_state: TicketState) -> bool:
    """
    Validate if a state transition is allowed.

    Args:
        from_state: The current state of the ticket
        to_state: The desired new state

    Returns:
        True if the transition is valid, False otherwise
    """
    if from_state not in ALLOWED_TRANSITIONS:
        return False
    return to_state in ALLOWED_TRANSITIONS[from_state]


def get_allowed_transitions(current_state: TicketState) -> list[TicketState]:
    """
    Get list of valid next states from the current state.

    Args:
        current_state: The current state of the ticket

    Returns:
        List of valid next states
    """
    return ALLOWED_TRANSITIONS.get(current_state, [])


# Terminal states for workspace cleanup and watchdog purposes.
# Note: DONE can transition back to EXECUTING if human requests changes on revision,
# but is still considered "terminal" for cleanup purposes (workspace recreated if needed).
TERMINAL_STATES: set[TicketState] = {TicketState.DONE, TicketState.ABANDONED}


def is_terminal_state(state: TicketState) -> bool:
    """
    Check if a state is a terminal state.

    Args:
        state: The ticket state to check

    Returns:
        True if the state is terminal (DONE or ABANDONED)
    """
    return state in TERMINAL_STATES
