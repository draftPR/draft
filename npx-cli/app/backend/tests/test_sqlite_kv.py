"""Tests for sqlite_kv module - low-level SQLite operations for middleware.

Tests cover: KV store, idempotency locking, rate limiting, TTL expiry.
"""

import sqlite3
import time
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Fixture: temp SQLite DB with all required tables
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_db(tmp_path):
    """Create a temporary SQLite DB with required tables and patch _DB_PATH."""
    db_path = str(tmp_path / "test_kv.db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE idempotency_cache (
            cache_key TEXT PRIMARY KEY,
            lock_value TEXT,
            result_value TEXT,
            lock_expires_at TIMESTAMP,
            result_expires_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE rate_limit_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_key TEXT NOT NULL,
            cost INTEGER NOT NULL DEFAULT 1,
            recorded_at REAL NOT NULL,
            expires_at REAL NOT NULL
        );
        CREATE INDEX ix_rate_limit_entries_client_key
            ON rate_limit_entries(client_key);
        CREATE INDEX ix_rate_limit_entries_expires_at
            ON rate_limit_entries(expires_at);
        CREATE TABLE kv_store (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            expires_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.close()

    with patch("app.sqlite_kv._DB_PATH", db_path):
        yield db_path


# ===========================================================================
# KV store tests
# ===========================================================================


class TestKVStore:
    """Tests for kv_set / kv_get / kv_take / kv_delete / kv_exists."""

    def test_set_and_get(self, sqlite_db):
        from app.sqlite_kv import kv_get, kv_set

        kv_set("hello", "world")
        assert kv_get("hello") == "world"

    def test_get_missing_key_returns_none(self, sqlite_db):
        from app.sqlite_kv import kv_get

        assert kv_get("nonexistent") is None

    def test_set_overwrites_existing(self, sqlite_db):
        from app.sqlite_kv import kv_get, kv_set

        kv_set("key", "v1")
        kv_set("key", "v2")
        assert kv_get("key") == "v2"

    def test_delete_existing_key(self, sqlite_db):
        from app.sqlite_kv import kv_delete, kv_get, kv_set

        kv_set("key", "val")
        assert kv_delete("key") is True
        assert kv_get("key") is None

    def test_delete_missing_key_returns_false(self, sqlite_db):
        from app.sqlite_kv import kv_delete

        assert kv_delete("nope") is False

    def test_exists(self, sqlite_db):
        from app.sqlite_kv import kv_exists, kv_set

        assert kv_exists("key") is False
        kv_set("key", "val")
        assert kv_exists("key") is True

    def test_take_returns_value_and_removes(self, sqlite_db):
        from app.sqlite_kv import kv_exists, kv_set, kv_take

        kv_set("take-me", "payload")
        result = kv_take("take-me")
        assert result == "payload"
        assert kv_exists("take-me") is False

    def test_take_missing_key_returns_none(self, sqlite_db):
        from app.sqlite_kv import kv_take

        assert kv_take("gone") is None

    def test_take_is_atomic(self, sqlite_db):
        """Two consecutive takes: only the first should get the value."""
        from app.sqlite_kv import kv_set, kv_take

        kv_set("once", "value")
        first = kv_take("once")
        second = kv_take("once")
        assert first == "value"
        assert second is None

    def test_ttl_expiry(self, sqlite_db):
        """Expired keys should not be returned by kv_get."""
        from app.sqlite_kv import kv_get, kv_set

        # Set with 1-second TTL
        kv_set("ephemeral", "data", ttl_seconds=1)
        assert kv_get("ephemeral") == "data"

        # Wait for expiry (2s to account for SQLite datetime second resolution)
        time.sleep(2.0)
        assert kv_get("ephemeral") is None

    def test_take_expired_key_returns_none(self, sqlite_db):
        from app.sqlite_kv import kv_set, kv_take

        kv_set("exp", "data", ttl_seconds=1)
        time.sleep(2.0)
        assert kv_take("exp") is None


# ===========================================================================
# Idempotency lock tests
# ===========================================================================


class TestIdempotencyLock:
    """Tests for idempotency_try_acquire / get_lock / store_result / get_result / release_lock."""

    def test_acquire_lock(self, sqlite_db):
        from app.sqlite_kv import idempotency_try_acquire

        assert idempotency_try_acquire("key1", "lock-a", 60) is True

    def test_double_acquire_fails(self, sqlite_db):
        from app.sqlite_kv import idempotency_try_acquire

        assert idempotency_try_acquire("key1", "lock-a", 60) is True
        assert idempotency_try_acquire("key1", "lock-b", 60) is False

    def test_get_lock_value(self, sqlite_db):
        from app.sqlite_kv import idempotency_get_lock, idempotency_try_acquire

        idempotency_try_acquire("key1", "my-lock", 60)
        assert idempotency_get_lock("key1") == "my-lock"

    def test_get_lock_missing_returns_none(self, sqlite_db):
        from app.sqlite_kv import idempotency_get_lock

        assert idempotency_get_lock("missing") is None

    def test_store_and_get_result(self, sqlite_db):
        from app.sqlite_kv import (
            idempotency_get_result,
            idempotency_store_result,
            idempotency_try_acquire,
        )

        idempotency_try_acquire("key1", "lock", 60)
        idempotency_store_result("key1", '{"status": "ok"}', 300)
        assert idempotency_get_result("key1") == '{"status": "ok"}'

    def test_store_result_clears_lock(self, sqlite_db):
        from app.sqlite_kv import (
            idempotency_get_lock,
            idempotency_store_result,
            idempotency_try_acquire,
        )

        idempotency_try_acquire("key1", "lock", 60)
        idempotency_store_result("key1", "result", 300)
        assert idempotency_get_lock("key1") is None

    def test_release_lock_deletes_entry(self, sqlite_db):
        from app.sqlite_kv import (
            idempotency_get_lock,
            idempotency_release_lock,
            idempotency_try_acquire,
        )

        idempotency_try_acquire("key1", "lock", 60)
        idempotency_release_lock("key1")
        assert idempotency_get_lock("key1") is None

    def test_release_lock_preserves_result(self, sqlite_db):
        """Release should not delete entries that have a stored result."""
        from app.sqlite_kv import (
            idempotency_get_result,
            idempotency_release_lock,
            idempotency_store_result,
            idempotency_try_acquire,
        )

        idempotency_try_acquire("key1", "lock", 60)
        idempotency_store_result("key1", "cached", 300)
        idempotency_release_lock("key1")
        assert idempotency_get_result("key1") == "cached"

    def test_get_result_missing_returns_none(self, sqlite_db):
        from app.sqlite_kv import idempotency_get_result

        assert idempotency_get_result("nope") is None


# ===========================================================================
# Rate limit tests
# ===========================================================================


class TestRateLimit:
    """Tests for rate_limit_check_and_record / rate_limit_check_only."""

    def test_first_request_returns_zero_cost(self, sqlite_db):
        from app.sqlite_kv import rate_limit_check_and_record

        current_cost, _ = rate_limit_check_and_record(
            "client-1", cost=5, window_seconds=60
        )
        assert current_cost == 0

    def test_cost_accumulates(self, sqlite_db):
        from app.sqlite_kv import rate_limit_check_and_record

        rate_limit_check_and_record("client-1", cost=5, window_seconds=60)
        current_cost, _ = rate_limit_check_and_record(
            "client-1", cost=3, window_seconds=60
        )
        assert current_cost == 5

    def test_different_clients_isolated(self, sqlite_db):
        from app.sqlite_kv import rate_limit_check_and_record

        rate_limit_check_and_record("client-a", cost=10, window_seconds=60)
        current_cost, _ = rate_limit_check_and_record(
            "client-b", cost=1, window_seconds=60
        )
        assert current_cost == 0

    def test_check_only_does_not_record(self, sqlite_db):
        from app.sqlite_kv import rate_limit_check_and_record, rate_limit_check_only

        rate_limit_check_and_record("client-1", cost=5, window_seconds=60)
        cost1, _ = rate_limit_check_only("client-1", window_seconds=60)
        cost2, _ = rate_limit_check_only("client-1", window_seconds=60)
        assert cost1 == cost2 == 5

    def test_expired_entries_cleaned(self, sqlite_db):
        from app.sqlite_kv import rate_limit_check_and_record

        # Record with 1-second window (expires quickly)
        rate_limit_check_and_record("client-1", cost=10, window_seconds=1)
        time.sleep(1.5)

        # After expiry, cost should be zero
        current_cost, _ = rate_limit_check_and_record(
            "client-1", cost=1, window_seconds=60
        )
        assert current_cost == 0

    def test_oldest_time_returned(self, sqlite_db):
        from app.sqlite_kv import rate_limit_check_and_record

        before = time.time()
        rate_limit_check_and_record("client-1", cost=1, window_seconds=60)
        _, oldest_time = rate_limit_check_and_record(
            "client-1", cost=1, window_seconds=60
        )
        assert oldest_time >= before
