"""Tests for idempotency and rate limiting middleware.

These tests verify failure modes and edge cases for the middleware.
Tests cover both Redis and SQLite backends.
"""

import json
import os
import sqlite3
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.idempotency import IdempotencyMiddleware, _compute_body_hash
from app.middleware.rate_limit import RateLimitMiddleware

# =============================================================================
# Test App Setup
# =============================================================================


def create_test_app(
    with_idempotency: bool = False,
    with_rate_limit: bool = False,
    rate_limit_budget: int = 100,  # Cost-based budget
    rate_limit_window: int = 60,
):
    """Create a test FastAPI app with specified middleware."""
    app = FastAPI()

    @app.post("/goals/{goal_id}/generate-tickets")
    async def generate_tickets(goal_id: str):
        return {"tickets": [], "goal_id": goal_id, "timestamp": time.time()}

    @app.post("/goals/{goal_id}/reflect-on-tickets")
    async def reflect_on_tickets(goal_id: str):
        return {"quality": "good", "timestamp": time.time()}

    @app.post("/other")
    async def other_endpoint():
        return {"status": "ok"}

    if with_rate_limit:
        app.add_middleware(
            RateLimitMiddleware,
            budget=rate_limit_budget,
            window_seconds=rate_limit_window,
        )

    if with_idempotency:
        app.add_middleware(IdempotencyMiddleware)

    return app


# =============================================================================
# Idempotency Tests (Redis backend)
# =============================================================================


class TestIdempotencyMiddleware:
    """Tests for IdempotencyMiddleware with Redis backend."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client for tests."""
        mock = MagicMock()
        mock.ping.return_value = True
        mock.set.return_value = True  # Lock acquired
        mock.get.return_value = None
        mock.setex.return_value = True
        mock.delete.return_value = 1
        mock.exists.return_value = False
        return mock

    def _patch_redis_backend(self, mock_redis):
        """Return context managers for patching to use Redis backend."""
        return (
            patch("app.task_backend._TASK_BACKEND", "redis"),
            patch("app.task_backend._SMART_KANBAN_MODE", ""),
            patch("app.redis_client.redis_available", return_value=True),
            patch("app.redis_client.get_redis", return_value=mock_redis),
        )

    def test_same_key_same_body_returns_cached_response(self, mock_redis):
        """Same idempotency key + same body should return exact same response."""
        app = create_test_app(with_idempotency=True)

        body_hash = _compute_body_hash(b"{}")
        cached_response = {
            "status_code": 200,
            "body": '{"tickets": [], "goal_id": "123", "timestamp": 1234567890}',
            "body_hash": body_hash,
            "completed_at": time.time(),
        }

        mock_redis.set.return_value = False  # Lock not acquired
        mock_redis.get.return_value = json.dumps(cached_response)

        p1, p2, p3, p4 = self._patch_redis_backend(mock_redis)
        with p1, p2, p3, p4:
            client = TestClient(app)

            response = client.post(
                "/goals/123/generate-tickets",
                json={},
                headers={"Idempotency-Key": "test-key-1"},
            )
            assert response.status_code == 200
            assert response.headers.get("X-Idempotency-Replayed") == "true"

    def test_first_request_executes_and_caches(self, mock_redis):
        """First request with idempotency key acquires lock, executes, and caches."""
        app = create_test_app(with_idempotency=True)

        mock_redis.set.return_value = True  # Lock acquired
        mock_redis.get.return_value = None

        p1, p2, p3, p4 = self._patch_redis_backend(mock_redis)
        with p1, p2, p3, p4:
            client = TestClient(app)

            response = client.post(
                "/goals/123/generate-tickets",
                json={},
                headers={"Idempotency-Key": "test-key-new"},
            )
            assert response.status_code == 200
            mock_redis.setex.assert_called_once()
            mock_redis.delete.assert_called_once()

    def test_same_key_different_body_returns_409(self, mock_redis):
        """Same idempotency key + different body should return 409 Conflict."""
        app = create_test_app(with_idempotency=True)

        mock_redis.set.return_value = False

        cached_response = {
            "status_code": 200,
            "body": '{"tickets": [], "goal_id": "123"}',
            "body_hash": "different_hash_12345",
            "completed_at": time.time(),
        }
        mock_redis.get.return_value = json.dumps(cached_response)

        p1, p2, p3, p4 = self._patch_redis_backend(mock_redis)
        with p1, p2, p3, p4:
            client = TestClient(app)

            response = client.post(
                "/goals/123/generate-tickets",
                json={"different": "body"},
                headers={"Idempotency-Key": "test-key-conflict"},
            )

            assert response.status_code == 409
            data = response.json()
            assert "already used with different request body" in data["detail"]
            assert data["error_type"] == "idempotency_conflict"

    def test_no_idempotency_key_processes_normally(self, mock_redis):
        """Requests without idempotency key should process normally."""
        app = create_test_app(with_idempotency=True)

        p1, p2, p3, p4 = self._patch_redis_backend(mock_redis)
        with p1, p2, p3, p4:
            client = TestClient(app)

            response = client.post(
                "/goals/123/generate-tickets",
                json={},
            )

            assert response.status_code == 200
            mock_redis.set.assert_not_called()

    def test_idempotency_key_too_long_returns_400(self, mock_redis):
        """Idempotency key longer than 64 chars should return 400."""
        app = create_test_app(with_idempotency=True)
        client = TestClient(app)

        response = client.post(
            "/goals/123/generate-tickets",
            json={},
            headers={"Idempotency-Key": "x" * 100},
        )

        assert response.status_code == 400
        assert "too long" in response.json()["detail"]

    def test_non_idempotent_endpoints_bypass_middleware(self, mock_redis):
        """Endpoints not in IDEMPOTENT_ENDPOINTS should bypass middleware."""
        app = create_test_app(with_idempotency=True)

        p1, p2, p3, p4 = self._patch_redis_backend(mock_redis)
        with p1, p2, p3, p4:
            client = TestClient(app)

            response = client.post(
                "/other",
                json={},
                headers={"Idempotency-Key": "test-key"},
            )

            assert response.status_code == 200
            mock_redis.get.assert_not_called()

    def test_redis_unavailable_returns_503(self):
        """When Redis is unavailable, mutating endpoints return 503."""
        app = create_test_app(with_idempotency=True)

        with (
            patch("app.task_backend._TASK_BACKEND", "redis"),
            patch("app.task_backend._SMART_KANBAN_MODE", ""),
            patch("app.redis_client.redis_available", return_value=False),
        ):
            client = TestClient(app)

            response = client.post(
                "/goals/123/generate-tickets",
                json={},
                headers={"Idempotency-Key": "test-key"},
            )

            assert response.status_code == 503
            data = response.json()
            assert data["error_type"] == "service_unavailable"

    def test_redis_unavailable_without_idempotency_key_returns_503(self):
        """Even without idempotency key, backend unavailable = 503 for mutating endpoints."""
        app = create_test_app(with_idempotency=True)

        with (
            patch("app.task_backend._TASK_BACKEND", "redis"),
            patch("app.task_backend._SMART_KANBAN_MODE", ""),
            patch("app.redis_client.redis_available", return_value=False),
        ):
            client = TestClient(app)

            response = client.post(
                "/goals/123/generate-tickets",
                json={},
            )

            assert response.status_code == 503


