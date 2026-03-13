"""In-memory orchestrator log buffer with file persistence.

Provides a simple circular buffer for orchestrator-level events
(planner decisions, state transitions, etc.) that can be read
by the debug router for display in the UI.

Also persists entries to a JSONL file at .draft/logs/orchestrator.jsonl
so logs survive restarts.
"""

import json
import logging
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_LOG_ENTRIES = 500
_orchestrator_logs: deque[dict] = deque(maxlen=MAX_LOG_ENTRIES)

# Persistence file path
_LOG_FILE: Path | None = None


def _get_log_file() -> Path | None:
    """Get the orchestrator log file path, creating dirs if needed."""
    global _LOG_FILE
    if _LOG_FILE is not None:
        return _LOG_FILE

    try:
        from app.data_dir import get_logs_dir

        log_dir = get_logs_dir()
        _LOG_FILE = log_dir / "orchestrator.jsonl"
        return _LOG_FILE
    except Exception as e:
        logger.debug(f"Could not determine orchestrator log file path: {e}")
        return None


def _load_persisted_logs() -> None:
    """Load persisted logs from JSONL file into the in-memory buffer on startup."""
    log_file = _get_log_file()
    if log_file is None or not log_file.exists():
        return

    try:
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        _orchestrator_logs.append(entry)
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logger.debug(f"Could not load persisted orchestrator logs: {e}")


# Load persisted logs on module import
_load_persisted_logs()


def add_orchestrator_log(level: str, message: str, data: dict | None = None) -> None:
    """Add a log entry to the orchestrator log buffer and persist to file."""
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": level,
        "message": message,
        "data": data or {},
    }
    _orchestrator_logs.append(entry)

    # Persist to JSONL file (append-only, best-effort)
    try:
        log_file = _get_log_file()
        if log_file is not None:
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.debug(f"Could not persist orchestrator log entry: {e}")
