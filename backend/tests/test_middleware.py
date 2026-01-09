"""Tests for idempotency and rate limiting middleware.

These tests verify failure modes and edge cases for the middleware.
Requires Redis to be running for full integration tests.
"""

import json
import time
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

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
# Idempotency Tests
# =============================================================================


class TestIdempotencyMiddleware:
    """Tests for IdempotencyMiddleware."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client for tests.
        
        The new idempotency implementation uses:
        - set(key, value, nx=True, ex=TTL) for acquiring the lock
        - get(result_key) for checking results
        - setex(result_key, TTL, data) for storing results  
        - delete(lock_key) for releasing lock
        """
        mock = MagicMock()
        mock.ping.return_value = True
        mock.set.return_value = True  # Lock acquired
        mock.get.return_value = None
        mock.setex.return_value = True
        mock.delete.return_value = 1
        mock.exists.return_value = False
        return mock

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
        
        # Simulate: lock already taken, result already cached
        # This tests the "wait for result" path
        mock_redis.set.return_value = False  # Lock not acquired (another req has it)
        mock_redis.get.return_value = json.dumps(cached_response)  # Result already cached
        mock_redis.exists.return_value = False  # Lock released
        
        with patch("app.middleware.idempotency.redis_available", return_value=True):
            with patch("app.middleware.idempotency.get_redis", return_value=mock_redis):
                client = TestClient(app)

                # Request should see cached result
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
        
        # Simulate: lock acquired successfully, no existing result
        mock_redis.set.return_value = True  # Lock acquired
        mock_redis.get.return_value = None  # No cached result
        
        with patch("app.middleware.idempotency.redis_available", return_value=True):
            with patch("app.middleware.idempotency.get_redis", return_value=mock_redis):
                client = TestClient(app)

                response = client.post(
                    "/goals/123/generate-tickets",
                    json={},
                    headers={"Idempotency-Key": "test-key-new"},
                )
                assert response.status_code == 200
                
                # Should have stored result
                mock_redis.setex.assert_called_once()
                # Should have released lock
                mock_redis.delete.assert_called_once()

    def test_same_key_different_body_returns_409(self, mock_redis):
        """Same idempotency key + different body should return 409 Conflict."""
        app = create_test_app(with_idempotency=True)

        # Mock: lock already taken and result already cached with different hash
        mock_redis.set.return_value = False  # Lock not acquired (already exists)
        
        cached_response = {
            "status_code": 200,
            "body": '{"tickets": [], "goal_id": "123"}',
            "body_hash": "different_hash_12345",  # Different from request body hash
            "completed_at": time.time(),
        }
        mock_redis.get.return_value = json.dumps(cached_response)

        with patch("app.middleware.idempotency.redis_available", return_value=True):
            with patch("app.middleware.idempotency.get_redis", return_value=mock_redis):
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

        with patch("app.middleware.idempotency.redis_available", return_value=True):
            with patch("app.middleware.idempotency.get_redis", return_value=mock_redis):
                client = TestClient(app)

                response = client.post(
                    "/goals/123/generate-tickets",
                    json={},
                )

                assert response.status_code == 200
                # Without idempotency key, lock acquisition should not be attempted
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

        with patch("app.middleware.idempotency.redis_available", return_value=True):
            with patch("app.middleware.idempotency.get_redis", return_value=mock_redis):
                client = TestClient(app)

                response = client.post(
                    "/other",
                    json={},
                    headers={"Idempotency-Key": "test-key"},
                )

                assert response.status_code == 200
                # Redis should not be called
                mock_redis.get.assert_not_called()

    def test_redis_unavailable_returns_503(self):
        """When Redis is unavailable, mutating endpoints return 503."""
        app = create_test_app(with_idempotency=True)

        with patch("app.middleware.idempotency.redis_available", return_value=False):
            client = TestClient(app)

            response = client.post(
                "/goals/123/generate-tickets",
                json={},
                headers={"Idempotency-Key": "test-key"},
            )

            # CRITICAL: Must return 503, not silently degrade
            assert response.status_code == 503
            data = response.json()
            assert "Redis" in data["detail"]
            assert data["error_type"] == "service_unavailable"

    def test_redis_unavailable_without_idempotency_key_returns_503(self):
        """Even without idempotency key, Redis unavailable = 503 for mutating endpoints."""
        app = create_test_app(with_idempotency=True)

        with patch("app.middleware.idempotency.redis_available", return_value=False):
            client = TestClient(app)

            response = client.post(
                "/goals/123/generate-tickets",
                json={},
                # No Idempotency-Key header
            )

            # CRITICAL: Must return 503 for mutating endpoints
            assert response.status_code == 503


