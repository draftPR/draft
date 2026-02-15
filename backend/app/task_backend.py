"""Task backend configuration.

Determines whether to use SQLite or Redis for background tasks,
idempotency, rate limiting, and message queuing.

TASK_BACKEND=sqlite (default): Zero external dependencies, uses SQLite.
TASK_BACKEND=redis: Uses Redis for cross-process communication.

When SMART_KANBAN_MODE=local, auto-uses sqlite regardless of TASK_BACKEND.
"""

import os

_SMART_KANBAN_MODE = os.getenv("SMART_KANBAN_MODE", "")
_TASK_BACKEND = os.getenv("TASK_BACKEND", "sqlite")


def get_task_backend() -> str:
    """Return 'sqlite' or 'redis'."""
    if _SMART_KANBAN_MODE == "local":
        return "sqlite"
    return _TASK_BACKEND.lower()


def is_sqlite_backend() -> bool:
    """True when using SQLite for task infrastructure."""
    return get_task_backend() == "sqlite"


def is_redis_backend() -> bool:
    """True when using Redis for task infrastructure."""
    return get_task_backend() == "redis"
