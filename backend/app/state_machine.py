"""State machine implementation for ticket workflow."""

from enum import Enum


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


class ActorType(str, Enum):
    """Enum representing the type of actor performing an action."""

    HUMAN = "human"
    PLANNER = "planner"
    SYSTEM = "system"
    EXECUTOR = "executor"


class EventType(str, Enum):
    """Enum representing types of ticket events."""

    CREATED = "created"
    TRANSITIONED = "transitioned"
    UPDATED = "updated"
    COMMENT = "comment"


# Allowed state transitions map
# Key: current state, Value: list of valid next states
ALLOWED_TRANSITIONS: dict[TicketState, list[TicketState]] = {
    TicketState.PROPOSED: [
        TicketState.PLANNED,
        TicketState.ABANDONED,
    ],
    TicketState.PLANNED: [
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
        TicketState.DONE,
        TicketState.EXECUTING,  # Rework needed
        TicketState.NEEDS_HUMAN,
        TicketState.BLOCKED,  # Verification failed
    ],
    TicketState.NEEDS_HUMAN: [
        TicketState.EXECUTING,  # Human resolved, back to executing
        TicketState.PLANNED,  # Human replanned
        TicketState.ABANDONED,
    ],
    TicketState.BLOCKED: [
        TicketState.PLANNED,  # Unblocked, back to planning
        TicketState.ABANDONED,
    ],
    TicketState.DONE: [],  # Terminal state
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


# Terminal states where tickets cannot transition further
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
