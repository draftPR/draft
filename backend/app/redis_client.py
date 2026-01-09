"""Redis client singleton for middleware and caching.

Provides a shared Redis connection used by:
- Idempotency middleware
- Rate limiting middleware
- Analysis caching (optional upgrade from DB)
"""

import os
import logging

import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Singleton Redis client
_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Get the shared Redis client instance.
    
    Returns a connected Redis client. Connection is lazy and cached.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            REDIS_URL,
            decode_responses=True,  # Return strings, not bytes
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _redis_client


def redis_available() -> bool:
    """Check if Redis is available.
    
    Returns True if we can ping Redis, False otherwise.
    Used to gracefully degrade when Redis is down.
    """
    try:
        client = get_redis()
        return client.ping()
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        return False


