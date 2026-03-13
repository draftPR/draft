"""In-memory cache for idempotency, rate limiting, and transient data.

Provides a simple dict-based cache with TTL support. Used by middleware
and services for short-lived data that doesn't need disk persistence.
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_cache_instance: "InMemoryCache | None" = None


class InMemoryCache:
    """In-memory cache with TTL support.

    Provides a Redis-compatible interface for single-process operation.
    """

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._expiry: dict[str, float] = {}

    def _check_expired(self, key: str) -> bool:
        """Check if a key has expired and delete it if so."""
        if key in self._expiry:
            if time.time() > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return True
        return False

    def get(self, key: str) -> Any | None:
        """Get value for key, returns None if not found or expired."""
        if self._check_expired(key):
            return None
        return self._data.get(key)

    def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        """Set key to value with optional expiry in seconds."""
        self._data[key] = value
        if ex is not None:
            self._expiry[key] = time.time() + ex
        elif key in self._expiry:
            del self._expiry[key]
        return True

    def setex(self, key: str, time_seconds: int, value: Any) -> bool:
        """Set key with expiry."""
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
        return True

    def close(self) -> None:
        pass


def get_redis() -> InMemoryCache:
    """Get the shared in-memory cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = InMemoryCache()
    return _cache_instance


def close_redis() -> None:
    """Clear the cache (call on shutdown)."""
    global _cache_instance
    if _cache_instance:
        _cache_instance.close()
        _cache_instance = None
