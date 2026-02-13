"""Database retry decorator for SQLite BUSY errors.

SQLite has concurrency limitations and can throw BUSY errors when multiple
processes/threads access the database. This module provides retry logic
with exponential backoff.
"""

import asyncio
import logging
import sqlite3
from functools import wraps
from typing import Callable, TypeVar

from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_db_retry(
    max_retries: int = 3,
    base_backoff: float = 0.1,
    max_backoff: float = 2.0,
):
    """Decorator to retry async DB operations on SQLite BUSY errors.

    Args:
        max_retries: Maximum number of retry attempts
        base_backoff: Base backoff time in seconds
        max_backoff: Maximum backoff time in seconds

    Usage:
        @with_db_retry(max_retries=3)
        async def my_db_operation(self, ...):
            # ... database operations ...
            await self.db.commit()
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (sqlite3.OperationalError, OperationalError) as e:
                    last_exception = e
                    error_msg = str(e).lower()

                    # Only retry on BUSY/locked errors
                    if "database is locked" in error_msg or "busy" in error_msg:
                        if attempt < max_retries - 1:
                            # Exponential backoff with cap
                            wait = min(base_backoff * (2**attempt), max_backoff)
                            logger.warning(
                                f"DB locked in {func.__name__}, "
                                f"retry {attempt + 1}/{max_retries} after {wait:.2f}s"
                            )
                            await asyncio.sleep(wait)
                            continue
                        else:
                            logger.error(
                                f"DB locked in {func.__name__}, "
                                f"exhausted {max_retries} retries"
                            )
                    # For other OperationalErrors, don't retry
                    raise

            # If we get here, all retries exhausted
            raise last_exception

        return wrapper

    return decorator


def with_db_retry_sync(
    max_retries: int = 3,
    base_backoff: float = 0.1,
    max_backoff: float = 2.0,
):
    """Decorator to retry sync DB operations on SQLite BUSY errors.

    Args:
        max_retries: Maximum number of retry attempts
        base_backoff: Base backoff time in seconds
        max_backoff: Maximum backoff time in seconds

    Usage:
        @with_db_retry_sync(max_retries=3)
        def my_db_operation(self, ...):
            # ... database operations ...
            db.commit()
    """
    import time

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (sqlite3.OperationalError, OperationalError) as e:
                    last_exception = e
                    error_msg = str(e).lower()

                    # Only retry on BUSY/locked errors
                    if "database is locked" in error_msg or "busy" in error_msg:
                        if attempt < max_retries - 1:
                            # Exponential backoff with cap
                            wait = min(base_backoff * (2**attempt), max_backoff)
                            logger.warning(
                                f"DB locked in {func.__name__}, "
                                f"retry {attempt + 1}/{max_retries} after {wait:.2f}s"
                            )
                            time.sleep(wait)
                            continue
                        else:
                            logger.error(
                                f"DB locked in {func.__name__}, "
                                f"exhausted {max_retries} retries"
                            )
                    # For other OperationalErrors, don't retry
                    raise

            # If we get here, all retries exhausted
            raise last_exception

        return wrapper

    return decorator
