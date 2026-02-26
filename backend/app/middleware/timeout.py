"""Request timeout middleware."""

import asyncio
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces a global timeout on all requests."""

    def __init__(self, app, timeout_seconds: int = 120):
        super().__init__(app)
        self.timeout_seconds = timeout_seconds

    async def dispatch(self, request: Request, call_next):
        try:
            response = await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout_seconds
            )
            return response
        except TimeoutError:
            logger.error(
                f"Request timed out after {self.timeout_seconds}s: "
                f"{request.method} {request.url.path}"
            )
            return JSONResponse(
                status_code=504,
                content={
                    "detail": f"Request timed out after {self.timeout_seconds} seconds",
                    "error_type": "timeout",
                }
            )
