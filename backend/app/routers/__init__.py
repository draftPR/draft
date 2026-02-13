"""API routers for Smart Kanban."""

from app.routers.board import legacy_router as board_legacy_router
from app.routers.board import router as boards_router
from app.routers.debug import router as debug_router
from app.routers.evidence import router as evidence_router
from app.routers.goals import router as goals_router
from app.routers.jobs import router as jobs_router
from app.routers.maintenance import router as maintenance_router
from app.routers.merge import router as merge_router
from app.routers.planner import router as planner_router
from app.routers.repos import router as repos_router
from app.routers.revisions import router as revisions_router
from app.routers.tickets import router as tickets_router

__all__ = [
    "goals_router",
    "tickets_router",
    "boards_router",
    "board_legacy_router",
    "repos_router",
    "jobs_router",
    "evidence_router",
    "planner_router",
    "revisions_router",
    "merge_router",
    "maintenance_router",
    "debug_router",
]