# =============================================================================
# Idempotency Tests (SQLite backend)
# =============================================================================


class TestIdempotencyMiddlewareSQLite:
    """Tests for IdempotencyMiddleware with SQLite backend."""

    @pytest.fixture(autouse=True)
    def setup_sqlite_db(self, tmp_path):
        """Create a temporary SQLite database with the required tables."""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE idempotency_cache (
                cache_key TEXT PRIMARY KEY,
                lock_value TEXT,
                result_value TEXT,
                lock_expires_at TIMESTAMP,
                result_expires_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE rate_limit_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_key TEXT NOT NULL,
                cost INTEGER NOT NULL DEFAULT 1,
                recorded_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE kv_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

        # Patch the DB path used by sqlite_kv
        with (
            patch("app.sqlite_kv._DB_PATH", db_path),
            patch("app.task_backend._TASK_BACKEND", "sqlite"),
            patch("app.task_backend._SMART_KANBAN_MODE", ""),
        ):
            yield

    def test_first_request_executes_with_sqlite(self):
        """First request acquires lock via SQLite INSERT OR IGNORE."""
        app = create_test_app(with_idempotency=True)
        client = TestClient(app)

        response = client.post(
            "/goals/123/generate-tickets",
            json={},
            headers={"Idempotency-Key": "sqlite-test-1"},
        )
        assert response.status_code == 200
        assert response.headers.get("X-Execution-ID") is not None

    def test_cached_response_returned_with_sqlite(self):
        """Second request with same key returns cached response."""
        app = create_test_app(with_idempotency=True)
        client = TestClient(app)

        # First request
        response1 = client.post(
            "/goals/123/generate-tickets",
            json={},
            headers={
                "Idempotency-Key": "sqlite-test-cache",
                "X-Client-ID": "test-client",
            },
        )
        assert response1.status_code == 200
        data1 = response1.json()

        # Second request - should get cached
        response2 = client.post(
            "/goals/123/generate-tickets",
            json={},
            headers={
                "Idempotency-Key": "sqlite-test-cache",
                "X-Client-ID": "test-client",
            },
        )
        assert response2.status_code == 200
        assert response2.headers.get("X-Idempotency-Replayed") == "true"
        data2 = response2.json()
        assert data1["timestamp"] == data2["timestamp"]

    def test_different_body_returns_409_with_sqlite(self):
        """Same key + different body returns 409."""
        app = create_test_app(with_idempotency=True)
        client = TestClient(app)

        # First request
        client.post(
            "/goals/123/generate-tickets",
            json={"body": "original"},
            headers={
                "Idempotency-Key": "sqlite-conflict",
                "X-Client-ID": "test-client",
            },
        )

        # Second request with different body
        response = client.post(
            "/goals/123/generate-tickets",
            json={"body": "different"},
            headers={
                "Idempotency-Key": "sqlite-conflict",
                "X-Client-ID": "test-client",
            },
        )
        assert response.status_code == 409


# =============================================================================
# Rate Limit Tests (Redis backend)
# =============================================================================


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware with Redis backend."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client for tests."""
        mock = MagicMock()
        mock.ping.return_value = True

        pipe_mock = MagicMock()
        pipe_mock.zremrangebyscore.return_value = pipe_mock
        pipe_mock.zrange.return_value = pipe_mock
        pipe_mock.execute.return_value = [0, []]
        mock.pipeline.return_value = pipe_mock

        mock.zadd.return_value = 1
        mock.expire.return_value = True
        return mock

    def _patch_redis_backend(self, mock_redis):
        """Return context managers for patching to use Redis backend."""
        return (
            patch("app.task_backend._TASK_BACKEND", "redis"),
            patch("app.task_backend._SMART_KANBAN_MODE", ""),
            patch("app.redis_client.redis_available", return_value=True),
            patch("app.redis_client.get_redis", return_value=mock_redis),
        )

    def test_burst_exceeds_rate_limit_returns_429(self, mock_redis):
        """Bursts that exceed rate limit should return 429."""
        app = create_test_app(with_rate_limit=True, rate_limit_budget=10)

        now = time.time()
        pipe_mock = mock_redis.pipeline.return_value
        pipe_mock.execute.return_value = [
            0,
            [(f"{now-10}:100", now - 10)]
        ]

        p1, p2, p3, p4 = self._patch_redis_backend(mock_redis)
        with p1, p2, p3, p4:
            client = TestClient(app)

            response = client.post(
                "/goals/123/generate-tickets",
                json={},
            )

            assert response.status_code == 429
            data = response.json()
            assert "Rate limit exceeded" in data["detail"]
            assert "retry_after_seconds" in data
            assert response.headers.get("Retry-After") is not None

    def test_retry_after_header_is_present_and_sane(self, mock_redis):
        """429 responses should include sane Retry-After header."""
        app = create_test_app(with_rate_limit=True, rate_limit_budget=10, rate_limit_window=60)

        now = time.time()
        pipe_mock = mock_redis.pipeline.return_value
        oldest_time = now - 30
        pipe_mock.execute.return_value = [
            0,
            [(f"{oldest_time}:100", oldest_time)]
        ]

        p1, p2, p3, p4 = self._patch_redis_backend(mock_redis)
        with p1, p2, p3, p4:
            client = TestClient(app)

            response = client.post(
                "/goals/123/generate-tickets",
                json={},
            )

            assert response.status_code == 429
            retry_after = int(response.headers.get("Retry-After", "0"))
            assert 1 <= retry_after <= 60

    def test_rate_limit_headers_present_on_success(self, mock_redis):
        """Successful requests should include rate limit headers."""
        app = create_test_app(with_rate_limit=True, rate_limit_budget=100)

        now = time.time()
        pipe_mock = mock_redis.pipeline.return_value
        pipe_mock.execute.return_value = [0, [(f"{now-5}:2", now - 5)]]

        p1, p2, p3, p4 = self._patch_redis_backend(mock_redis)
        with p1, p2, p3, p4:
            client = TestClient(app)

            response = client.post(
                "/goals/123/generate-tickets",
                json={},
            )

            assert response.status_code == 200
            assert response.headers.get("X-RateLimit-Limit") == "100"
            assert response.headers.get("X-RateLimit-Remaining") is not None
            assert response.headers.get("X-RateLimit-Reset") is not None
            assert response.headers.get("X-RateLimit-Estimated-Cost") is not None
            assert response.headers.get("X-RateLimit-Actual-Cost") is not None

    def test_non_rate_limited_endpoints_bypass_middleware(self, mock_redis):
        """Endpoints not in RATE_LIMITED_ENDPOINTS should bypass middleware."""
        app = create_test_app(with_rate_limit=True)

        p1, p2, p3, p4 = self._patch_redis_backend(mock_redis)
        with p1, p2, p3, p4:
            client = TestClient(app)

            response = client.post("/other", json={})

            assert response.status_code == 200
            assert response.headers.get("X-RateLimit-Limit") is None

    def test_redis_unavailable_returns_503(self):
        """When Redis is unavailable, rate-limited endpoints return 503."""
        app = create_test_app(with_rate_limit=True, rate_limit_budget=100)

        with (
            patch("app.task_backend._TASK_BACKEND", "redis"),
            patch("app.task_backend._SMART_KANBAN_MODE", ""),
            patch("app.redis_client.redis_available", return_value=False),
        ):
            client = TestClient(app)

            response = client.post(
                "/goals/123/generate-tickets",
                json={},
            )

            assert response.status_code == 503
            data = response.json()
            assert data["error_type"] == "service_unavailable"

    def test_client_id_from_header_takes_precedence(self, mock_redis):
        """X-Client-ID header should be used over IP for rate limiting."""
        app = create_test_app(with_rate_limit=True, rate_limit_budget=100)
        pipe_mock = mock_redis.pipeline.return_value
        pipe_mock.execute.return_value = [0, []]

        p1, p2, p3, p4 = self._patch_redis_backend(mock_redis)
        with p1, p2, p3, p4:
            client = TestClient(app)

            response = client.post(
                "/goals/123/generate-tickets",
                json={},
                headers={"X-Client-ID": "unique-client-123"},
            )

            assert response.status_code == 200
            zadd_call = mock_redis.zadd.call_args
            if zadd_call:
                redis_key = zadd_call[0][0]
                assert "unique-client-123" in redis_key


# =============================================================================
# Rate Limit Tests (SQLite backend)
# =============================================================================


class TestRateLimitMiddlewareSQLite:
    """Tests for RateLimitMiddleware with SQLite backend."""

    @pytest.fixture(autouse=True)
    def setup_sqlite_db(self, tmp_path):
        """Create a temporary SQLite database with the required tables."""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE rate_limit_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_key TEXT NOT NULL,
                cost INTEGER NOT NULL DEFAULT 1,
                recorded_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE idempotency_cache (
                cache_key TEXT PRIMARY KEY,
                lock_value TEXT,
                result_value TEXT,
                lock_expires_at TIMESTAMP,
                result_expires_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE kv_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

        with (
            patch("app.sqlite_kv._DB_PATH", db_path),
            patch("app.task_backend._TASK_BACKEND", "sqlite"),
            patch("app.task_backend._SMART_KANBAN_MODE", ""),
        ):
            yield

    def test_rate_limit_allows_within_budget(self):
        """Requests within budget should succeed."""
        app = create_test_app(with_rate_limit=True, rate_limit_budget=100)
        client = TestClient(app)

        response = client.post(
            "/goals/123/generate-tickets",
            json={},
        )
        assert response.status_code == 200
        assert response.headers.get("X-RateLimit-Limit") == "100"

    def test_rate_limit_blocks_when_exceeded(self):
        """Requests exceeding budget should get 429."""
        # Very low budget
        app = create_test_app(with_rate_limit=True, rate_limit_budget=5, rate_limit_window=60)
        client = TestClient(app)

        # Make requests until rate limited
        got_429 = False
        for _ in range(10):
            response = client.post(
                "/goals/123/generate-tickets",
                json={},
            )
            if response.status_code == 429:
                got_429 = True
                break

        assert got_429, "Should have been rate limited"
        data = response.json()
        assert "Rate limit exceeded" in data["detail"]


# =============================================================================
# Integration Tests (require real Redis)
# =============================================================================


@pytest.mark.integration
class TestMiddlewareIntegration:
    """Integration tests that require real Redis.

    Run with: pytest -m integration
    """

    def test_idempotency_full_flow(self):
        """Full idempotency flow with real Redis."""
        from app.redis_client import FallbackCache, get_redis

        redis = get_redis()
        if isinstance(redis, FallbackCache):
            pytest.skip("Real Redis not available (using in-memory fallback)")

        app = create_test_app(with_idempotency=True)
        client = TestClient(app)

        test_key = "integration-test-key"

        with (
            patch("app.task_backend._TASK_BACKEND", "redis"),
            patch("app.task_backend._SMART_KANBAN_MODE", ""),
        ):
            # First request
            response1 = client.post(
                "/goals/123/generate-tickets",
                json={"test": "data"},
                headers={
                    "Idempotency-Key": test_key,
                    "X-Client-ID": "integration-test-client",
                },
            )
            assert response1.status_code == 200
            data1 = response1.json()

            # Second request - should return cached
            response2 = client.post(
                "/goals/123/generate-tickets",
                json={"test": "data"},
                headers={
                    "Idempotency-Key": test_key,
                    "X-Client-ID": "integration-test-client",
                },
            )
            assert response2.status_code == 200
            assert response2.headers.get("X-Idempotency-Replayed") == "true"
            data2 = response2.json()

            assert data1["timestamp"] == data2["timestamp"]

    def test_rate_limit_full_flow(self):
        """Full rate limit flow with real Redis."""
        from app.redis_client import redis_available

        if not redis_available():
            pytest.skip("Redis not available")

        app = create_test_app(with_rate_limit=True, rate_limit_budget=5, rate_limit_window=60)
        client = TestClient(app)

        client_id = f"rate-limit-test-{time.time()}"

        with (
            patch("app.task_backend._TASK_BACKEND", "redis"),
            patch("app.task_backend._SMART_KANBAN_MODE", ""),
        ):
            for i in range(3):
                response = client.post(
                    "/goals/123/generate-tickets",
                    json={},
                    headers={"X-Client-ID": client_id},
                )
                assert response.status_code == 200, f"Request {i+1} failed"

            for _ in range(10):
                response = client.post(
                    "/goals/123/generate-tickets",
                    json={},
                    headers={"X-Client-ID": client_id},
                )
                if response.status_code == 429:
                    break

            assert response.status_code == 429

    def test_idempotency_concurrency(self):
        """Test that concurrent requests with same idempotency key work correctly."""
        import concurrent.futures
        import threading

        from app.redis_client import get_redis, redis_available

        if not redis_available():
            pytest.skip("Redis not available")

        from fastapi import FastAPI

        from app.middleware.idempotency import IdempotencyMiddleware

        side_effect_counter = {"count": 0}
        counter_lock = threading.Lock()

        app = FastAPI()

        @app.post("/goals/{goal_id}/generate-tickets")
        async def generate_tickets(goal_id: str):
            with counter_lock:
                side_effect_counter["count"] += 1
                current_count = side_effect_counter["count"]

            import asyncio
            await asyncio.sleep(0.1)

            return {
                "tickets": [],
                "goal_id": goal_id,
                "execution_id": current_count,
            }

        app.add_middleware(IdempotencyMiddleware)

        get_redis()

        test_key = f"concurrency-test-{time.time()}"
        client_id = f"concurrency-client-{time.time()}"

        def make_request():
            client = TestClient(app)
            return client.post(
                "/goals/123/generate-tickets",
                json={"test": "concurrent"},
                headers={
                    "Idempotency-Key": test_key,
                    "X-Client-ID": client_id,
                },
            )

        with (
            patch("app.task_backend._TASK_BACKEND", "redis"),
            patch("app.task_backend._SMART_KANBAN_MODE", ""),
        ):
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(make_request) for _ in range(10)]
                responses = [f.result() for f in concurrent.futures.as_completed(futures)]

        success_responses = []
        processing_responses = []
        for r in responses:
            assert r.status_code in (200, 202), f"Got unexpected status {r.status_code}: {r.text}"
            if r.status_code == 200:
                success_responses.append(r)
            else:
                processing_responses.append(r)

        if success_responses:
            execution_ids = [r.json()["execution_id"] for r in success_responses]
            assert len(set(execution_ids)) == 1, f"Got different execution IDs: {execution_ids}"

        replayed_count = sum(
            1 for r in success_responses
            if r.headers.get("X-Idempotency-Replayed") == "true"
        )

        non_original_count = replayed_count + len(processing_responses)
        assert non_original_count >= 9, (
            f"Only {non_original_count} were replayed/processing "
            f"(replayed={replayed_count}, processing={len(processing_responses)})"
        )

        assert side_effect_counter["count"] == 1, (
            f"Side effect happened {side_effect_counter['count']} times - "
            f"IDEMPOTENCY VIOLATION! Must be exactly 1."
        )
