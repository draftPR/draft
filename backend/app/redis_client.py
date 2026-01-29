"""Redis client singleton with connection pooling and retry logic."""

import os
import logging
import time
from typing import Callable, TypeVar, Any, Optional

import redis
from redis.connection import ConnectionPool
from redis.exceptions import ConnectionError, TimeoutError, RedisError

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))
REDIS_SOCKET_TIMEOUT = int(os.getenv("REDIS_SOCKET_TIMEOUT", "5"))
REDIS_SOCKET_CONNECT_TIMEOUT = int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5"))
SMART_KANBAN_MODE = os.getenv("SMART_KANBAN_MODE", "production")

# Connection pool (shared across workers)
_connection_pool: ConnectionPool | None = None
_redis_client: redis.Redis | None = None
_fallback_client: Optional['FallbackCache'] = None

T = TypeVar('T')


class FallbackCache:
    """In-memory fallback cache when Redis is unavailable.

    This provides a basic Redis-compatible interface for single-process
    evaluation/demo mode. NOT suitable for production or multi-process setups.
    """

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._expiry: dict[str, float] = {}
        logger.warning(
            "Using in-memory fallback cache. This is NOT suitable for production. "
            "Install and run Redis for proper functionality."
        )

    def _check_expired(self, key: str) -> bool:
        """Check if a key has expired and delete it if so."""
        if key in self._expiry:
            if time.time() > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return True
        return False

    def get(self, key: str) -> Optional[Any]:
        """Get value for key, returns None if not found or expired."""
        if self._check_expired(key):
            return None
        return self._data.get(key)

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Set key to value with optional expiry in seconds."""
        self._data[key] = value
        if ex is not None:
            self._expiry[key] = time.time() + ex
        elif key in self._expiry:
            del self._expiry[key]
        return True

    def setex(self, key: str, time_seconds: int, value: Any) -> bool:
        """Set key with expiry (Redis-compatible signature)."""
        return self.set(key, value, ex=time_seconds)

    def delete(self, *keys: str) -> int:
        """Delete one or more keys, returns count of deleted keys."""
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                count += 1
            if key in self._expiry:
                del self._expiry[key]
        return count

    def setnx(self, key: str, value: Any) -> bool:
        """Set key only if it doesn't exist. Returns True if set, False otherwise."""
        if self._check_expired(key):
            # Key was expired, treat as non-existent
            pass
        elif key in self._data:
            return False

        self._data[key] = value
        return True

    def exists(self, *keys: str) -> int:
        """Check if keys exist, returns count of existing keys."""
        count = 0
        for key in keys:
            if not self._check_expired(key) and key in self._data:
                count += 1
        return count

    def expire(self, key: str, time_seconds: int) -> bool:
        """Set expiry on existing key."""
        if key not in self._data or self._check_expired(key):
            return False
        self._expiry[key] = time.time() + time_seconds
        return True

    def ttl(self, key: str) -> int:
        """Get time to live for key. Returns -1 if no expiry, -2 if not found."""
        if self._check_expired(key) or key not in self._data:
            return -2
        if key not in self._expiry:
            return -1
        remaining = int(self._expiry[key] - time.time())
        return max(0, remaining)

    def ping(self) -> bool:
        """Health check - always returns True for in-memory cache."""
        return True

    def close(self) -> None:
        """No-op for compatibility."""
        pass


def get_connection_pool() -> ConnectionPool:
    """Get or create the shared Redis connection pool."""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = ConnectionPool.from_url(
            REDIS_URL,
            decode_responses=True,
            max_connections=REDIS_MAX_CONNECTIONS,
            socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
            socket_timeout=REDIS_SOCKET_TIMEOUT,
            health_check_interval=30,  # Ping every 30s to detect stale connections
        )
        logger.info(
            f"Created Redis connection pool: max_connections={REDIS_MAX_CONNECTIONS}, "
            f"timeout={REDIS_SOCKET_TIMEOUT}s"
        )
    return _connection_pool


def get_redis() -> redis.Redis | FallbackCache:
    """Get the shared Redis client instance with connection pooling.

    In local/demo mode (SMART_KANBAN_MODE=local), returns an in-memory
    fallback cache instead of Redis. This allows evaluation without Redis.

    Returns a connected Redis client or FallbackCache. Connection is lazy and pooled.
    """
    global _redis_client, _fallback_client

    # Check if we should use fallback mode
    if SMART_KANBAN_MODE == "local":
        if _fallback_client is None:
            _fallback_client = FallbackCache()
            logger.info("Running in LOCAL mode - using in-memory cache (no Redis required)")
        return _fallback_client

    # Try to use real Redis
    if _redis_client is None:
        try:
            pool = get_connection_pool()
            _redis_client = redis.Redis(connection_pool=pool)
            # Test connection
            _redis_client.ping()
            logger.info("Connected to Redis successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            # Fall back to in-memory cache if Redis unavailable
            if _fallback_client is None:
                _fallback_client = FallbackCache()
            return _fallback_client

    return _redis_client


def redis_with_retry(
    func: Callable[[], T],
    max_retries: int = 3,
    base_backoff: float = 0.1,
    max_backoff: float = 2.0,
) -> T:
    """Execute a Redis operation with exponential backoff retry.

    Retries on:
    - ConnectionError (Redis unavailable)
    - TimeoutError (Redis overloaded)

    Does NOT retry on:
    - RedisError (command errors - e.g., wrong type)

    Args:
        func: Function to execute (takes no args, returns T)
        max_retries: Maximum retry attempts
        base_backoff: Initial backoff in seconds
        max_backoff: Maximum backoff in seconds

    Returns:
        Result of func()

    Raises:
        RedisError: If all retries exhausted or non-retryable error
    """
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            return func()
        except (ConnectionError, TimeoutError) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = min(base_backoff * (2 ** attempt), max_backoff)
                logger.warning(
                    f"Redis operation failed (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait:.2f}s..."
                )
                time.sleep(wait)
            else:
                logger.error(
                    f"Redis operation failed after {max_retries} attempts: {e}"
                )
        except RedisError as e:
            # Don't retry command errors
            logger.error(f"Redis command error (non-retryable): {e}")
            raise

    # All retries exhausted
    raise last_error or RedisError("Redis operation failed")


def redis_available() -> bool:
    """Check if Redis is available with retry logic.

    Returns True if we can ping Redis (with retries), False otherwise.
    Used to gracefully degrade when Redis is down.
    """
    try:
        client = get_redis()
        redis_with_retry(client.ping, max_retries=2)
        return True
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        return False


def close_redis() -> None:
    """Close Redis connection pool (call on shutdown)."""
    global _connection_pool, _redis_client, _fallback_client
    if _redis_client:
        _redis_client.close()
        _redis_client = None
    if _connection_pool:
        _connection_pool.disconnect()
        _connection_pool = None
        logger.info("Closed Redis connection pool")
    if _fallback_client:
        _fallback_client.close()
        _fallback_client = None
