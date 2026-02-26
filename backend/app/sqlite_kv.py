"""Low-level SQLite operations for middleware (sync, used via asyncio.to_thread).

These functions use raw SQLite connections (not SQLAlchemy sessions) for
atomicity and to avoid interfering with the async session lifecycle.
The middleware runs outside of route handlers, so it cannot use get_db().
"""

import os
import sqlite3
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).parent.parent.resolve()
_DB_PATH = os.getenv("SQLITE_BACKEND_DB", str(_BACKEND_DIR / "kanban.db"))

# Parse async DATABASE_URL to extract path if set
_DATABASE_URL = os.getenv("DATABASE_URL", "")
if _DATABASE_URL:
    # Handle both sqlite:///path and sqlite+aiosqlite:///path
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if _DATABASE_URL.startswith(prefix):
            _extracted = _DATABASE_URL[len(prefix) :]
            if _extracted:
                _DB_PATH = _extracted
            break


def _get_conn() -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode."""
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


# ─── Idempotency operations ───


def idempotency_try_acquire(cache_key: str, lock_value: str, ttl_seconds: int) -> bool:
    """Try to acquire an idempotency lock. Returns True if acquired."""
    now = time.time()
    now + ttl_seconds
    conn = _get_conn()
    try:
        # Clean expired locks first
        conn.execute(
            "DELETE FROM idempotency_cache WHERE lock_expires_at IS NOT NULL "
            "AND lock_expires_at < datetime('now')"
        )
        # Try atomic insert
        cursor = conn.execute(
            "INSERT OR IGNORE INTO idempotency_cache "
            "(cache_key, lock_value, lock_expires_at, created_at) "
            "VALUES (?, ?, datetime('now', ?), datetime('now'))",
            (cache_key, lock_value, f"+{ttl_seconds} seconds"),
        )
        conn.commit()
        return cursor.rowcount == 1
    finally:
        conn.close()


def idempotency_get_lock(cache_key: str) -> str | None:
    """Get the lock value for a key (None if not locked or expired)."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT lock_value FROM idempotency_cache "
            "WHERE cache_key = ? AND (lock_expires_at IS NULL OR lock_expires_at >= datetime('now'))",
            (cache_key,),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def idempotency_store_result(
    cache_key: str, result_value: str, ttl_seconds: int
) -> None:
    """Store the result and clear the lock."""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE idempotency_cache SET result_value = ?, "
            "result_expires_at = datetime('now', ?), "
            "lock_value = NULL, lock_expires_at = NULL "
            "WHERE cache_key = ?",
            (result_value, f"+{ttl_seconds} seconds", cache_key),
        )
        conn.commit()
    finally:
        conn.close()


def idempotency_get_result(cache_key: str) -> str | None:
    """Get cached result (None if not found or expired)."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT result_value FROM idempotency_cache "
            "WHERE cache_key = ? AND result_value IS NOT NULL "
            "AND (result_expires_at IS NULL OR result_expires_at >= datetime('now'))",
            (cache_key,),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def idempotency_release_lock(cache_key: str) -> None:
    """Release lock (delete entry if no result stored)."""
    conn = _get_conn()
    try:
        conn.execute(
            "DELETE FROM idempotency_cache WHERE cache_key = ? AND result_value IS NULL",
            (cache_key,),
        )
        conn.commit()
    finally:
        conn.close()


# ─── Rate limit operations ───


def rate_limit_check_and_record(
    client_key: str, cost: int, window_seconds: int
) -> tuple[int, float]:
    """Check current usage and record new cost entry.

    Returns (current_cost_before_recording, oldest_entry_time).
    """
    now = time.time()
    window_start = now - window_seconds
    expires_at = now + window_seconds

    conn = _get_conn()
    try:
        # Cleanup expired
        conn.execute("DELETE FROM rate_limit_entries WHERE expires_at < ?", (now,))

        # Sum current cost in window (also filter by expires_at for consistency)
        row = conn.execute(
            "SELECT COALESCE(SUM(cost), 0) FROM rate_limit_entries "
            "WHERE client_key = ? AND recorded_at > ? AND expires_at >= ?",
            (client_key, window_start, now),
        ).fetchone()
        current_cost = row[0] if row else 0

        # Get oldest entry time for retry-after calculation
        oldest_row = conn.execute(
            "SELECT MIN(recorded_at) FROM rate_limit_entries "
            "WHERE client_key = ? AND recorded_at > ? AND expires_at >= ?",
            (client_key, window_start, now),
        ).fetchone()
        oldest_time = oldest_row[0] if oldest_row and oldest_row[0] else now

        # Record new entry
        conn.execute(
            "INSERT INTO rate_limit_entries (client_key, cost, recorded_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (client_key, cost, now, expires_at),
        )
        conn.commit()

        return current_cost, oldest_time
    finally:
        conn.close()


def rate_limit_check_only(client_key: str, window_seconds: int) -> tuple[int, float]:
    """Check current usage without recording. Returns (current_cost, oldest_time)."""
    now = time.time()
    window_start = now - window_seconds

    conn = _get_conn()
    try:
        # Cleanup expired
        conn.execute("DELETE FROM rate_limit_entries WHERE expires_at < ?", (now,))

        row = conn.execute(
            "SELECT COALESCE(SUM(cost), 0) FROM rate_limit_entries "
            "WHERE client_key = ? AND recorded_at > ? AND expires_at >= ?",
            (client_key, window_start, now),
        ).fetchone()
        current_cost = row[0] if row else 0

        oldest_row = conn.execute(
            "SELECT MIN(recorded_at) FROM rate_limit_entries "
            "WHERE client_key = ? AND recorded_at > ? AND expires_at >= ?",
            (client_key, window_start, now),
        ).fetchone()
        oldest_time = oldest_row[0] if oldest_row and oldest_row[0] else now

        conn.commit()
        return current_cost, oldest_time
    finally:
        conn.close()


# ─── KV store operations (for queued messages) ───


def kv_set(key: str, value: str, ttl_seconds: int | None = None) -> None:
    """Set a key-value pair with optional TTL."""
    conn = _get_conn()
    try:
        if ttl_seconds:
            conn.execute(
                "INSERT OR REPLACE INTO kv_store (key, value, expires_at, created_at) "
                "VALUES (?, ?, datetime('now', ?), datetime('now'))",
                (key, value, f"+{ttl_seconds} seconds"),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO kv_store (key, value, created_at) "
                "VALUES (?, ?, datetime('now'))",
                (key, value),
            )
        conn.commit()
    finally:
        conn.close()


def kv_get(key: str) -> str | None:
    """Get a value by key (None if not found or expired)."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM kv_store WHERE key = ? "
            "AND (expires_at IS NULL OR expires_at >= datetime('now'))",
            (key,),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def kv_take(key: str) -> str | None:
    """Get and delete a value atomically (None if not found or expired)."""
    conn = _get_conn()
    try:
        # Atomic get-and-delete using DELETE...RETURNING (SQLite 3.35+)
        row = conn.execute(
            "DELETE FROM kv_store WHERE key = ? "
            "AND (expires_at IS NULL OR expires_at >= datetime('now')) "
            "RETURNING value",
            (key,),
        ).fetchone()
        conn.commit()
        return row[0] if row else None
    finally:
        conn.close()


def kv_delete(key: str) -> bool:
    """Delete a key. Returns True if deleted."""
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def kv_exists(key: str) -> bool:
    """Check if a key exists (and is not expired)."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM kv_store WHERE key = ? "
            "AND (expires_at IS NULL OR expires_at >= datetime('now'))",
            (key,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()
