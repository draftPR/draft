"""Common Pydantic schemas for API responses."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """Schema for error responses."""

    detail: str
    error_type: str | None = None


class SuccessResponse(BaseModel):
    """Schema for simple success responses."""

    message: str
    success: bool = True


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper.

    Used for list endpoints that support pagination via page/limit params.
    """

    items: list[T]
    total: int = Field(description="Total number of items matching the query")
    page: int = Field(description="Current page number (1-based)")
    limit: int = Field(description="Number of items per page")
