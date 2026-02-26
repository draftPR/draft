"""Tests for idempotency and rate limiting middleware.

These tests verify failure modes and edge cases for the SQLite-backed middleware.
"""

import sqlite3
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.idempotency import IdempotencyMiddleware
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
# Shared SQLite fixture
# =============================================================================


@pytest.fixture
def sqlite_test_db(tmp_path):
    """Create a temporary SQLite database with all required tables."""
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

    with patch("app.sqlite_kv._DB_PATH", db_path):
        yield db_path


# =============================================================================
# Idempotency Tests
# =============================================================================


class TestIdempotencyMiddleware:
    """Tests for IdempotencyMiddleware with SQLite backend."""

    def test_first_request_executes(self, sqlite_test_db):
        """First request acquires lock via SQLite INSERT OR IGNORE."""
        app = create_test_app(with_idempotency=True)
        client = TestClient(app)

        response = client.post(
            "/goals/123/generate-tickets",
            json={},
            headers={"Idempotency-Key": "test-1"},
        )
        assert response.status_code == 200
        assert response.headers.get("X-Execution-ID") is not None

    def test_cached_response_returned(self, sqlite_test_db):
        """Second request with same key returns cached response."""
        app = create_test_app(with_idempotency=True)
        client = TestClient(app)

        # First request
        response1 = client.post(
            "/goals/123/generate-tickets",
            json={},
            headers={
                "Idempotency-Key": "test-cache",
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
                "Idempotency-Key": "test-cache",
                "X-Client-ID": "test-client",
            },
        )
        assert response2.status_code == 200
        assert response2.headers.get("X-Idempotency-Replayed") == "true"
        data2 = response2.json()
        assert data1["timestamp"] == data2["timestamp"]

    def test_different_body_returns_409(self, sqlite_test_db):
        """Same key + different body returns 409."""
        app = create_test_app(with_idempotency=True)
        client = TestClient(app)

        # First request
        client.post(
            "/goals/123/generate-tickets",
            json={"body": "original"},
            headers={
                "Idempotency-Key": "test-conflict",
                "X-Client-ID": "test-client",
            },
        )

        # Second request with different body
        response = client.post(
            "/goals/123/generate-tickets",
            json={"body": "different"},
            headers={
                "Idempotency-Key": "test-conflict",
                "X-Client-ID": "test-client",
            },
        )
        assert response.status_code == 409

    def test_no_idempotency_key_processes_normally(self, sqlite_test_db):
        """Requests without idempotency key should process normally."""
        app = create_test_app(with_idempotency=True)
        client = TestClient(app)

        response = client.post(
            "/goals/123/generate-tickets",
            json={},
        )
        assert response.status_code == 200

    def test_idempotency_key_too_long_returns_400(self):
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

    def test_non_idempotent_endpoints_bypass_middleware(self, sqlite_test_db):
        """Endpoints not in IDEMPOTENT_ENDPOINTS should bypass middleware."""
        app = create_test_app(with_idempotency=True)
        client = TestClient(app)

        response = client.post(
            "/other",
            json={},
            headers={"Idempotency-Key": "test-key"},
        )
        assert response.status_code == 200


# =============================================================================
# Rate Limit Tests
# =============================================================================


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware with SQLite backend."""

    def test_rate_limit_allows_within_budget(self, sqlite_test_db):
        """Requests within budget should succeed."""
        app = create_test_app(with_rate_limit=True, rate_limit_budget=100)
        client = TestClient(app)

        response = client.post(
            "/goals/123/generate-tickets",
            json={},
        )
        assert response.status_code == 200
        assert response.headers.get("X-RateLimit-Limit") == "100"

    def test_rate_limit_blocks_when_exceeded(self, sqlite_test_db):
        """Requests exceeding budget should get 429."""
        app = create_test_app(
            with_rate_limit=True, rate_limit_budget=5, rate_limit_window=60
        )
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

    def test_rate_limit_headers_present_on_success(self, sqlite_test_db):
        """Successful requests should include rate limit headers."""
        app = create_test_app(with_rate_limit=True, rate_limit_budget=100)
        client = TestClient(app)

        response = client.post(
            "/goals/123/generate-tickets",
            json={},
        )
        assert response.status_code == 200
        assert response.headers.get("X-RateLimit-Limit") == "100"
        assert response.headers.get("X-RateLimit-Remaining") is not None
        assert response.headers.get("X-RateLimit-Reset") is not None

    def test_non_rate_limited_endpoints_bypass_middleware(self, sqlite_test_db):
        """Endpoints not in RATE_LIMITED_ENDPOINTS should bypass middleware."""
        app = create_test_app(with_rate_limit=True)
        client = TestClient(app)

        response = client.post("/other", json={})
        assert response.status_code == 200
        assert response.headers.get("X-RateLimit-Limit") is None
