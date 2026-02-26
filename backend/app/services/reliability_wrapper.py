"""Reliability wrapper for autonomous execution with retry, checkpointing, and recovery."""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ExecutorError, ExecutorTimeoutError


class CheckpointType(StrEnum):
    """Types of execution checkpoints."""
    START = "start"
    PROGRESS = "progress"
    VALIDATION = "validation"
    COMPLETION = "completion"
    FAILURE = "failure"


@dataclass
class ExecutionCheckpoint:
    """Represents a point in execution that can be resumed from."""
    checkpoint_id: str
    ticket_id: str
    job_id: str | None
    checkpoint_type: CheckpointType
    timestamp: datetime
    retry_count: int
    state_snapshot: dict[str, Any]
    error_message: str | None = None


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    initial_delay_seconds: float = 2.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True

    def get_delay(self, retry_attempt: int) -> float:
        """Calculate delay for given retry attempt with exponential backoff."""
        delay = min(
            self.initial_delay_seconds * (self.exponential_base ** retry_attempt),
            self.max_delay_seconds
        )

        if self.jitter:
            # Add random jitter of ±20% to prevent thundering herd
            import random
            jitter_amount = delay * 0.2
            delay = delay + random.uniform(-jitter_amount, jitter_amount)

        return max(0, delay)


