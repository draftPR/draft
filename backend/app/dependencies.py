"""Reusable FastAPI dependencies for validation and DI."""

from typing import Annotated

from fastapi import Path

from app.utils.validators import validate_uuid


def ValidatedUUID(field_name: str):
    """Create an annotated type for UUID path parameter validation.

    Creates a type annotation that validates UUID format and returns the normalized UUID string.

    Usage:
        @router.get("/{ticket_id}")
        async def get_ticket(
            ticket_id: Annotated[str, ValidatedUUID("ticket_id")],
            db: AsyncSession = Depends(get_db),
        ):
            # ticket_id is guaranteed to be a valid UUID

    Args:
        field_name: Name of the field for error messages (e.g., "ticket_id")

    Returns:
        A Path dependency that validates and returns the UUID
    """
    def validator(value: str) -> str:
        return validate_uuid(value, field_name)

    return Path(..., description=f"Valid UUID for {field_name}")


# Type aliases for common ID types - use with Annotated
# Example: ticket_id: TicketID
TicketID = Annotated[str, Path(..., description="Valid UUID for ticket_id")]
JobID = Annotated[str, Path(..., description="Valid UUID for job_id")]
GoalID = Annotated[str, Path(..., description="Valid UUID for goal_id")]
BoardID = Annotated[str, Path(..., description="Valid UUID for board_id")]
RevisionID = Annotated[str, Path(..., description="Valid UUID for revision_id")]
EvidenceID = Annotated[str, Path(..., description="Valid UUID for evidence_id")]
