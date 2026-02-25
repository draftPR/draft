"""Real-time log streaming service with ultra-low latency.

Uses in-memory broadcast for same-process subscribers (<1ms latency).
Worker runs in-process, so cross-process communication is not needed.
"""

import asyncio
import logging
import threading
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from weakref import WeakSet

logger = logging.getLogger(__name__)


class LogLevel(str, Enum):
    """Log message levels."""
    STDOUT = "stdout"
    STDERR = "stderr"
    INFO = "info"
    ERROR = "error"
    PROGRESS = "progress"  # Progress updates
    NORMALIZED = "normalized"  # Normalized agent log entry (parsed JSON)
    FINISHED = "finished"


@dataclass
class LogMessage:
    """A single log message with optional metadata."""
    level: LogLevel
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Optional progress metadata
    progress_pct: int | None = None  # 0-100
    stage: str | None = None  # e.g., "parsing", "generating", "applying"

    def to_dict(self) -> dict:
        """Serialize for Redis/JSON."""
        d = {
            "level": self.level.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.progress_pct is not None:
            d["progress_pct"] = self.progress_pct
        if self.stage:
            d["stage"] = self.stage
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "LogMessage":
        """Deserialize from Redis/JSON."""
        return cls(
            level=LogLevel(data["level"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            progress_pct=data.get("progress_pct"),
            stage=data.get("stage"),
        )


def _get_channel_name(job_id: str) -> str:
    return f"job_logs:{job_id}"


def _get_history_key(job_id: str) -> str:
    return f"job_logs_history:{job_id}"


class InMemoryBroadcaster:
    """In-memory pub/sub for same-process subscribers.

    Provides <1ms latency for local subscribers.
    Thread-safe for worker threads.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # job_id -> set of async queues
        self._subscribers: dict[str, WeakSet[asyncio.Queue]] = defaultdict(WeakSet)
        # job_id -> list of messages (for history/catch-up)
        self._history: dict[str, list[LogMessage]] = defaultdict(list)
        self._max_history = 500

    def push(self, job_id: str, msg: LogMessage) -> None:
        """Push message to all local subscribers (thread-safe)."""
        with self._lock:
            # Store in history
            history = self._history[job_id]
            history.append(msg)
            if len(history) > self._max_history:
                self._history[job_id] = history[-self._max_history:]

            # Broadcast to subscribers
            subscribers = self._subscribers.get(job_id, set())
            for queue in list(subscribers):
                try:
                    queue.put_nowait(msg)
                except asyncio.QueueFull:
                    pass  # Drop if subscriber is slow

    def subscribe(self, job_id: str) -> asyncio.Queue:
        """Create a subscription queue for a job."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subscribers[job_id].add(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        """Remove a subscription."""
        with self._lock:
            if job_id in self._subscribers:
                self._subscribers[job_id].discard(queue)

    def get_history(self, job_id: str) -> list[LogMessage]:
        """Get message history for catch-up."""
        with self._lock:
            return list(self._history.get(job_id, []))

    def cleanup(self, job_id: str) -> None:
        """Clean up after job finishes."""
        with self._lock:
            self._subscribers.pop(job_id, None)
            # Keep history for a bit for late subscribers
            # (cleanup happens via TTL in Redis anyway)


# Global in-memory broadcaster
_broadcaster = InMemoryBroadcaster()


class LogStreamPublisher:
    """In-memory log publisher for same-process workers.

    Used by workers to push logs to subscribers via InMemoryBroadcaster.
    """

    def push(
        self,
        job_id: str,
        level: LogLevel,
        content: str,
        progress_pct: int | None = None,
        stage: str | None = None,
    ) -> None:
        """Push a log message via in-memory broadcast (<1ms)."""
        msg = LogMessage(
            level=level,
            content=content,
            progress_pct=progress_pct,
            stage=stage,
        )
        _broadcaster.push(job_id, msg)

    def flush_all(self, job_id: str) -> None:
        """No-op — in-memory broadcast is instant."""
        pass

    def push_stdout(self, job_id: str, content: str) -> None:
        self.push(job_id, LogLevel.STDOUT, content)

    def push_stderr(self, job_id: str, content: str) -> None:
        self.push(job_id, LogLevel.STDERR, content)

    def push_info(self, job_id: str, content: str) -> None:
        self.push(job_id, LogLevel.INFO, content)

    def push_error(self, job_id: str, content: str) -> None:
        self.push(job_id, LogLevel.ERROR, content)

    def push_progress(self, job_id: str, pct: int, stage: str, content: str = "") -> None:
        """Push a progress update."""
        self.push(job_id, LogLevel.PROGRESS, content, progress_pct=pct, stage=stage)

    def push_finished(self, job_id: str) -> None:
        """Signal job completion."""
        self.push(job_id, LogLevel.FINISHED, "")
        self.flush_all(job_id)  # Ensure all messages are flushed
        _broadcaster.cleanup(job_id)


class LogStreamSubscriber:
    """In-memory subscriber for log streams.

    Used by FastAPI SSE endpoints. Worker runs in-process so
    in-memory broadcast provides instant delivery.
    """

    def get_history(self, job_id: str) -> list[LogMessage]:
        """Get message history from in-memory broadcaster."""
        return _broadcaster.get_history(job_id)

    async def subscribe(self, job_id: str, max_wait_seconds: int = 1800) -> AsyncIterator[LogMessage]:
        """Subscribe to log stream with minimal latency.

        1. Yield history for catch-up
        2. Use in-memory broadcast (<1ms latency)
        """
        # First yield history
        for msg in self.get_history(job_id):
            yield msg
            if msg.level == LogLevel.FINISHED:
                return

        queue = _broadcaster.subscribe(job_id)
        start_time = time.monotonic()

        try:
            while (time.monotonic() - start_time) < max_wait_seconds:
                try:
                    msg = queue.get_nowait()
                    yield msg
                    if msg.level == LogLevel.FINISHED:
                        return
                    continue
                except asyncio.QueueEmpty:
                    pass

                await asyncio.sleep(0.01)  # 10ms poll interval

            logger.warning(f"Log stream subscription for job {job_id} timed out after {max_wait_seconds}s")
            yield LogMessage(
                level=LogLevel.INFO,
                content=f"[Stream timeout after {max_wait_seconds}s - connection closed]",
            )

        finally:
            _broadcaster.unsubscribe(job_id, queue)


# Global instances
log_stream_publisher = LogStreamPublisher()
log_stream_service = LogStreamSubscriber()