class ReliabilityWrapper:
    """
    Wraps execution with reliability features:
    - Automatic retry with exponential backoff
    - Checkpointing for resume capability
    - Progress tracking
    - Error recovery
    """

    def __init__(
        self,
        db: AsyncSession,
        retry_config: RetryConfig | None = None,
        checkpoint_interval_seconds: int = 300,  # 5 minutes
    ):
        self.db = db
        self.retry_config = retry_config or RetryConfig()
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self._checkpoints: dict[str, ExecutionCheckpoint] = {}
        self._last_checkpoint_time: dict[str, float] = {}

    async def execute_with_reliability(
        self,
        func: Callable,
        *args,
        ticket_id: str,
        job_id: str | None = None,
        validation_func: Callable[[Any], bool] | None = None,
        checkpoint_key: str | None = None,
        **kwargs
    ) -> Any:
        """
        Execute a function with automatic retry, checkpointing, and recovery.

        Args:
            func: The function to execute
            *args: Positional arguments for func
            ticket_id: ID of the ticket being executed
            job_id: Optional job ID for tracking
            validation_func: Optional function to validate result before accepting
            checkpoint_key: Optional key for checkpoint storage
            **kwargs: Keyword arguments for func

        Returns:
            The result of the function execution

        Raises:
            The last exception if all retries are exhausted
        """
        checkpoint_key = checkpoint_key or f"{ticket_id}:{job_id or 'default'}"

        # Create initial checkpoint
        await self._create_checkpoint(
            checkpoint_key=checkpoint_key,
            ticket_id=ticket_id,
            job_id=job_id,
            checkpoint_type=CheckpointType.START,
            retry_count=0,
            state_snapshot={"args": str(args), "kwargs": str(kwargs)}
        )

        last_exception = None

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # Execute the function
                result = await self._execute_with_monitoring(
                    func=func,
                    checkpoint_key=checkpoint_key,
                    ticket_id=ticket_id,
                    job_id=job_id,
                    retry_count=attempt,
                    *args,
                    **kwargs
                )

                # Validate result if validation function provided
                if validation_func and not await self._validate_result(result, validation_func):
                    raise ValueError("Result validation failed")

                # Success - create completion checkpoint
                await self._create_checkpoint(
                    checkpoint_key=checkpoint_key,
                    ticket_id=ticket_id,
                    job_id=job_id,
                    checkpoint_type=CheckpointType.COMPLETION,
                    retry_count=attempt,
                    state_snapshot={"success": True}
                )

                return result

            except asyncio.CancelledError:
                # Don't retry on cancellation
                await self._create_checkpoint(
                    checkpoint_key=checkpoint_key,
                    ticket_id=ticket_id,
                    job_id=job_id,
                    checkpoint_type=CheckpointType.FAILURE,
                    retry_count=attempt,
                    state_snapshot={"cancelled": True},
                    error_message="Execution cancelled"
                )
                raise

            except Exception as e:
                last_exception = e

                # Check if error is retryable
                if not self._is_retryable_error(e):
                    await self._create_checkpoint(
                        checkpoint_key=checkpoint_key,
                        ticket_id=ticket_id,
                        job_id=job_id,
                        checkpoint_type=CheckpointType.FAILURE,
                        retry_count=attempt,
                        state_snapshot={"non_retryable": True},
                        error_message=str(e)
                    )
                    raise

                # Last attempt failed
                if attempt >= self.retry_config.max_retries:
                    await self._create_checkpoint(
                        checkpoint_key=checkpoint_key,
                        ticket_id=ticket_id,
                        job_id=job_id,
                        checkpoint_type=CheckpointType.FAILURE,
                        retry_count=attempt,
                        state_snapshot={"exhausted_retries": True},
                        error_message=str(e)
                    )
                    raise

                # Calculate delay and retry
                delay = self.retry_config.get_delay(attempt)

                await self._create_checkpoint(
                    checkpoint_key=checkpoint_key,
                    ticket_id=ticket_id,
                    job_id=job_id,
                    checkpoint_type=CheckpointType.PROGRESS,
                    retry_count=attempt,
                    state_snapshot={
                        "retry_in_seconds": delay,
                        "error": str(e),
                        "attempt": attempt + 1
                    },
                    error_message=str(e)
                )

                await asyncio.sleep(delay)

        # Should not reach here, but handle it
        if last_exception:
            raise last_exception

    async def _execute_with_monitoring(
        self,
        func: Callable,
        checkpoint_key: str,
        ticket_id: str,
        job_id: str | None,
        retry_count: int,
        *args,
        **kwargs
    ) -> Any:
        """Execute function with progress monitoring and periodic checkpointing."""
        start_time = time.time()
        self._last_checkpoint_time[checkpoint_key] = start_time

        # Check if this is an async function
        if asyncio.iscoroutinefunction(func):
            # Create a task so we can monitor it
            task = asyncio.create_task(func(*args, **kwargs))

            # Monitor execution and create periodic checkpoints
            while not task.done():
                await asyncio.sleep(1)  # Check every second

                elapsed = time.time() - self._last_checkpoint_time[checkpoint_key]
                if elapsed >= self.checkpoint_interval_seconds:
                    await self._create_checkpoint(
                        checkpoint_key=checkpoint_key,
                        ticket_id=ticket_id,
                        job_id=job_id,
                        checkpoint_type=CheckpointType.PROGRESS,
                        retry_count=retry_count,
                        state_snapshot={
                            "elapsed_seconds": time.time() - start_time,
                            "still_running": True
                        }
                    )
                    self._last_checkpoint_time[checkpoint_key] = time.time()

            return await task
        else:
            # Sync function - execute directly
            return func(*args, **kwargs)

    async def _validate_result(self, result: Any, validation_func: Callable) -> bool:
        """Validate execution result."""
        try:
            if asyncio.iscoroutinefunction(validation_func):
                return await validation_func(result)
            else:
                return validation_func(result)
        except Exception:
            return False

    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is retryable."""
        # Network/connection errors - retryable
        if isinstance(error, (ConnectionError, TimeoutError, asyncio.TimeoutError)):
            return True

        # Executor timeout - retryable
        if isinstance(error, ExecutorTimeoutError):
            return True

        # Some executor errors are retryable (transient failures)
        if isinstance(error, ExecutorError):
            error_msg = str(error).lower()
            # Retry on rate limits, temporary unavailability, etc.
            retryable_patterns = [
                "rate limit",
                "timeout",
                "temporary",
                "unavailable",
                "too many requests",
                "service unavailable",
                "connection",
            ]
            return any(pattern in error_msg for pattern in retryable_patterns)

        # Validation errors, logic errors - not retryable
        if isinstance(error, (ValueError, TypeError, KeyError, AttributeError)):
            return False

        # Default: don't retry unknown errors
        return False

    async def _create_checkpoint(
        self,
        checkpoint_key: str,
        ticket_id: str,
        job_id: str | None,
        checkpoint_type: CheckpointType,
        retry_count: int,
        state_snapshot: dict[str, Any],
        error_message: str | None = None,
    ):
        """Create an execution checkpoint."""
        checkpoint = ExecutionCheckpoint(
            checkpoint_id=f"{checkpoint_key}:{checkpoint_type.value}:{int(time.time())}",
            ticket_id=ticket_id,
            job_id=job_id,
            checkpoint_type=checkpoint_type,
            timestamp=datetime.utcnow(),
            retry_count=retry_count,
            state_snapshot=state_snapshot,
            error_message=error_message,
        )

        self._checkpoints[checkpoint_key] = checkpoint

        # TODO: Persist checkpoint to database for true resumability
        # For now, keeping in memory is sufficient for single-session reliability

    async def get_last_checkpoint(self, checkpoint_key: str) -> ExecutionCheckpoint | None:
        """Get the last checkpoint for a given key."""
        return self._checkpoints.get(checkpoint_key)

    async def list_checkpoints(self, ticket_id: str) -> list[ExecutionCheckpoint]:
        """List all checkpoints for a ticket."""
        return [
            cp for cp in self._checkpoints.values()
            if cp.ticket_id == ticket_id
        ]

    async def cleanup_checkpoints(self, ticket_id: str):
        """Clean up checkpoints for a completed ticket."""
        keys_to_remove = [
            key for key, cp in self._checkpoints.items()
            if cp.ticket_id == ticket_id
        ]
        for key in keys_to_remove:
            del self._checkpoints[key]
            if key in self._last_checkpoint_time:
                del self._last_checkpoint_time[key]


async def with_retry(
    func: Callable,
    *args,
    max_retries: int = 3,
    initial_delay: float = 2.0,
    **kwargs
) -> Any:
    """
    Simple retry decorator for functions that don't need full reliability wrapper.

    Usage:
        result = await with_retry(some_async_func, arg1, arg2, max_retries=5)
    """
    retry_config = RetryConfig(max_retries=max_retries, initial_delay_seconds=initial_delay)
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            if attempt >= max_retries:
                raise

            delay = retry_config.get_delay(attempt)
            await asyncio.sleep(delay)

    if last_exception:
        raise last_exception
