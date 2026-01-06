"""API router for Board endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.ticket import BoardResponse, TicketResponse, TicketsByState
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/board", tags=["board"])


@router.get(
    "",
    response_model=BoardResponse,
    summary="Get the board view",
)
async def get_board(
    db: AsyncSession = Depends(get_db),
) -> BoardResponse:
    """
    Get the board view with all tickets grouped by state.

    Returns tickets organized into columns by state, ordered by priority
    (highest first) within each column.
    """
    service = TicketService(db)
    columns = await service.get_board()

    # Transform to response schema
    response_columns = []
    total_tickets = 0
    for column in columns:
        ticket_responses = [TicketResponse.model_validate(t) for t in column.tickets]
        total_tickets += len(ticket_responses)
        response_columns.append(
            TicketsByState(
                state=column.state,
                tickets=ticket_responses,
            )
        )

    return BoardResponse(
        columns=response_columns,
        total_tickets=total_tickets,
    )
