"""Common Pydantic schemas for API responses."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Schema for error responses."""

    detail: str
    error_type: str | None = None


class SuccessResponse(BaseModel):
    """Schema for simple success responses."""

    message: str
    success: bool = True

