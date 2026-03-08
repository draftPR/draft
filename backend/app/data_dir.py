"""Central data directory for Draft runtime artifacts.

All worktrees, logs, and evidence files live under a single central
directory (~/.telem/ by default) instead of polluting target repos.

Override with the TELEM_DATA_DIR environment variable.
"""

import os
from pathlib import Path

_DEFAULT_DATA_DIR = Path.home() / ".telem"


def get_data_dir() -> Path:
    """Return the central data directory, creating it if needed.

    Resolution order:
        1. TELEM_DATA_DIR environment variable
        2. ~/.telem/
    """
    data_dir = Path(os.environ.get("TELEM_DATA_DIR", str(_DEFAULT_DATA_DIR)))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_worktree_dir(board_id: str, ticket_id: str) -> Path:
    """Return the worktree directory for a ticket.

    Layout: {data_dir}/worktrees/{board_id}/{ticket_id}/
    """
    return get_data_dir() / "worktrees" / board_id / ticket_id


def get_worktrees_root() -> Path:
    """Return the root worktrees directory.

    Layout: {data_dir}/worktrees/
    """
    return get_data_dir() / "worktrees"


def get_log_path(job_id: str) -> Path:
    """Return the log file path for a job.

    Layout: {data_dir}/logs/{job_id}.log
    """
    logs_dir = get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / f"{job_id}.log"


def get_logs_dir() -> Path:
    """Return the central logs directory.

    Layout: {data_dir}/logs/
    """
    d = get_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_evidence_dir(job_id: str) -> Path:
    """Return the evidence directory for a job.

    Layout: {data_dir}/evidence/{job_id}/
    """
    d = get_data_dir() / "evidence" / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_jobs_dir(job_id: str) -> Path:
    """Return the job working directory.

    Layout: {data_dir}/jobs/{job_id}/
    """
    d = get_data_dir() / "jobs" / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# Legacy path constant for migration-period checks
LEGACY_SMARTKANBAN_DIR = ".smartkanban"
LEGACY_WORKTREES_DIR = ".smartkanban/worktrees"
