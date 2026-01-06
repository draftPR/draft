"""Pydantic schemas for Smart Kanban API."""

from app.schemas.common import ErrorResponse, SuccessResponse
from app.schemas.evidence import (
    EvidenceDetailResponse,
    EvidenceKind,
    EvidenceListResponse,
    EvidenceResponse,
)
from app.schemas.goal import GoalCreate, GoalListResponse, GoalResponse
from app.schemas.job import (
    CancelJobResponse,
    JobCreateResponse,
    JobDetailResponse,
    JobKind,
    JobListResponse,
    JobResponse,
    JobStatus,
)
from app.schemas.ticket import (
    BoardResponse,
    TicketCreate,
    TicketDetailResponse,
    TicketResponse,
    TicketsByState,
    TicketTransition,
    TicketWithGoal,
)
from app.schemas.ticket_event import TicketEventListResponse, TicketEventResponse
from app.schemas.workspace import WorkspaceResponse

__all__ = [
    "GoalCreate",
    "GoalResponse",
    "GoalListResponse",
    "TicketCreate",
    "TicketResponse",
    "TicketDetailResponse",
    "TicketTransition",
    "TicketWithGoal",
    "TicketsByState",
    "BoardResponse",
    "TicketEventResponse",
    "TicketEventListResponse",
    "ErrorResponse",
    "SuccessResponse",
    "EvidenceKind",
    "EvidenceResponse",
    "EvidenceDetailResponse",
    "EvidenceListResponse",
    "JobKind",
    "JobStatus",
    "JobResponse",
    "JobDetailResponse",
    "JobListResponse",
    "JobCreateResponse",
    "CancelJobResponse",
    "WorkspaceResponse",
]
