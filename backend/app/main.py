"""Alma Kanban Backend - FastAPI Application."""

import logging
import os
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.database import init_db
from app.exceptions import (
    ConfigurationError,
    ConflictError,
    InvalidStateTransitionError,
    LLMAPIError,
    ResourceNotFoundError,
    SmartKanbanError,
    ValidationError,
)
from app.middleware import (
    IdempotencyMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    TimeoutMiddleware,
)
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
    repos_router,
    revisions_router,
    tickets_router,
)
from app.routers.agents import router as agents_router
from app.routers.dashboard import router as dashboard_router
from app.routers.executors import router as executors_router
from app.routers.pull_requests import router as pull_requests_router
from app.routers.settings import router as settings_router
from app.routers.webhooks import router as webhooks_router
from app.routers.websocket import router as websocket_router

load_dotenv()

# Initialize Sentry error tracking (only if SENTRY_DSN is set)
_sentry_dsn = os.getenv("SENTRY_DSN")
if _sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=_sentry_dsn,
            environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
            traces_sample_rate=0.1,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        )
    except ImportError:
        pass  # sentry-sdk not installed, skip

APP_NAME = "Alma Kanban"
APP_VERSION = "0.1.0"

logger = logging.getLogger(__name__)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size to prevent OOM attacks."""

    def __init__(self, app, max_body_size: int = 10_000_000):  # 10MB default
        super().__init__(app)
        self.max_body_size = max_body_size

    async def dispatch(self, request: Request, call_next):
        """Check content-length header before processing request."""
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_body_size:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": f"Request body too large. Max size: {self.max_body_size / 1_000_000:.1f}MB",
                        "error_type": "payload_too_large",
                    },
                )
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - initializes database on startup."""
    # Startup: Initialize database tables
    await init_db()

    # Start in-process background worker
    from app.services.sqlite_worker import setup_worker

    worker = setup_worker()
    worker.start()
    logger.info("Background worker started")

    yield

    # Shutdown
    worker.stop()
    logger.info("Application shutdown complete")


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="A local-first Alma Kanban application with state machine workflow",
    lifespan=lifespan,
)

# Security headers (add first, applies to all responses)
app.add_middleware(SecurityHeadersMiddleware)

# Request timeout (600s global timeout, needed for long-running analysis)
app.add_middleware(TimeoutMiddleware, timeout_seconds=600)

