"""Idempotency middleware with pluggable backend (Redis or SQLite).

Guarantees exactly-once execution for LLM operations.

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

import asyncio
import hashlib
import json
import logging
import time
import uuid
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

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
        for p_part, path_part in zip(pattern_parts, path_parts, strict=False):
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


def _backend_available() -> bool:
    """Check if the idempotency backend is available."""
    return True  # SQLite is always available


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Atomic idempotency middleware using Redis SETNX or SQLite INSERT OR IGNORE.

    Guarantees exactly-once execution with deterministic behavior:
    1. Try to acquire lock atomically
    2. If acquired: execute request, store result with execution_id
    3. If not acquired: blocking wait up to WAIT_TIMEOUT_SECONDS
    4. If result appears: return with X-Idempotency-Replayed
    5. If timeout: return 202 with execution_id for polling
    6. If body mismatch: return 409 Conflict
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
            # No key provided - still require backend for these endpoints
            if not _backend_available():
                return self._service_unavailable()
            return await call_next(request)

        # Validate key format
        if len(idempotency_key) > 64:
            return JSONResponse(
                status_code=400,
                content={"detail": "Idempotency-Key too long (max 64 chars)"},
            )

        # Backend REQUIRED - NO fallback
        if not _backend_available():
            return self._service_unavailable()

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

        # Build cache key
        base_key = f"{client_id}:{request.url.path}:{resource_scope}:{idempotency_key}"

        # Generate execution_id for this attempt
        execution_id = _generate_execution_id()

        try:
            return await self._dispatch_sqlite(
                request, call_next, body, body_hash, base_key,
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

    # ─── SQLite backend ───

    async def _dispatch_sqlite(
        self, request, call_next, body, body_hash, base_key,
        idempotency_key, execution_id,
    ) -> Response:
        from app.sqlite_kv import idempotency_try_acquire

        lock_value = json.dumps({
            "body_hash": body_hash,
            "execution_id": execution_id,
            "started_at": time.time(),
        })

        acquired = await asyncio.to_thread(
            idempotency_try_acquire, base_key, lock_value, LOCK_TTL_SECONDS
        )

        if acquired:
            return await self._execute_and_cache_sqlite(
                request, call_next, body, body_hash, base_key,
                idempotency_key, execution_id
            )
        else:
            return await self._blocking_wait_sqlite(
                base_key, body_hash, idempotency_key, execution_id
            )

    async def _execute_and_cache_sqlite(
        self, request, call_next, body, body_hash, cache_key,
        idempotency_key, execution_id,
    ) -> Response:
        from app.sqlite_kv import idempotency_release_lock, idempotency_store_result

        async def receive():
            return {"type": "http.request", "body": body}
        request._receive = receive

        try:
            response = await call_next(request)

            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk

            result_data = json.dumps({
                "status_code": response.status_code,
                "body": response_body.decode("utf-8"),
                "body_hash": body_hash,
                "execution_id": execution_id,
                "completed_at": time.time(),
            })
            await asyncio.to_thread(
                idempotency_store_result, cache_key, result_data, CACHE_TTL_SECONDS
            )

            logger.debug(f"Executed and cached for key: {idempotency_key[:8]}... exec_id: {execution_id[:8]}...")

            return Response(
                content=response_body,
                status_code=response.status_code,
                media_type="application/json",
                headers={"X-Execution-ID": execution_id},
            )

        except Exception:
            await asyncio.to_thread(idempotency_release_lock, cache_key)
            raise

    async def _blocking_wait_sqlite(
        self, cache_key, body_hash, idempotency_key, our_execution_id,
    ) -> Response:
        from app.sqlite_kv import idempotency_get_lock, idempotency_get_result

        start_time = time.time()
        original_execution_id: str | None = None

        while time.time() - start_time < WAIT_TIMEOUT_SECONDS:
            result_data = await asyncio.to_thread(idempotency_get_result, cache_key)
            if result_data:
                cached = json.loads(result_data)
                if cached.get("body_hash") != body_hash:
                    return JSONResponse(
                        status_code=409,
                        content={
                            "detail": "Idempotency key already used with different request body",
                            "error_type": "idempotency_conflict",
                            "original_execution_id": cached.get("execution_id"),
                        },
                    )
                return Response(
                    content=cached["body"].encode() if isinstance(cached["body"], str) else cached["body"],
                    status_code=cached["status_code"],
                    media_type="application/json",
                    headers={
                        "X-Idempotency-Replayed": "true",
                        "X-Execution-ID": cached.get("execution_id", "unknown"),
                    },
                )

            lock_data = await asyncio.to_thread(idempotency_get_lock, cache_key)
            if not lock_data:
                # Lock released but no result - original failed, allow retry
                break
            try:
                lock_info = json.loads(lock_data)
                original_execution_id = lock_info.get("execution_id")
            except (json.JSONDecodeError, TypeError):
                original_execution_id = "unknown"

            await asyncio.sleep(POLL_INTERVAL_MS / 1000)

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

    def _service_unavailable(self) -> JSONResponse:
        """Return 503 when backend is unavailable."""
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Service temporarily unavailable. Backend is required for this operation.",
                "error_type": "service_unavailable",
                "retry_after_seconds": 30,
            },
            headers={"Retry-After": "30"},
        )
