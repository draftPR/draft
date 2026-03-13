"""Draft SDK — Python client for the Draft AI-powered kanban board."""

from .client import DraftClient
from .exceptions import (
    DraftAPIError,
    DraftConflictError,
    DraftConnectionError,
    DraftError,
    DraftNotFoundError,
    DraftTimeoutError,
    DraftValidationError,
)
from .models import (
    Board,
    BulkAcceptResult,
    Goal,
    GoalProgress,
    GoalResult,
    Job,
    Revision,
    ReviewComment,
    ReviewSummary,
    RevisionDiff,
    Ticket,
)

__all__ = [
    "DraftClient",
    # Models
    "Board",
    "BulkAcceptResult",
    "Goal",
    "GoalProgress",
    "GoalResult",
    "Job",
    "Revision",
    "ReviewComment",
    "ReviewSummary",
    "RevisionDiff",
    "Ticket",
    # Exceptions
    "DraftAPIError",
    "DraftConflictError",
    "DraftConnectionError",
    "DraftError",
    "DraftNotFoundError",
    "DraftTimeoutError",
    "DraftValidationError",
]

__version__ = "0.1.0"
