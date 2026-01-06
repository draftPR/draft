"""API routers for Smart Kanban."""

from app.routers.board import router as board_router
from app.routers.evidence import router as evidence_router
from app.routers.goals import router as goals_router
from app.routers.jobs import router as jobs_router
from app.routers.tickets import router as tickets_router

__all__ = ["goals_router", "tickets_router", "board_router", "jobs_router", "evidence_router"]
