"""WebSocket connection manager for real-time updates.

This module manages WebSocket connections and provides channel-based
broadcasting for real-time updates to clients.
"""

import asyncio
import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections for real-time updates.

    Supports channel-based broadcasting where clients can subscribe to
    specific channels (e.g., job:{job_id}, board:{board_id}) to receive
    targeted updates.
    """

    def __init__(self):
        # Map of channel -> set of websockets
        self.connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channel: str):
        """Accept and register a new WebSocket connection to a channel.

        Args:
            websocket: The WebSocket connection to register
            channel: The channel to subscribe to (e.g., "job:123", "board:abc")
        """
        await websocket.accept()
        async with self._lock:
            if channel not in self.connections:
                self.connections[channel] = set()
            self.connections[channel].add(websocket)
            logger.info(f"WebSocket connected to channel: {channel}")

    async def disconnect(self, websocket: WebSocket, channel: str):
        """Unregister a WebSocket connection from a channel.

        Args:
            websocket: The WebSocket connection to remove
            channel: The channel to unsubscribe from
        """
        async with self._lock:
            if channel in self.connections:
                self.connections[channel].discard(websocket)
                if not self.connections[channel]:
                    # Remove empty channel
                    del self.connections[channel]
                logger.info(f"WebSocket disconnected from channel: {channel}")

    async def broadcast(self, channel: str, message: dict):
        """Send message to all connections on a channel.

        Args:
            channel: The channel to broadcast to
            message: The message dict to send (will be JSON serialized)

        Automatically cleans up dead connections that fail to receive messages.
        """
        if channel not in self.connections:
            return

        dead_connections = set()
        for connection in list(self.connections[channel]):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(
                    f"Failed to send message to WebSocket on channel {channel}: {e}"
                )
                dead_connections.add(connection)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                if channel in self.connections:
                    self.connections[channel] -= dead_connections
                    if not self.connections[channel]:
                        del self.connections[channel]
                    logger.info(
                        f"Cleaned up {len(dead_connections)} dead connections from {channel}"
                    )

    async def broadcast_to_all(self, message: dict):
        """Broadcast message to all connections across all channels.

        Args:
            message: The message dict to send to all connected clients
        """
        for channel in list(self.connections.keys()):
            await self.broadcast(channel, message)

    def get_connection_count(self, channel: str = None) -> int:
        """Get count of active connections.

        Args:
            channel: Optional channel to count connections for.
                    If None, returns total across all channels.

        Returns:
            Number of active connections
        """
        if channel:
            return len(self.connections.get(channel, set()))
        return sum(len(conns) for conns in self.connections.values())

    def get_channels(self) -> list[str]:
        """Get list of all active channels.

        Returns:
            List of channel names with active connections
        """
        return list(self.connections.keys())

    async def broadcast_board_state(self, board_id: str, board_state: dict):
        """Broadcast board state as JSON patch to connected clients.

        On first call for a board, sends a full snapshot. On subsequent calls,
        computes and sends an RFC 6902 JSON patch. Sends nothing if no change.

        Args:
            board_id: The board ID
            board_state: Full board state dict
        """
        channel = f"board:{board_id}"
        if channel not in self.connections:
            return

        from app.websocket.state_tracker import get_tracker

        tracker = get_tracker(board_id)

        if not tracker.has_state:
            message = tracker.get_snapshot_message(board_state)
        else:
            message = tracker.compute_patch(board_state)
            if message is None:
                return  # No changes

        await self.broadcast(channel, message)


# Global connection manager instance
manager = ConnectionManager()


# Helper functions for sync code (like Celery workers)
def broadcast_sync(channel: str, message: dict):
    """Broadcast message from synchronous code.

    This is a helper for sync contexts (like Celery workers) that need to
    broadcast WebSocket messages. It schedules the broadcast on the event loop.

    Args:
        channel: The channel to broadcast to
        message: The message dict to send

    Note: This uses asyncio.create_task() which requires an active event loop.
    If called from a thread without a loop, the broadcast will be skipped.
    """
    try:
        import asyncio

        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(manager.broadcast(channel, message))
        else:
            # If no loop is running, we can't broadcast
            logger.debug(
                f"Skipping WebSocket broadcast to {channel} - no event loop running"
            )
    except Exception as e:
        logger.debug(f"Failed to broadcast WebSocket message to {channel}: {e}")
