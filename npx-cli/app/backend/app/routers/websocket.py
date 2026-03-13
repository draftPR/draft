"""WebSocket endpoints for real-time updates.

This module provides WebSocket endpoints for streaming live updates to clients:
- Job output streaming (live execution logs)
- Board updates (ticket status changes, new jobs, etc.)
- Board JSON patches (incremental state updates via RFC 6902)
"""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket.manager import manager
from app.websocket.state_tracker import get_tracker, remove_tracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/jobs/{job_id}")
async def job_output_stream(websocket: WebSocket, job_id: str):
    """Stream live output from a running job.

    Clients subscribe to this endpoint to receive real-time updates about
    job execution, including stdout/stderr output and status changes.

    Subscribes to the in-memory log broadcaster so terminal output from
    the worker is forwarded to the WebSocket in real-time.

    Args:
        websocket: The WebSocket connection
        job_id: The job ID to stream updates for

    Message format:
        {
            "type": "output" | "status" | "complete" | "error",
            "content": str,  # For output messages
            "status": str,   # For status messages
            "timestamp": str # ISO format timestamp
        }
    """
    import asyncio

    from app.services.log_stream_service import LogLevel, log_stream_service

    channel = f"job:{job_id}"
    await manager.connect(websocket, channel)

    # Background task to forward log stream messages to WebSocket
    async def _forward_logs():
        try:
            async for msg in log_stream_service.subscribe(job_id):
                try:
                    if msg.level == LogLevel.FINISHED:
                        await websocket.send_json(
                            {
                                "type": "complete",
                                "content": "",
                                "timestamp": msg.timestamp.isoformat(),
                            }
                        )
                        return
                    elif msg.level in (LogLevel.STDOUT, LogLevel.STDERR):
                        await websocket.send_json(
                            {
                                "type": "output",
                                "content": msg.content,
                                "timestamp": msg.timestamp.isoformat(),
                            }
                        )
                    elif msg.level == LogLevel.ERROR:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "content": msg.content,
                                "timestamp": msg.timestamp.isoformat(),
                            }
                        )
                    elif msg.level == LogLevel.PROGRESS:
                        await websocket.send_json(
                            {
                                "type": "status",
                                "content": msg.content,
                                "status": msg.stage or "running",
                                "progress_pct": msg.progress_pct,
                                "timestamp": msg.timestamp.isoformat(),
                            }
                        )
                    else:
                        await websocket.send_json(
                            {
                                "type": "output",
                                "content": msg.content,
                                "timestamp": msg.timestamp.isoformat(),
                            }
                        )
                except Exception:
                    return  # WebSocket closed
        except asyncio.CancelledError:
            pass

    forward_task = asyncio.create_task(_forward_logs())

    try:
        # Keep connection alive and handle client messages
        while True:
            data = await websocket.receive_text()

            # Handle ping/pong for keep-alive
            if data == "ping":
                await websocket.send_text("pong")
            elif data == "subscribe":
                # Already subscribed, acknowledge
                await websocket.send_json(
                    {"type": "subscribed", "channel": channel, "job_id": job_id}
                )
            elif data == "unsubscribe":
                # Client wants to unsubscribe
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected from job stream: {job_id}")
    except Exception as e:
        logger.error(f"WebSocket error on job stream {job_id}: {e}", exc_info=True)
    finally:
        forward_task.cancel()
        try:
            await forward_task
        except asyncio.CancelledError:
            pass
        await manager.disconnect(websocket, channel)


@router.websocket("/board/{board_id}")
async def board_updates(websocket: WebSocket, board_id: str):
    """Stream board updates (ticket status changes, new jobs, etc.).

    Supports two protocols:
    1. Legacy: broadcasts raw event messages
    2. JSON Patch: sends snapshot on connect, then RFC 6902 patches

    Client can request a resync by sending: {"type": "resync"}

    Args:
        websocket: The WebSocket connection
        board_id: The board ID to stream updates for

    Message format (legacy):
        {
            "type": "ticket_update" | "job_created" | "job_completed",
            "ticket_id": str,
            "job_id": str,
            "data": dict,
            "timestamp": str
        }

    Message format (JSON Patch):
        Connect:  {"type": "snapshot", "data": {...}, "seq": 0}
        Update:   {"type": "patch", "ops": [...], "seq": N}
        Resync:   client sends {"type": "resync"} → server sends snapshot
    """
    channel = f"board:{board_id}"
    await manager.connect(websocket, channel)

    try:
        # Keep connection alive and handle client messages
        while True:
            data = await websocket.receive_text()

            if data == "ping":
                await websocket.send_text("pong")
            elif data == "subscribe":
                await websocket.send_json(
                    {"type": "subscribed", "channel": channel, "board_id": board_id}
                )
            elif data == "unsubscribe":
                break
            else:
                # Try to parse JSON messages
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "resync":
                        # Client requested a full resync - tracker will send
                        # snapshot on next broadcast
                        tracker = get_tracker(board_id)
                        if tracker.has_state:
                            # Re-send current snapshot
                            snapshot = tracker.get_snapshot_message(
                                tracker._state  # type: ignore[arg-type]
                            )
                            await websocket.send_json(snapshot)
                except (json.JSONDecodeError, TypeError):
                    pass

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected from board: {board_id}")
    except Exception as e:
        logger.error(f"WebSocket error on board {board_id}: {e}", exc_info=True)
    finally:
        await manager.disconnect(websocket, channel)
        # Clean up tracker if no more connections
        if manager.get_connection_count(channel) == 0:
            remove_tracker(board_id)


@router.websocket("/goals/{goal_id}")
async def goal_updates(websocket: WebSocket, goal_id: str):
    """Stream goal updates (ticket generation, pipeline progress, etc.).

    Clients subscribe to this endpoint to receive real-time updates about
    goal-level changes, including ticket generation progress, pipeline
    execution status, and goal completion.

    Args:
        websocket: The WebSocket connection
        goal_id: The goal ID to stream updates for

    Message format:
        {
            "type": "ticket_generated" | "pipeline_progress" | "goal_completed",
            "goal_id": str,
            "data": dict,
            "timestamp": str
        }
    """
    channel = f"goal:{goal_id}"
    await manager.connect(websocket, channel)

    try:
        while True:
            data = await websocket.receive_text()

            if data == "ping":
                await websocket.send_text("pong")
            elif data == "subscribe":
                await websocket.send_json(
                    {"type": "subscribed", "channel": channel, "goal_id": goal_id}
                )
            elif data == "unsubscribe":
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected from goal: {goal_id}")
    except Exception as e:
        logger.error(f"WebSocket error on goal {goal_id}: {e}", exc_info=True)
    finally:
        await manager.disconnect(websocket, channel)
