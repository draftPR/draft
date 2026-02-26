"""Input validation utilities for API requests."""

import uuid

from fastapi import HTTPException


def validate_uuid(value: str, field_name: str = "ID") -> str:
    """Validate that a string is a valid UUID format.

    Args:
        value: String to validate
        field_name: Field name for error message

    Returns:
        The validated UUID string (normalized)

    Raises:
        HTTPException: 400 if not a valid UUID
    """
    try:
        # Parse and normalize UUID
        parsed = uuid.UUID(value)
        return str(parsed)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: must be a valid UUID (got: {value})",
        )


def validate_uuids(values: list[str], field_name: str = "IDs") -> list[str]:
    """Validate a list of UUIDs.

    Args:
        values: List of UUID strings to validate
        field_name: Field name for error message

    Returns:
        List of validated UUID strings

    Raises:
        HTTPException: 400 if any UUID is invalid
    """
    validated = []
    for value in values:
        try:
            validated.append(validate_uuid(value, field_name))
        except HTTPException:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid {field_name}: '{value}' is not a valid UUID",
            )
    return validated
