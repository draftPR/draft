"""Cost-based rate limiting middleware backed by Redis.

CRITICAL: Rate limiting gates on ESTIMATED cost BEFORE expensive work.
Actual cost is emitted as telemetry only (X-RateLimit-Actual-Cost header).

Cost estimation (pre-request):
- Base cost: 1 point per request
- +1 per focus_area
- +2 if include_readme=true
- +5 if depth > 1 (future)
- Caps from config add fixed overhead

This prevents "melt down first, then reject" under load.

CRITICAL: Redis is REQUIRED. Returns 503 if unavailable.
"""

import json
import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.redis_client import get_redis, redis_available

logger = logging.getLogger(__name__)


# Endpoints with rate limiting (expensive LLM operations)
RATE_LIMITED_ENDPOINTS = {
    "/goals/{goal_id}/generate-tickets",
    "/goals/{goal_id}/reflect-on-tickets",
    "/boards/{board_id}/analyze-codebase",
    "/board/analyze-codebase",  # Legacy
    "/planner/tick",
    "/planner/start",
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
        for p_part, path_part in zip(pattern_parts, path_parts):
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
    """Estimate cost BEFORE request executes based on request intent.
    
    This is the gating cost - we reject requests that would exceed budget
    BEFORE doing any expensive work.
    """
    cost = BASE_COST
    
    # Add operation-specific base cost
    if matched_pattern:
        if "analyze-codebase" in matched_pattern:
            cost += COST_ANALYZE_CODEBASE
        elif "generate-tickets" in matched_pattern:
            cost += COST_GENERATE_TICKETS
        elif "reflect-on-tickets" in matched_pattern:
            cost += COST_REFLECT
        elif "planner" in matched_pattern:
            cost += COST_PLANNER_TICK
    
    # Parse body to estimate additional cost
    try:
        body_dict = json.loads(body) if body else {}
        
        # Focus areas add cost
        focus_areas = body_dict.get("focus_areas", [])
        if focus_areas:
            cost += len(focus_areas) * COST_PER_FOCUS_AREA
        
        # README adds context processing cost
        if body_dict.get("include_readme"):
            cost += COST_INCLUDE_README
            
    except (json.JSONDecodeError, TypeError):
        pass
    
    return cost


def _compute_actual_cost(response_body: bytes, estimated_cost: int) -> int:
    """Compute actual cost from response (TELEMETRY ONLY, not for gating).
    
    This is for observability - we emit it as a header so clients and
    dashboards can see real cost vs estimated.
    """
    actual = estimated_cost
    
    try:
        response_dict = json.loads(response_body)
        context_stats = response_dict.get("context_stats")
        
        if context_stats:
            # Add cost based on actual work done
            files_scanned = context_stats.get("files_scanned", 0)
            actual += files_scanned // 50  # +1 per 50 files
            
            bytes_read = context_stats.get("bytes_read", 0)
            actual += bytes_read // 10240  # +1 per 10KB
            
            if context_stats.get("context_truncated"):
                actual += 5  # Hit caps = expensive
            
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    
    return actual


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Cost-based rate limiter that gates on ESTIMATED cost before work.
    
    CRITICAL: Redis is REQUIRED. Returns 503 if unavailable.
    
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

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        # Only rate-limit POST requests to specific endpoints
        if request.method != "POST":
            return await call_next(request)
        
        matches, matched_pattern = _matches_pattern(request.url.path, RATE_LIMITED_ENDPOINTS)
        if not matches:
            return await call_next(request)
        
        # CRITICAL: Redis REQUIRED - NO fallback
        if not redis_available():
            logger.error(f"Redis unavailable for rate-limited endpoint: {request.url.path}")
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service temporarily unavailable. Redis is required for rate limiting.",
                    "error_type": "service_unavailable",
                    "retry_after_seconds": 30,
                },
                headers={"Retry-After": "30"},
            )
        
        redis_client = get_redis()
        client_id = _get_client_id(request)
        route_key = _get_route_key(request.url.path)
        
        # Read body to estimate cost BEFORE expensive work
        body = await request.body()
        estimated_cost = _estimate_request_cost(body, matched_pattern)
        
        now = time.time()
        window_start = now - self.window_seconds
        redis_key = f"{REDIS_KEY_PREFIX}{client_id}:{route_key}"
        
        try:
            # Clean up expired entries and get current usage
            pipe = redis_client.pipeline()
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zrange(redis_key, 0, -1, withscores=True)
            results = pipe.execute()
            entries = results[1]
            
            # Sum current cost
            current_cost = 0
            oldest_time = now
            for member, score in entries:
                try:
                    _, cost_str = member.split(":", 1)
                    current_cost += int(cost_str)
                    if score < oldest_time:
                        oldest_time = score
                except (ValueError, AttributeError):
                    current_cost += BASE_COST
            
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
            
            # Record ESTIMATED cost immediately (before work)
            # This reserves budget so concurrent requests see the reservation
            member = f"{now}:{estimated_cost}"
            redis_client.zadd(redis_key, {member: now})
            redis_client.expire(redis_key, self.window_seconds + 10)
            
        except Exception as e:
            logger.error(f"Redis rate limit pre-check failed: {e}")
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service temporarily unavailable due to rate limit error.",
                    "error_type": "service_unavailable",
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
