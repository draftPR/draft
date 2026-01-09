"""Smart Kanban Backend - FastAPI Application."""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import init_db
from app.exceptions import (
    ConfigurationError,
    InvalidStateTransitionError,
    LLMAPIError,
    ResourceNotFoundError,
    SmartKanbanError,
    ValidationError,
)
from app.middleware import IdempotencyMiddleware, RateLimitMiddleware
from app.routers import (
    board_legacy_router,
    boards_router,
    debug_router,
    evidence_router,
    goals_router,
    jobs_router,
    maintenance_router,
    merge_router,
    planner_router,
    revisions_router,
    tickets_router,
)

load_dotenv()

APP_NAME = "Orion Kanban"
APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - initializes database on startup."""
    # Startup: Initialize database tables
    await init_db()
    yield
    # Shutdown: cleanup if needed


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="A local-first Smart Kanban application with state machine workflow",
    lifespan=lifespan,
)

# CORS configuration for local development
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting for LLM endpoints (10 req/min)
app.add_middleware(RateLimitMiddleware)

# Idempotency support for expensive operations
app.add_middleware(IdempotencyMiddleware)


# Exception handlers
@app.exception_handler(ResourceNotFoundError)
async def resource_not_found_handler(
    request: Request, exc: ResourceNotFoundError
) -> JSONResponse:
    """Handle resource not found errors."""
    return JSONResponse(
        status_code=404,
        content={
            "detail": exc.message,
            "error_type": "resource_not_found",
        },
    )


@app.exception_handler(InvalidStateTransitionError)
async def invalid_transition_handler(
    request: Request, exc: InvalidStateTransitionError
) -> JSONResponse:
    """Handle invalid state transition errors."""
    return JSONResponse(
        status_code=400,
        content={
            "detail": exc.message,
            "error_type": "invalid_state_transition",
            "from_state": exc.from_state,
            "to_state": exc.to_state,
        },
    )


@app.exception_handler(ValidationError)
async def validation_error_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """Handle validation errors."""
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.message,
            "error_type": "validation_error",
        },
    )


@app.exception_handler(ConfigurationError)
async def configuration_error_handler(
    request: Request, exc: ConfigurationError
) -> JSONResponse:
    """Handle configuration errors (e.g., missing API keys)."""
    return JSONResponse(
        status_code=400,
        content={
            "detail": exc.message,
            "error_type": "configuration_error",
        },
    )


@app.exception_handler(LLMAPIError)
async def llm_api_error_handler(
    request: Request, exc: LLMAPIError
) -> JSONResponse:
    """Handle LLM API errors."""
    return JSONResponse(
        status_code=502,
        content={
            "detail": exc.message,
            "error_type": "llm_api_error",
            "provider": exc.provider,
        },
    )


@app.exception_handler(SmartKanbanError)
async def smart_kanban_error_handler(
    request: Request, exc: SmartKanbanError
) -> JSONResponse:
    """Handle generic Smart Kanban errors."""
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "error_type": "internal_error",
        },
    )


# Include routers
app.include_router(goals_router)
app.include_router(tickets_router)
app.include_router(boards_router)  # New multi-board endpoints (/boards/...)
app.include_router(board_legacy_router)  # Legacy kanban view (/board)
app.include_router(jobs_router)
app.include_router(evidence_router)
app.include_router(planner_router)
app.include_router(revisions_router)
app.include_router(merge_router)
app.include_router(maintenance_router)
app.include_router(debug_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/version")
async def get_version():
    """Return application name and version."""
    return {"app": APP_NAME, "version": APP_VERSION}
