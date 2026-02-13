"""Circuit breaker pattern for resilient external API calls.

Prevents cascading failures by temporarily stopping requests to a failing service,
giving it time to recover.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests immediately
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""

    pass


class CircuitBreaker:
    """Circuit breaker for external API calls with automatic recovery.

    States:
        - CLOSED: Normal operation, requests pass through
        - OPEN: Too many failures, reject all requests immediately
        - HALF_OPEN: Testing recovery, allow limited requests

    Transitions:
        - CLOSED -> OPEN: After failure_threshold consecutive failures
        - OPEN -> HALF_OPEN: After timeout_seconds elapsed
        - HALF_OPEN -> CLOSED: After success_threshold consecutive successes
        - HALF_OPEN -> OPEN: On any failure

    Thread-safe.
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: int = 60,
    ):
        """Initialize circuit breaker.

        Args:
            name: Name for logging
            failure_threshold: Number of failures before opening circuit
            success_threshold: Number of successes needed to close circuit (from half-open)
            timeout_seconds: Seconds to wait before trying half-open
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: datetime | None = None
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state (thread-safe)."""
        with self._lock:
            return self._state

    @property
    def failure_count(self) -> int:
        """Get current failure count (thread-safe)."""
        with self._lock:
            return self._failure_count

    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute a function with circuit breaker protection.

        Args:
            func: Function to call
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Return value from func

        Raises:
            CircuitBreakerError: If circuit is open
            Exception: If func raises an exception
        """
        with self._lock:
            current_state = self._state

            # Check if we should transition from OPEN to HALF_OPEN
            if current_state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    logger.info(
                        f"Circuit breaker '{self.name}' transitioning OPEN -> HALF_OPEN "
                        f"(timeout elapsed: {self.timeout_seconds}s)"
                    )
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    current_state = CircuitState.HALF_OPEN
                else:
                    # Still open, reject immediately
                    time_since_failure = (
                        datetime.now() - self._last_failure_time
                    ).total_seconds()
                    raise CircuitBreakerError(
                        f"Circuit breaker '{self.name}' is OPEN "
                        f"({self._failure_count} failures, retry in "
                        f"{self.timeout_seconds - time_since_failure:.0f}s)"
                    )

        # Execute the function (outside lock to avoid blocking other threads)
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(e)
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset (must hold lock)."""
        if self._last_failure_time is None:
            return True
        elapsed = datetime.now() - self._last_failure_time
        return elapsed >= timedelta(seconds=self.timeout_seconds)

    def _on_success(self):
        """Handle successful call (transitions HALF_OPEN -> CLOSED)."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                logger.info(
                    f"Circuit breaker '{self.name}' success in HALF_OPEN "
                    f"({self._success_count}/{self.success_threshold})"
                )

                if self._success_count >= self.success_threshold:
                    logger.info(
                        f"Circuit breaker '{self.name}' transitioning HALF_OPEN -> CLOSED "
                        f"(service recovered)"
                    )
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self._last_failure_time = None

            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                if self._failure_count > 0:
                    logger.debug(
                        f"Circuit breaker '{self.name}' success, "
                        f"resetting failure count from {self._failure_count}"
                    )
                    self._failure_count = 0

    def _on_failure(self, exception: Exception):
        """Handle failed call (transitions CLOSED -> OPEN, HALF_OPEN -> OPEN)."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open immediately opens circuit
                logger.warning(
                    f"Circuit breaker '{self.name}' failed in HALF_OPEN -> OPEN "
                    f"(service still failing: {exception})"
                )
                self._state = CircuitState.OPEN
                self._success_count = 0

            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    logger.error(
                        f"Circuit breaker '{self.name}' CLOSED -> OPEN "
                        f"(threshold reached: {self._failure_count} failures)"
                    )
                    self._state = CircuitState.OPEN
                else:
                    logger.warning(
                        f"Circuit breaker '{self.name}' failure "
                        f"{self._failure_count}/{self.failure_threshold}: {exception}"
                    )

    def reset(self):
        """Manually reset circuit breaker to CLOSED state."""
        with self._lock:
            logger.info(f"Circuit breaker '{self.name}' manually reset to CLOSED")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None

    def get_status(self) -> dict:
        """Get circuit breaker status (for monitoring/debugging)."""
        with self._lock:
            status = {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "failure_threshold": self.failure_threshold,
                "success_threshold": self.success_threshold,
                "timeout_seconds": self.timeout_seconds,
            }

            if self._last_failure_time:
                status["last_failure_time"] = self._last_failure_time.isoformat()
                time_since_failure = (
                    datetime.now() - self._last_failure_time
                ).total_seconds()
                status["seconds_since_failure"] = int(time_since_failure)

            return status
