"""Idempotency middleware backed by Redis with atomic first-writer-wins.

Guarantees exactly-once execution for LLM operations using Redis SETNX.

CRITICAL: Redis is REQUIRED for mutating endpoints. If Redis is unavailable,
these endpoints return 503 Service Unavailable.

Behavior Contract (Deterministic):
1. First request: acquires lock, executes, stores result with execution_id
2. Concurrent requests: blocking wait up to WAIT_TIMEOUT_SECONDS for result
3. If result appears within timeout: return it with X-Idempotency-Replayed
4. If timeout: return 202 Accepted with execution_id for polling
5. If same key + different body: return 409 Conflict

Key structure includes resource scope to prevent cross-goal/board collisions:
    (client_id, route, resource_scope, idempotency_key)

Scope Precedence Rules (strict):
1. Path param (e.g., goal_id from /goals/{goal_id}/...) takes precedence
2. Body param used only if no path param
3. If both exist and DIFFER: return 400 scope_mismatch
"""

import hashlib
import json
import logging
import time
import uuid
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.redis_client import get_redis, redis_available

logger = logging.getLogger(__name__)

# Endpoints that support idempotency (expensive LLM operations that mutate state)
IDEMPOTENT_ENDPOINTS = {
    "/goals/{goal_id}/generate-tickets",
    "/goals/{goal_id}/reflect-on-tickets",
    "/boards/{board_id}/analyze-codebase",
    "/board/analyze-codebase",  # Legacy
    "/tickets/bulk-update-priority",
}

# TTL for cached responses (10 minutes)
CACHE_TTL_SECONDS = 600

# TTL for processing lock (2 minutes - should be enough for any LLM call)
LOCK_TTL_SECONDS = 120

# Blocking wait timeout (10 seconds max)
WAIT_TIMEOUT_SECONDS = 10
POLL_INTERVAL_MS = 100

# Redis key prefixes
REDIS_LOCK_PREFIX = "idemp:lock:"
REDIS_RESULT_PREFIX = "idemp:result:"


def _matches_pattern(path: str, patterns: set[str]) -> tuple[bool, dict[str, str]]:
    """Check if path matches any pattern.
    
    Returns (matches, extracted_params) where extracted_params contains
    path parameters like {goal_id} -> actual value.
    """
    for pattern in patterns:
        pattern_parts = pattern.split("/")
        path_parts = path.split("/")
        
        if len(pattern_parts) != len(path_parts):
            continue
        
        match = True
        params = {}
        for p_part, path_part in zip(pattern_parts, path_parts):
            if p_part.startswith("{") and p_part.endswith("}"):
                param_name = p_part[1:-1]
                params[param_name] = path_part
            elif p_part != path_part:
                match = False
                break
        
        if match:
            return True, params
    return False, {}


def _get_client_id(request: Request) -> str:
    """Get client identifier for idempotency scoping."""
    client_id = request.headers.get("X-Client-ID")
    if client_id and len(client_id) <= 64:
        return client_id
    
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    
    return f"ip:{request.client.host if request.client else 'unknown'}"


def _compute_body_hash(body: bytes) -> str:
    """Compute a hash of the request body."""
    return hashlib.sha256(body).hexdigest()[:16]


def _extract_resource_scope(
    path: str, body_dict: dict[str, Any], path_params: dict[str, str]
) -> tuple[str, str | None]:
    """Extract resource scope with strict precedence rules.
    
    Returns:
        (scope_string, error_message)
        - If error_message is not None, there's a scope mismatch
    
    Precedence:
    1. Path param takes precedence
    2. Body param used only if no path param
    3. If both exist and DIFFER: return error
    """
    path_goal_id = path_params.get("goal_id")
    path_board_id = path_params.get("board_id")
    body_goal_id = body_dict.get("goal_id")
    body_board_id = body_dict.get("board_id")
    
    # Check for scope mismatch (path vs body)
    if path_goal_id and body_goal_id:
        if path_goal_id != body_goal_id:
            return "", f"Scope mismatch: path goal_id '{path_goal_id}' differs from body goal_id '{body_goal_id}'"
    
    if path_board_id and body_board_id:
        if path_board_id != body_board_id:
            return "", f"Scope mismatch: path board_id '{path_board_id}' differs from body board_id '{body_board_id}'"
    
    # Path takes precedence
    if path_goal_id:
        return f"goal:{path_goal_id}", None
    if path_board_id:
        return f"board:{path_board_id}", None
    
    # Fall back to body
    if body_goal_id:
        return f"goal:{body_goal_id}", None
    if body_board_id:
        return f"board:{body_board_id}", None
    
    # Board-level endpoints without explicit ID
    if "/board/" in path or "/boards/" in path:
        return "board:default", None
    
    return "global", None


