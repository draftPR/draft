"""Cost-based rate limiting middleware with pluggable backend (Redis or SQLite).

CRITICAL: Rate limiting gates on ESTIMATED cost BEFORE expensive work.
Actual cost is emitted as telemetry only (X-RateLimit-Actual-Cost header).

Cost estimation (pre-request):
- Base cost: 1 point per request
- +1 per focus_area
- +2 if include_readme=true
- +5 if depth > 1 (future)
- Caps from config add fixed overhead

This prevents "melt down first, then reject" under load.
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


# Endpoints with rate limiting (expensive LLM operations)
RATE_LIMITED_ENDPOINTS = {
    "/goals/{goal_id}/generate-tickets",
    "/goals/{goal_id}/reflect-on-tickets",
    "/boards/{board_id}/analyze-codebase",
    "/board/analyze-codebase",  # Legacy
    "/planner/tick",
    "/planner/start",
    "/udar/{goal_id}/generate",  # UDAR agent initial generation
    "/udar/{goal_id}/replan",  # UDAR agent incremental replanning
}

# Cost-based rate limit configuration
RATE_LIMIT_BUDGET = 100  # Cost points per window
RATE_LIMIT_WINDOW_SECONDS = 60  # Per minute

# Cost scoring - estimated BEFORE request executes
BASE_COST = 1
COST_PER_FOCUS_AREA = 2
COST_INCLUDE_README = 3
COST_ANALYZE_CODEBASE = 10  # Heavy operation
COST_GENERATE_TICKETS = 5
COST_REFLECT = 5
COST_PLANNER_TICK = 3
COST_UDAR_GENERATE = 8  # UDAR initial generation (1-2 LLM calls)
COST_UDAR_REPLAN = 3  # UDAR replanning (0-1 LLM calls)

# Redis key prefix
REDIS_KEY_PREFIX = "ratelimit:"


def _matches_pattern(path: str, patterns: set[str]) -> tuple[bool, str | None]:
    """Check if path matches any pattern. Returns (matches, matched_pattern)."""
    for pattern in patterns:
        pattern_parts = pattern.split("/")
        path_parts = path.split("/")

        if len(pattern_parts) != len(path_parts):
            continue

        match = True
        for p_part, path_part in zip(pattern_parts, path_parts, strict=False):
            if p_part.startswith("{") and p_part.endswith("}"):
                continue
            if p_part != path_part:
                match = False
                break

        if match:
            return True, pattern
    return False, None


def _get_client_id(request: Request) -> str:
    """Get client identifier for rate limiting."""
    client_id = request.headers.get("X-Client-ID")
    if client_id and len(client_id) <= 64:
        return client_id

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"

    return f"ip:{request.client.host if request.client else 'unknown'}"


def _get_route_key(path: str) -> str:
    """Normalize path to route key."""
    import re

    return re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{id}",
        path,
        flags=re.IGNORECASE,
    )


def _estimate_request_cost(body: bytes, matched_pattern: str | None) -> int:
    """Estimate cost BEFORE request executes based on request intent."""
    cost = BASE_COST

    if matched_pattern:
        if "analyze-codebase" in matched_pattern:
            cost += COST_ANALYZE_CODEBASE
        elif "generate-tickets" in matched_pattern:
            cost += COST_GENERATE_TICKETS
        elif "reflect-on-tickets" in matched_pattern:
            cost += COST_REFLECT
        elif "planner" in matched_pattern:
            cost += COST_PLANNER_TICK
        elif "/udar/" in matched_pattern:
            if "/generate" in matched_pattern:
                cost += COST_UDAR_GENERATE
            elif "/replan" in matched_pattern:
                cost += COST_UDAR_REPLAN

    try:
        body_dict = json.loads(body) if body else {}
        focus_areas = body_dict.get("focus_areas", [])
        if focus_areas:
            cost += len(focus_areas) * COST_PER_FOCUS_AREA
        if body_dict.get("include_readme"):
            cost += COST_INCLUDE_README
    except (json.JSONDecodeError, TypeError):
        pass

    return cost


def _compute_actual_cost(response_body: bytes, estimated_cost: int) -> int:
    """Compute actual cost from response (TELEMETRY ONLY, not for gating)."""
    actual = estimated_cost

    try:
        response_dict = json.loads(response_body)
        context_stats = response_dict.get("context_stats")

        if context_stats:
            files_scanned = context_stats.get("files_scanned", 0)
            actual += files_scanned // 50

            bytes_read = context_stats.get("bytes_read", 0)
            actual += bytes_read // 10240

            if context_stats.get("context_truncated"):
                actual += 5

    except (json.JSONDecodeError, TypeError, AttributeError):
        pass

    return actual


def _backend_available() -> bool:
    """Check if the rate limit backend is available."""
    return True  # SQLite is always available


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Cost-based rate limiter with pluggable backend.

    Flow:
    1. Estimate cost from request intent
    2. Check if estimated cost would exceed budget
    3. If over budget: reject with 429 BEFORE doing work
    4. If under budget: execute request
    5. Compute actual cost and emit as telemetry header
    """

    def __init__(
        self,
        app,
        budget: int = RATE_LIMIT_BUDGET,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
    ):
        super().__init__(app)
        self.budget = budget
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only rate-limit POST requests to specific endpoints
        if request.method != "POST":
            return await call_next(request)

        matches, matched_pattern = _matches_pattern(
            request.url.path, RATE_LIMITED_ENDPOINTS
        )
        if not matches:
            return await call_next(request)

        # Backend REQUIRED
        if not _backend_available():
            logger.error(
                f"Backend unavailable for rate-limited endpoint: {request.url.path}"
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service temporarily unavailable. Backend is required for rate limiting.",
                    "error_type": "service_unavailable",
                    "retry_after_seconds": 30,
                },
                headers={"Retry-After": "30"},
            )

        client_id = _get_client_id(request)
        route_key = _get_route_key(request.url.path)

        # Read body to estimate cost BEFORE expensive work
        body = await request.body()
        estimated_cost = _estimate_request_cost(body, matched_pattern)

        now = time.time()

        try:
            current_cost, oldest_time = await self._check_sqlite(
                client_id, route_key, estimated_cost
            )
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service temporarily unavailable due to rate limit error.",
                    "error_type": "service_unavailable",
                },
            )

        # GATE: Check if estimated cost would exceed budget BEFORE work
        if current_cost + estimated_cost > self.budget:
            retry_after = int(oldest_time + self.window_seconds - now)
            retry_after = max(1, retry_after)

            logger.warning(
                f"Rate limit exceeded for {client_id}: "
                f"{current_cost}/{self.budget} points, estimated +{estimated_cost}"
            )

            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Budget: {self.budget} points/min.",
                    "retry_after_seconds": retry_after,
                    "budget": self.budget,
                    "current_usage": current_cost,
                    "estimated_cost": estimated_cost,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.budget),
                    "X-RateLimit-Remaining": str(max(0, self.budget - current_cost)),
                    "X-RateLimit-Reset": str(int(now + retry_after)),
                },
            )

        # Reconstruct request with body
        async def receive():
            return {"type": "http.request", "body": body}

        request._receive = receive

        # Execute request (budget already reserved)
        response = await call_next(request)

        # Read response body for telemetry
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        # Compute actual cost for observability (telemetry only)
        actual_cost = _compute_actual_cost(response_body, estimated_cost)
        remaining = max(0, self.budget - current_cost - estimated_cost)

        # Build response with rate limit headers, preserving original headers (including CORS)
        new_response = Response(
            content=response_body,
            status_code=response.status_code,
            media_type=response.media_type or "application/json",
        )
        # Copy original headers (preserves CORS headers)
        for key, value in response.headers.items():
            new_response.headers[key] = value
        # Add rate limit headers
        new_response.headers["X-RateLimit-Limit"] = str(self.budget)
        new_response.headers["X-RateLimit-Remaining"] = str(remaining)
        new_response.headers["X-RateLimit-Reset"] = str(int(now + self.window_seconds))
        new_response.headers["X-RateLimit-Estimated-Cost"] = str(estimated_cost)
        new_response.headers["X-RateLimit-Actual-Cost"] = str(actual_cost)

        return new_response

    # ─── SQLite backend ───

    async def _check_sqlite(
        self, client_id: str, route_key: str, estimated_cost: int
    ) -> tuple[int, float]:
        """Check and record rate limit via SQLite. Returns (current_cost, oldest_time)."""
        from app.sqlite_kv import rate_limit_check_and_record

        client_key = f"{client_id}:{route_key}"
        return await asyncio.to_thread(
            rate_limit_check_and_record, client_key, estimated_cost, self.window_seconds
        )