# CORS configuration — supports both dev (vite on :5173) and production (same origin)
_frontend_url = os.getenv("FRONTEND_URL")
if not _frontend_url:
    _frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if _frontend_dist.exists():
        _backend_port = os.getenv("PORT", "8000")
        _frontend_url = f"http://localhost:{_backend_port}"
    else:
        _frontend_url = "http://localhost:5173"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[_frontend_url, "http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request size limits (prevent DoS)
app.add_middleware(RequestSizeLimitMiddleware, max_body_size=10_000_000)

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


@app.exception_handler(ConflictError)
async def conflict_error_handler(
    request: Request, exc: ConflictError
) -> JSONResponse:
    """Handle conflict errors (e.g., duplicate operations, stale state)."""
    return JSONResponse(
        status_code=409,
        content={
            "detail": exc.message,
            "error_type": "conflict",
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
async def llm_api_error_handler(request: Request, exc: LLMAPIError) -> JSONResponse:
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
    """Handle generic Alma Kanban errors."""
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "error_type": "internal_error",
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler that prevents information leakage (SECURITY).

    In production, sanitizes errors to prevent exposing internal details.
    In development, includes full traceback for debugging.
    """
    # Log full error internally (for debugging/monitoring)
    logger.error(
        f"Unhandled exception in {request.method} {request.url.path}",
        exc_info=exc,
        extra={
            "path": request.url.path,
            "method": request.method,
            "client": request.client.host if request.client else None,
        },
    )

    # Return sanitized error to client
    if os.getenv("APP_ENV") == "production":
        # PRODUCTION: Never expose internal details
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error_type": "internal_error",
                # NO stack trace or exception details
            },
        )
    else:
        # DEVELOPMENT: Include details for debugging
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "error_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            },
        )


# Health check endpoints (for monitoring/load balancers)
@app.get("/health", tags=["monitoring"])
async def healthcheck() -> JSONResponse:
    """Health check endpoint for load balancers and monitoring.

    Checks:
    - Basic service availability

    Returns 200 OK if service is running.
    """
    from datetime import UTC, datetime

    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "timestamp": datetime.now(UTC).isoformat(),
            "service": APP_NAME,
            "version": APP_VERSION,
        },
    )


@app.get("/health/detailed", tags=["monitoring"])
async def healthcheck_detailed(request: Request) -> JSONResponse:
    """Detailed health check with dependency checks.

    Checks:
    - Database connectivity
    - Redis connectivity
    - Disk space

    Returns 200 if all healthy, 503 if any component unhealthy.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func, select

    from app.database import get_db

    checks = {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "service": APP_NAME,
        "version": APP_VERSION,
        "checks": {},
    }

    # Check database
    try:
        async for db in get_db():
            await db.execute(select(1))
            checks["checks"]["database"] = "ok"
            break
    except Exception as e:
        checks["status"] = "unhealthy"
        checks["checks"]["database"] = f"error: {str(e)}"
        logger.error(f"Database health check failed: {e}")

    # Check disk space
    try:
        import shutil

        stat = shutil.disk_usage("/")
        free_percent = (stat.free / stat.total) * 100
        checks["checks"]["disk_space"] = f"{free_percent:.1f}% free"
        if free_percent < 10:
            checks["status"] = "degraded"
            logger.warning(f"Low disk space: {free_percent:.1f}% free")
    except Exception as e:
        checks["checks"]["disk_space"] = f"error: {str(e)}"
        logger.error(f"Disk space check failed: {e}")

    # Check worker health
    try:
        from app.services.sqlite_worker import _worker

        worker_running = _worker is not None and _worker._running
        checks["checks"]["worker"] = "running" if worker_running else "stopped"
        if not worker_running:
            checks["status"] = "degraded"
    except Exception as e:
        checks["checks"]["worker"] = f"error: {str(e)}"

    # Check last planner tick time
    try:
        async for db in get_db():
            from app.models.planner_lock import PlannerLock

            lock_result = await db.execute(
                select(PlannerLock).where(PlannerLock.lock_key == "planner_tick")
            )
            lock = lock_result.scalar_one_or_none()
            if lock:
                checks["checks"]["planner_lock"] = {
                    "held": True,
                    "acquired_at": lock.acquired_at.isoformat()
                    if lock.acquired_at
                    else None,
                }
            else:
                checks["checks"]["planner_lock"] = {"held": False}

            # Count stuck jobs (RUNNING longer than 30 minutes)
            from app.models.job import Job, JobStatus

            thirty_min_ago = datetime.now(UTC) - timedelta(minutes=30)
            stuck_result = await db.execute(
                select(func.count(Job.id)).where(
                    Job.status == JobStatus.RUNNING.value,
                    Job.started_at < thirty_min_ago,
                )
            )
            stuck_count = stuck_result.scalar() or 0
            checks["checks"]["stuck_jobs"] = stuck_count
            if stuck_count > 0:
                checks["status"] = "degraded"
            break
    except Exception as e:
        checks["checks"]["worker_details"] = f"error: {str(e)}"

    status_code = 200 if checks["status"] == "healthy" else 503
    return JSONResponse(content=checks, status_code=status_code)


@app.get("/readiness", tags=["monitoring"])
async def readiness() -> JSONResponse:
    """Readiness check for Kubernetes/container orchestration."""
    return JSONResponse(status_code=200, content={"status": "ready"})


@app.get("/liveness", tags=["monitoring"])
async def liveness() -> JSONResponse:
    """Liveness check for Kubernetes/container orchestration."""
    return JSONResponse(status_code=200, content={"status": "alive"})


# Include routers
app.include_router(goals_router)
app.include_router(tickets_router)
app.include_router(boards_router)  # New multi-board endpoints (/boards/...)
app.include_router(board_legacy_router)  # Legacy kanban view (/board)
app.include_router(repos_router)  # Repository discovery and management
app.include_router(jobs_router)
app.include_router(evidence_router)
app.include_router(planner_router)
app.include_router(revisions_router)
app.include_router(merge_router)
app.include_router(maintenance_router)
app.include_router(debug_router)
app.include_router(agents_router)  # AI agent management
app.include_router(dashboard_router)  # Sprint dashboard and metrics
app.include_router(executors_router)  # Executor plugin management
app.include_router(settings_router)  # Global settings (smartkanban.yaml)
app.include_router(websocket_router)  # WebSocket real-time updates
app.include_router(pull_requests_router)  # GitHub PR integration
app.include_router(webhooks_router)  # Webhook notifications for ticket changes


@app.get("/version")
async def get_version():
    """Return application name and version."""
    return {"app": APP_NAME, "version": APP_VERSION}


# Serve pre-built frontend (production / npx mode).
# Must be AFTER all API routes so /health, /api/*, /ws/* take priority.
_frontend_dist_path = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist_path.exists():
    # Serve static assets (js, css, images)
    app.mount(
        "/assets",
        StaticFiles(directory=_frontend_dist_path / "assets"),
        name="frontend-assets",
    )

    # SPA catch-all: serve index.html for all non-API, non-asset routes
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the SPA index.html for client-side routing."""
        file_path = _frontend_dist_path / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist_path / "index.html")
