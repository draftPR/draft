"""Smart Kanban Backend - FastAPI Application."""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import init_db
from app.exceptions import (
    InvalidStateTransitionError,
    ResourceNotFoundError,
    SmartKanbanError,
    ValidationError,
)
from app.routers import board_router, evidence_router, goals_router, jobs_router, tickets_router

load_dotenv()

APP_NAME = "Smart Kanban"
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
app.include_router(board_router)
app.include_router(jobs_router)
app.include_router(evidence_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/version")
async def get_version():
    """Return application name and version."""
    return {"app": APP_NAME, "version": APP_VERSION}
