"""Real-time log streaming service with ultra-low latency.

Hybrid architecture for instant feedback:
1. In-memory broadcast for same-process subscribers (<1ms latency)
2. Redis pub/sub for cross-process communication (~10-50ms latency)
3. Redis pipelining to minimize round-trips

Inspired by vibe-kanban's MsgStore but optimized for Python/FastAPI.
"""

import asyncio
import json
import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import AsyncIterator, Callable
from weakref import WeakSet

import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


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
    """Hybrid publisher: in-memory + Redis for cross-process.
    
    Used by Celery workers to push logs.
    """
    
    def __init__(self):
        self._redis: redis.Redis | None = None
        self._max_history = 500
        self._batch_size = 10  # Batch Redis writes
        self._pending: dict[str, list[str]] = defaultdict(list)
        self._last_flush: dict[str, float] = {}
        self._flush_interval = 0.05  # Flush every 50ms max
    
    def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(
                REDIS_URL,
                socket_keepalive=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        return self._redis
    
    def push(
        self,
        job_id: str,
        level: LogLevel,
        content: str,
        progress_pct: int | None = None,
        stage: str | None = None,
    ) -> None:
        """Push a log message via both in-memory and Redis.
        
        In-memory broadcast is instant (<1ms).
        Redis is batched and pipelined for efficiency.
        """
        msg = LogMessage(
            level=level,
            content=content,
            progress_pct=progress_pct,
            stage=stage,
        )
        
        # 1. Instant in-memory broadcast
        _broadcaster.push(job_id, msg)
        
        # 2. Queue for Redis (batched)
        msg_json = json.dumps(msg.to_dict())
        self._pending[job_id].append(msg_json)
        
        # Flush if batch is full or interval elapsed
        now = time.monotonic()
        last = self._last_flush.get(job_id, 0)
        if len(self._pending[job_id]) >= self._batch_size or (now - last) > self._flush_interval:
            self._flush_redis(job_id)
    
    def _flush_redis(self, job_id: str) -> None:
        """Flush pending messages to Redis using pipelining."""
        pending = self._pending.pop(job_id, [])
        if not pending:
            return
        
        try:
            r = self._get_redis()
            channel = _get_channel_name(job_id)
            history_key = _get_history_key(job_id)
            
            # Use pipeline for atomic batch operation
            pipe = r.pipeline()
            for msg_json in pending:
                pipe.publish(channel, msg_json)
                pipe.rpush(history_key, msg_json)
            pipe.ltrim(history_key, -self._max_history, -1)
            pipe.expire(history_key, 86400)
            pipe.execute()
            
            self._last_flush[job_id] = time.monotonic()
            
        except Exception as e:
            logger.warning(f"Failed to flush logs to Redis for job {job_id}: {e}")
    
    def flush_all(self, job_id: str) -> None:
        """Force flush all pending messages."""
        self._flush_redis(job_id)
    
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
    """Hybrid subscriber: prefers in-memory, falls back to Redis.
    
    Used by FastAPI SSE endpoints.
    """
    
    def __init__(self):
        self._redis: redis.Redis | None = None
    
    def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(
                REDIS_URL,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        return self._redis
    
    def get_history(self, job_id: str) -> list[LogMessage]:
        """Get message history (prefers in-memory, falls back to Redis)."""
        # Try in-memory first
        history = _broadcaster.get_history(job_id)
        if history:
            return history
        
        # Fall back to Redis
        try:
            r = self._get_redis()
            history_key = _get_history_key(job_id)
            messages = r.lrange(history_key, 0, -1)
            return [LogMessage.from_dict(json.loads(msg)) for msg in messages]
        except Exception as e:
            logger.warning(f"Failed to get history for job {job_id}: {e}")
            return []
    
    async def subscribe(self, job_id: str, max_wait_seconds: int = 1800) -> AsyncIterator[LogMessage]:
        """Subscribe to log stream with minimal latency.
        
        1. Yield history for catch-up
        2. Try in-memory broadcast first (<1ms latency)
        3. Fall back to Redis pub/sub if needed
        
        Args:
            job_id: The job to subscribe to
            max_wait_seconds: Maximum time to wait for messages (default 30 minutes).
                              Prevents infinite loops if FINISHED is never received.
        """
        # First yield history
        for msg in self.get_history(job_id):
            yield msg
            if msg.level == LogLevel.FINISHED:
                return
        
        # Try in-memory subscription first
        queue = _broadcaster.subscribe(job_id)
        redis_task = None
        start_time = time.monotonic()
        
        try:
            # Also subscribe to Redis as backup (for cross-process messages)
            redis_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
            redis_task = asyncio.create_task(
                self._redis_subscriber(job_id, redis_queue)
            )
            
            # Multiplex both sources with timeout protection
            while (time.monotonic() - start_time) < max_wait_seconds:
                # Check in-memory queue first (faster)
                try:
                    msg = queue.get_nowait()
                    yield msg
                    if msg.level == LogLevel.FINISHED:
                        return
                    continue
                except asyncio.QueueEmpty:
                    pass
                
                # Check Redis queue
                try:
                    msg = redis_queue.get_nowait()
                    yield msg
                    if msg.level == LogLevel.FINISHED:
                        return
                    continue
                except asyncio.QueueEmpty:
                    pass
                
                # Neither has data, wait a bit
                await asyncio.sleep(0.01)  # 10ms poll interval
            
            # Timeout reached - yield a timeout message and exit
            logger.warning(f"Log stream subscription for job {job_id} timed out after {max_wait_seconds}s")
            yield LogMessage(
                level=LogLevel.INFO,
                content=f"[Stream timeout after {max_wait_seconds}s - connection closed]",
            )
                
        finally:
            _broadcaster.unsubscribe(job_id, queue)
            if redis_task:
                redis_task.cancel()
                try:
                    await redis_task
                except asyncio.CancelledError:
                    pass
    
    async def _redis_subscriber(self, job_id: str, queue: asyncio.Queue) -> None:
        """Background task to subscribe to Redis pub/sub."""
        r = self._get_redis()
        pubsub = r.pubsub()
        channel = _get_channel_name(job_id)
        
        try:
            pubsub.subscribe(channel)
            
            while True:
                message = await asyncio.to_thread(
                    pubsub.get_message,
                    ignore_subscribe_messages=True,
                    timeout=0.5,
                )
                
                if message and message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        msg = LogMessage.from_dict(data)
                        await queue.put(msg)
                    except (json.JSONDecodeError, KeyError):
                        pass
                
                await asyncio.sleep(0.01)
                
        except asyncio.CancelledError:
            pass
        finally:
            pubsub.unsubscribe(channel)
            pubsub.close()


# Global instances
log_stream_publisher = LogStreamPublisher()
log_stream_service = LogStreamSubscriber()
