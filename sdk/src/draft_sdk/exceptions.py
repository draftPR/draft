"""Exceptions for the Draft SDK."""

from __future__ import annotations


class DraftError(Exception):
    """Base exception for the Draft SDK."""


class DraftAPIError(DraftError):
    """Raised when the Draft API returns a non-2xx response."""

    def __init__(self, status_code: int, detail: str, error_type: str | None = None):
        self.status_code = status_code
        self.detail = detail
        self.error_type = error_type
        super().__init__(f"HTTP {status_code}: {detail}")


class DraftNotFoundError(DraftAPIError):
    """Raised on 404 responses."""

    def __init__(self, detail: str = "Not found"):
        super().__init__(404, detail)


class DraftConflictError(DraftAPIError):
    """Raised on 409 responses (idempotency conflict)."""

    def __init__(self, detail: str = "Conflict"):
        super().__init__(409, detail)


class DraftValidationError(DraftAPIError):
    """Raised on 422 responses."""

    def __init__(self, detail: str = "Validation error"):
        super().__init__(422, detail)


class DraftTimeoutError(DraftError):
    """Raised when a polling operation exceeds its timeout."""

    def __init__(self, message: str = "Operation timed out"):
        super().__init__(message)


class DraftConnectionError(DraftError):
    """Raised when the SDK cannot connect to the Draft server."""

    def __init__(self, message: str = "Cannot connect to Draft server"):
        super().__init__(message)
