"""Tmux session manager for multi-agent execution.

Each agent in a team runs in its own detached tmux session with pipe-pane
logging. This module provides low-level tmux operations: create, send,
capture, kill, and list sessions.

Inspired by coral's tmux_manager.py but adapted for Draft's per-ticket
lifecycle (sessions created at execution start, killed at completion).
"""

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Prefix for all Draft agent tmux sessions
SESSION_PREFIX = "draft-agent-"


@dataclass
class TmuxSessionInfo:
    """Information about a running tmux session."""

    session_name: str
    pane_target: str  # e.g., "draft-agent-abc123:0.0"
    working_dir: str
    pid: int | None = None
    is_alive: bool = True


def is_tmux_available() -> bool:
    """Check if tmux is installed and available."""
    return shutil.which("tmux") is not None


def _run_tmux(
    *args: str, check: bool = True, capture: bool = True
) -> subprocess.CompletedProcess:
    """Run a tmux command."""
    cmd = ["tmux", *args]
    try:
        return subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            check=check,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        logger.warning("tmux command timed out: %s", " ".join(cmd))
        raise
    except subprocess.CalledProcessError as e:
        logger.debug(
            "tmux command failed: %s\nstdout: %s\nstderr: %s",
            " ".join(cmd),
            e.stdout,
            e.stderr,
        )
        if check:
            raise
        return e  # type: ignore[return-value]


def create_session(
    session_name: str,
    working_dir: str | Path,
    window_name: str = "agent",
) -> str:
    """Create a detached tmux session.

    Returns the session name.
    """
    working_dir = str(working_dir)
    _run_tmux(
        "new-session",
        "-d",
        "-s",
        session_name,
        "-n",
        window_name,
        "-c",
        working_dir,
    )
    # Unset CLAUDECODE env var to prevent nested Claude Code detection
    _run_tmux(
        "set-environment",
        "-t",
        session_name,
        "-u",
        "CLAUDECODE",
    )
    logger.info("Created tmux session: %s in %s", session_name, working_dir)
    return session_name


def setup_logging(session_name: str, log_path: str | Path) -> Path:
    """Set up pipe-pane logging for a tmux session.

    All output from the pane is continuously written to the log file.
    """
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _run_tmux(
        "pipe-pane",
        "-o",
        "-t",
        f"{session_name}:0.0",
        f"cat >> '{log_path}'",
    )
    logger.debug("Logging enabled: %s -> %s", session_name, log_path)
    return log_path


def send_command(session_name: str, command: str) -> None:
    """Send a command string to a tmux session (press Enter after)."""
    _run_tmux(
        "send-keys",
        "-t",
        f"{session_name}:0.0",
        command,
        "Enter",
    )


def send_text(session_name: str, text: str) -> None:
    """Send text to a tmux session using bracket paste (safe for multi-line).

    Uses tmux's bracket-paste escape to avoid interpretation of special chars.
    """
    # Escape any single quotes in the text
    escaped = text.replace("'", "'\\''")
    _run_tmux(
        "send-keys",
        "-t",
        f"{session_name}:0.0",
        "-l",  # literal mode
        escaped,
    )
    _run_tmux(
        "send-keys",
        "-t",
        f"{session_name}:0.0",
        "Enter",
    )


def set_environment(session_name: str, key: str, value: str) -> None:
    """Set an environment variable in a tmux session."""
    _run_tmux(
        "set-environment",
        "-t",
        session_name,
        key,
        value,
    )


def capture_output(session_name: str, lines: int = 100) -> str:
    """Capture recent output from a tmux pane."""
    result = _run_tmux(
        "capture-pane",
        "-t",
        f"{session_name}:0.0",
        "-p",  # print to stdout
        "-S",
        str(-lines),  # start from N lines back
        check=False,
    )
    return result.stdout if result.stdout else ""


def kill_session(session_name: str) -> bool:
    """Kill a tmux session. Returns True if killed successfully."""
    try:
        _run_tmux("kill-session", "-t", session_name)
        logger.info("Killed tmux session: %s", session_name)
        return True
    except subprocess.CalledProcessError:
        logger.debug("Session already dead or not found: %s", session_name)
        return False


def is_session_alive(session_name: str) -> bool:
    """Check if a tmux session is still running."""
    try:
        result = _run_tmux(
            "has-session",
            "-t",
            session_name,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def list_draft_sessions() -> list[TmuxSessionInfo]:
    """List all Draft agent tmux sessions."""
    try:
        result = _run_tmux(
            "list-panes",
            "-a",
            "-F",
            "#{session_name}\t#{pane_current_path}\t#{pane_pid}",
            check=False,
        )
    except Exception:
        return []

    if not result.stdout:
        return []

    sessions = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].startswith(SESSION_PREFIX):
            sessions.append(
                TmuxSessionInfo(
                    session_name=parts[0],
                    pane_target=f"{parts[0]}:0.0",
                    working_dir=parts[1] if len(parts) > 1 else "",
                    pid=int(parts[2])
                    if len(parts) > 2 and parts[2].isdigit()
                    else None,
                )
            )
    return sessions


def generate_session_name(ticket_id: str, role: str, short_uuid: str) -> str:
    """Generate a tmux session name for an agent.

    Format: draft-agent-{ticket_short}-{role}-{uuid_short}
    """
    ticket_short = ticket_id[:8]
    role_clean = re.sub(r"[^a-zA-Z0-9]", "", role)[:12]
    return f"{SESSION_PREFIX}{ticket_short}-{role_clean}-{short_uuid[:6]}"