# =============================================================================
# Rate Limit Tests
# =============================================================================


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware.
    
    The cost-based rate limiter uses:
    - pipeline().zremrangebyscore().zrange().execute() to clean and get entries
    - Entry format: "timestamp:cost" in sorted set
    - Budget is measured in cost points, not request count
    """

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client for tests."""
        mock = MagicMock()
        mock.ping.return_value = True
        
        # Mock pipeline operations
        pipe_mock = MagicMock()
        pipe_mock.zremrangebyscore.return_value = pipe_mock
        pipe_mock.zrange.return_value = pipe_mock
        pipe_mock.execute.return_value = [0, []]  # [removed_count, entries]
        mock.pipeline.return_value = pipe_mock
        
        mock.zadd.return_value = 1
        mock.expire.return_value = True
        return mock

    def test_burst_exceeds_rate_limit_returns_429(self, mock_redis):
        """Bursts that exceed rate limit should return 429."""
        app = create_test_app(with_rate_limit=True, rate_limit_budget=10)  # Low budget for test

        # Simulate already at limit (100 cost points used)
        now = time.time()
        pipe_mock = mock_redis.pipeline.return_value
        # entries: [(member, score)] where member = "timestamp:cost"
        # Note: Redis returns strings when decode_responses=True (which our client uses)
        pipe_mock.execute.return_value = [
            0,  # removed count
            [(f"{now-10}:100", now - 10)]  # 100 cost points used 10 sec ago
        ]

        with patch("app.middleware.rate_limit.redis_available", return_value=True):
            with patch("app.middleware.rate_limit.get_redis", return_value=mock_redis):
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

        # Simulate budget exhausted
        now = time.time()
        pipe_mock = mock_redis.pipeline.return_value
        oldest_time = now - 30  # 30 seconds ago
        pipe_mock.execute.return_value = [
            0, 
            [(f"{oldest_time}:100", oldest_time)]
        ]

        with patch("app.middleware.rate_limit.redis_available", return_value=True):
            with patch("app.middleware.rate_limit.get_redis", return_value=mock_redis):
                client = TestClient(app)

                response = client.post(
                    "/goals/123/generate-tickets",
                    json={},
                )

                assert response.status_code == 429
                retry_after = int(response.headers.get("Retry-After", "0"))
                # Should be roughly 30 seconds (60 - 30 elapsed)
                assert 1 <= retry_after <= 60

    def test_rate_limit_headers_present_on_success(self, mock_redis):
        """Successful requests should include rate limit headers."""
        app = create_test_app(with_rate_limit=True, rate_limit_budget=100)

        # Simulate within limit (2 cost points used)
        now = time.time()
        pipe_mock = mock_redis.pipeline.return_value
        pipe_mock.execute.return_value = [0, [(f"{now-5}:2", now - 5)]]

        with patch("app.middleware.rate_limit.redis_available", return_value=True):
            with patch("app.middleware.rate_limit.get_redis", return_value=mock_redis):
                client = TestClient(app)

                response = client.post(
                    "/goals/123/generate-tickets",
                    json={},
                )

                assert response.status_code == 200
                assert response.headers.get("X-RateLimit-Limit") == "100"
                assert response.headers.get("X-RateLimit-Remaining") is not None
                assert response.headers.get("X-RateLimit-Reset") is not None
                # Estimated cost header (pre-request gating)
                assert response.headers.get("X-RateLimit-Estimated-Cost") is not None
                # Actual cost header (post-request telemetry)
                assert response.headers.get("X-RateLimit-Actual-Cost") is not None

    def test_non_rate_limited_endpoints_bypass_middleware(self, mock_redis):
        """Endpoints not in RATE_LIMITED_ENDPOINTS should bypass middleware."""
        app = create_test_app(with_rate_limit=True)

        with patch("app.middleware.rate_limit.redis_available", return_value=True):
            with patch("app.middleware.rate_limit.get_redis", return_value=mock_redis):
                client = TestClient(app)

                response = client.post("/other", json={})

                assert response.status_code == 200
                # No rate limit headers on non-limited endpoints
                assert response.headers.get("X-RateLimit-Limit") is None

    def test_redis_unavailable_returns_503(self):
        """When Redis is unavailable, rate-limited endpoints return 503."""
        app = create_test_app(with_rate_limit=True, rate_limit_budget=100)

        with patch("app.middleware.rate_limit.redis_available", return_value=False):
            client = TestClient(app)

            response = client.post(
                "/goals/123/generate-tickets",
                json={},
            )

            # CRITICAL: Must return 503, not silently skip rate limiting
            assert response.status_code == 503
            data = response.json()
            assert "Redis" in data["detail"]
            assert data["error_type"] == "service_unavailable"

    def test_client_id_from_header_takes_precedence(self, mock_redis):
        """X-Client-ID header should be used over IP for rate limiting."""
        app = create_test_app(with_rate_limit=True, rate_limit_budget=100)
        pipe_mock = mock_redis.pipeline.return_value
        pipe_mock.execute.return_value = [0, []]

        with patch("app.middleware.rate_limit.redis_available", return_value=True):
            with patch("app.middleware.rate_limit.get_redis", return_value=mock_redis):
                client = TestClient(app)

                response = client.post(
                    "/goals/123/generate-tickets",
                    json={},
                    headers={"X-Client-ID": "unique-client-123"},
                )

                assert response.status_code == 200
                # Verify the Redis key includes the client ID
                zadd_call = mock_redis.zadd.call_args
                if zadd_call:
                    redis_key = zadd_call[0][0]
                    assert "unique-client-123" in redis_key


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
        from app.redis_client import redis_available, get_redis

        if not redis_available():
            pytest.skip("Redis not available")

        app = create_test_app(with_idempotency=True)
        client = TestClient(app)

        # Clear any existing key
        redis = get_redis()
        test_key = "integration-test-key"

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

        # Timestamps should be the same (cached)
        assert data1["timestamp"] == data2["timestamp"]

    def test_rate_limit_full_flow(self):
        """Full rate limit flow with real Redis."""
        from app.redis_client import redis_available

        if not redis_available():
            pytest.skip("Redis not available")

        # Very low budget for testing (cost-based)
        app = create_test_app(with_rate_limit=True, rate_limit_budget=5, rate_limit_window=60)
        client = TestClient(app)

        client_id = f"rate-limit-test-{time.time()}"

        # First few requests should succeed (base cost = 1)
        for i in range(3):
            response = client.post(
                "/goals/123/generate-tickets",
                json={},
                headers={"X-Client-ID": client_id},
            )
            assert response.status_code == 200, f"Request {i+1} failed"

        # Eventually should hit rate limit
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
        """Test that concurrent requests with same idempotency key work correctly.
        
        Fire 10 concurrent requests with same Idempotency-Key and body.
        Assert:
        - All responses are 200 or 202 (processing)
        - All 200 responses have same execution_id
        - At least 9 have X-Idempotency-Replayed: true (or 202 processing)
        - The side-effect counter is EXACTLY 1 (atomic first-writer-wins)
        """
        import concurrent.futures
        from app.redis_client import redis_available, get_redis
        import threading

        if not redis_available():
            pytest.skip("Redis not available")

        # Create app with an atomic counter to track side effects
        from fastapi import FastAPI
        from app.middleware.idempotency import IdempotencyMiddleware

        side_effect_counter = {"count": 0}
        counter_lock = threading.Lock()

        app = FastAPI()

        @app.post("/goals/{goal_id}/generate-tickets")
        async def generate_tickets(goal_id: str):
            # Atomic increment
            with counter_lock:
                side_effect_counter["count"] += 1
                current_count = side_effect_counter["count"]
            
            # Simulate some work to increase race window
            import asyncio
            await asyncio.sleep(0.1)
            
            return {
                "tickets": [],
                "goal_id": goal_id,
                "execution_id": current_count,
            }

        app.add_middleware(IdempotencyMiddleware)

        # Clear any existing keys
        redis = get_redis()
        
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

        # Fire 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            responses = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All should succeed (200) or be processing (202)
        success_responses = []
        processing_responses = []
        for r in responses:
            assert r.status_code in (200, 202), f"Got unexpected status {r.status_code}: {r.text}"
            if r.status_code == 200:
                success_responses.append(r)
            else:
                processing_responses.append(r)

        # All 200 responses should have same execution_id
        if success_responses:
            execution_ids = [r.json()["execution_id"] for r in success_responses]
            assert len(set(execution_ids)) == 1, f"Got different execution IDs: {execution_ids}"

        # Count replayed responses
        replayed_count = sum(
            1 for r in success_responses 
            if r.headers.get("X-Idempotency-Replayed") == "true"
        )
        
        # Most should be replayed (or processing)
        non_original_count = replayed_count + len(processing_responses)
        assert non_original_count >= 9, (
            f"Only {non_original_count} were replayed/processing "
            f"(replayed={replayed_count}, processing={len(processing_responses)})"
        )

        # CRITICAL: Side effect must happen EXACTLY ONCE
        # This is the whole point of idempotency
        assert side_effect_counter["count"] == 1, (
            f"Side effect happened {side_effect_counter['count']} times - "
            f"IDEMPOTENCY VIOLATION! Must be exactly 1."
        )