def _generate_execution_id() -> str:
    """Generate a unique execution ID for tracking."""
    return str(uuid.uuid4())


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Atomic idempotency middleware using Redis SETNX.
    
    Guarantees exactly-once execution with deterministic behavior:
    1. Try SETNX to acquire lock
    2. If acquired: execute request, store result with execution_id
    3. If not acquired: blocking wait up to WAIT_TIMEOUT_SECONDS
    4. If result appears: return with X-Idempotency-Replayed
    5. If timeout: return 202 with execution_id for polling
    6. If body mismatch: return 409 Conflict
    
    CRITICAL: Redis is REQUIRED. Returns 503 if unavailable.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Only handle POST requests to specific endpoints
        if request.method != "POST":
            return await call_next(request)
        
        matches, path_params = _matches_pattern(request.url.path, IDEMPOTENT_ENDPOINTS)
        if not matches:
            return await call_next(request)
        
        # Check for idempotency key header
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            # No key provided - still require Redis for these endpoints
            if not redis_available():
                return self._service_unavailable()
            return await call_next(request)
        
        # Validate key format
        if len(idempotency_key) > 64:
            return JSONResponse(
                status_code=400,
                content={"detail": "Idempotency-Key too long (max 64 chars)"},
            )
        
        # CRITICAL: Redis REQUIRED - NO fallback
        if not redis_available():
            return self._service_unavailable()
        
        redis_client = get_redis()
        client_id = _get_client_id(request)
        
        # Read request body
        body = await request.body()
        body_hash = _compute_body_hash(body)
        
        # Parse body for scope extraction
        try:
            body_dict = json.loads(body) if body else {}
        except json.JSONDecodeError:
            body_dict = {}
        
        # Extract scope with strict precedence
        resource_scope, scope_error = _extract_resource_scope(
            request.url.path, body_dict, path_params
        )
        if scope_error:
            return JSONResponse(
                status_code=400,
                content={
                    "detail": scope_error,
                    "error_type": "scope_mismatch",
                },
            )
        
        # Build Redis keys
        base_key = f"{client_id}:{request.url.path}:{resource_scope}:{idempotency_key}"
        lock_key = f"{REDIS_LOCK_PREFIX}{base_key}"
        result_key = f"{REDIS_RESULT_PREFIX}{base_key}"
        
        # Generate execution_id for this attempt
        execution_id = _generate_execution_id()
        
        try:
            import asyncio
            
            # Try to acquire lock atomically with SETNX - run in thread to avoid blocking
            lock_value = json.dumps({
                "body_hash": body_hash,
                "execution_id": execution_id,
                "started_at": time.time(),
            })
            
            def _redis_acquire_lock():
                return redis_client.set(
                    lock_key, lock_value, nx=True, ex=LOCK_TTL_SECONDS
                )
            
            try:
                acquired = await asyncio.wait_for(
                    asyncio.to_thread(_redis_acquire_lock),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.error(f"Redis lock acquisition timed out for key {idempotency_key[:8]}...")
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Service temporarily unavailable due to lock timeout.",
                        "error_type": "service_unavailable",
                        "retry_after_seconds": 5,
                    },
                    headers={"Retry-After": "5"},
                )
            
            if acquired:
                # We own the lock - execute the request
                return await self._execute_and_cache(
                    request, call_next, body, body_hash, redis_client,
                    lock_key, result_key, idempotency_key, execution_id
                )
            else:
                # Someone else has the lock - blocking wait for result
                return await self._blocking_wait_for_result(
                    redis_client, lock_key, result_key, body_hash, 
                    idempotency_key, execution_id
                )
                
        except Exception as e:
            logger.error(f"Idempotency error: {e}")
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service temporarily unavailable due to cache error.",
                    "error_type": "service_unavailable",
                },
            )

    def _service_unavailable(self) -> JSONResponse:
        """Return 503 when Redis is unavailable."""
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Service temporarily unavailable. Redis is required for this operation.",
                "error_type": "service_unavailable",
                "retry_after_seconds": 30,
            },
            headers={"Retry-After": "30"},
        )

    async def _execute_and_cache(
        self,
        request: Request,
        call_next,
        body: bytes,
        body_hash: str,
        redis_client,
        lock_key: str,
        result_key: str,
        idempotency_key: str,
        execution_id: str,
    ) -> Response:
        """Execute the request and cache the result."""
        # Reconstruct request with body
        async def receive():
            return {"type": "http.request", "body": body}
        request._receive = receive
        
        try:
            response = await call_next(request)
            
            # Read response body
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk
            
            # Cache result with execution_id
            result_data = json.dumps({
                "status_code": response.status_code,
                "body": response_body.decode("utf-8"),
                "body_hash": body_hash,
                "execution_id": execution_id,
                "completed_at": time.time(),
            })
            redis_client.setex(result_key, CACHE_TTL_SECONDS, result_data)
            
            # Release lock (delete it - result is now available)
            redis_client.delete(lock_key)
            
            logger.debug(f"Executed and cached for key: {idempotency_key[:8]}... exec_id: {execution_id[:8]}...")
            
            return Response(
                content=response_body,
                status_code=response.status_code,
                media_type="application/json",
                headers={"X-Execution-ID": execution_id},
            )
            
        except Exception as e:
            # On error, release lock so others can retry
            redis_client.delete(lock_key)
            raise

    async def _blocking_wait_for_result(
        self,
        redis_client,
        lock_key: str,
        result_key: str,
        body_hash: str,
        idempotency_key: str,
        our_execution_id: str,
    ) -> Response:
        """Blocking wait for another request to complete.
        
        Deterministic behavior:
        - Wait up to WAIT_TIMEOUT_SECONDS
        - If result appears: return with X-Idempotency-Replayed
        - If timeout: return 202 with execution_id for polling
        - If body mismatch: return 409 Conflict
        """
        import asyncio
        
        start_time = time.time()
        max_wait = WAIT_TIMEOUT_SECONDS
        original_execution_id: str | None = None  # Track the original request's execution_id
        
        while time.time() - start_time < max_wait:
            # Check if result is available
            result_data = redis_client.get(result_key)
            if result_data:
                cached = json.loads(result_data)
                
                # Verify body hash matches
                if cached.get("body_hash") != body_hash:
                    logger.warning(
                        f"Idempotency key reused with different body: {idempotency_key[:8]}..."
                    )
                    return JSONResponse(
                        status_code=409,
                        content={
                            "detail": "Idempotency key already used with different request body",
                            "error_type": "idempotency_conflict",
                            "original_execution_id": cached.get("execution_id"),
                        },
                    )
                
                # Return cached result
                logger.info(f"Idempotency cache hit: {idempotency_key[:8]}... exec_id: {cached.get('execution_id', 'unknown')[:8]}...")
                return Response(
                    content=cached["body"].encode() if isinstance(cached["body"], str) else cached["body"],
                    status_code=cached["status_code"],
                    media_type="application/json",
                    headers={
                        "X-Idempotency-Replayed": "true",
                        "X-Execution-ID": cached.get("execution_id", "unknown"),
                    },
                )
            
            # Check if lock still exists (original request still processing)
            lock_data = redis_client.get(lock_key)
            if not lock_data:
                # Lock released but no result - check one more time
                result_data = redis_client.get(result_key)
                if result_data:
                    cached = json.loads(result_data)
                    if cached.get("body_hash") != body_hash:
                        return JSONResponse(
                            status_code=409,
                            content={
                                "detail": "Idempotency key already used with different request body",
                                "error_type": "idempotency_conflict",
                            },
                        )
                    return Response(
                        content=cached["body"].encode(),
                        status_code=cached["status_code"],
                        media_type="application/json",
                        headers={
                            "X-Idempotency-Replayed": "true",
                            "X-Execution-ID": cached.get("execution_id", "unknown"),
                        },
                    )
                # Lock gone, no result - original request failed
                # Allow this request to retry by breaking out
                break
            
            # Get execution_id from lock for polling reference
            try:
                lock_info = json.loads(lock_data)
                original_execution_id = lock_info.get("execution_id")
            except (json.JSONDecodeError, TypeError):
                original_execution_id = "unknown"
            
            # Wait and poll again
            await asyncio.sleep(POLL_INTERVAL_MS / 1000)
        
        # Timeout - return 202 Accepted with execution_id for polling
        return JSONResponse(
            status_code=202,
            content={
                "detail": "Request is being processed. Poll for result using execution_id.",
                "error_type": "processing",
                "execution_id": original_execution_id or our_execution_id,
                "retry_after_seconds": 2,
            },
            headers={
                "Retry-After": "2",
                "X-Execution-ID": original_execution_id or our_execution_id,
            },
        )
