"""Celery worker tasks for Smart Kanban."""

from __future__ import annotations

import json
import logging
import select
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from celery.exceptions import Ignore
from sqlalchemy.orm import selectinload

if TYPE_CHECKING:
    from app.services.config_service import PlannerConfig

logger = logging.getLogger(__name__)

from app.celery_app import celery_app
from app.database_sync import get_sync_db
from app.exceptions import (
    ExecutorInvocationError,
    ExecutorNotFoundError,
    NotAGitRepositoryError,
    WorkspaceError,
)
from app.models.evidence import Evidence, EvidenceKind
from app.models.job import Job, JobStatus
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.services.config_service import ConfigService, YoloStatus
from app.services.executor_service import ExecutorService, ExecutorMode, ExecutorType, PromptBundleBuilder
from app.services.log_stream_service import LogLevel, log_stream_publisher
from app.services.cursor_log_normalizer import CursorLogNormalizer, NormalizedEntry
from app.services.workspace_service import WorkspaceService
from app.services.worktree_validator import WorktreeValidator
from app.state_machine import ActorType, EventType, TicketState

# Fallback logs directory (used when worktree is not available)
FALLBACK_LOGS_DIR = Path(__file__).parent.parent / "logs"

# Thread-local storage for job context (THREAD-SAFE)
_job_context = threading.local()

# Track active subprocesses for cancellation (THREAD-SAFE with lock)
_active_processes: dict[str, subprocess.Popen] = {}
_active_processes_lock = threading.Lock()


def ensure_fallback_logs_dir() -> None:
    """Ensure the fallback logs directory exists."""
    FALLBACK_LOGS_DIR.mkdir(exist_ok=True)


def get_fallback_log_path(job_id: str) -> Path:
    """Get the fallback log file path for a job."""
    return FALLBACK_LOGS_DIR / f"{job_id}.log"


def get_current_job() -> str | None:
    """Get the current job ID for this thread."""
    return getattr(_job_context, 'job_id', None)


def write_log(log_path: Path, message: str, job_id: str | None = None) -> None:
    """Write a timestamped message to the log file AND stream via Redis.

    Args:
        log_path: Path to the log file
        message: The log message
        job_id: Optional job ID for real-time streaming (uses thread-local if not set)
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat()
    with open(log_path, "a") as f:
        f.write(f"[{timestamp}] {message}\n")

    # Also stream to Redis for real-time SSE (THREAD-SAFE)
    stream_job_id = job_id or get_current_job()
    if stream_job_id:
        try:
            log_stream_publisher.push_info(stream_job_id, message)
        except Exception:
            pass  # Don't fail job if streaming fails


def set_current_job(job_id: str | None) -> None:
    """Set the current job ID for this thread (THREAD-SAFE)."""
    _job_context.job_id = job_id


def register_active_process(job_id: str, process: subprocess.Popen) -> None:
    """Register an active subprocess for potential cancellation."""
    with _active_processes_lock:
        _active_processes[job_id] = process


def unregister_active_process(job_id: str) -> None:
    """Unregister an active subprocess."""
    with _active_processes_lock:
        _active_processes.pop(job_id, None)


def kill_job_process(job_id: str) -> bool:
    """Kill the subprocess for a job (for cancellation).

    Returns:
        True if process was found and killed, False otherwise
    """
    with _active_processes_lock:
        process = _active_processes.get(job_id)
        if process and process.poll() is None:  # Still running
            logger.info(f"Killing process {process.pid} for job {job_id}")
            try:
                process.kill()
                process.wait(timeout=5)
                return True
            except Exception as e:
                logger.error(f"Failed to kill process for job {job_id}: {e}")
                return False
    return False


def stream_finished(job_id: str) -> None:
    """Signal that job has finished streaming."""
    try:
        log_stream_publisher.push_finished(job_id)
    except Exception:
        pass


def get_job_with_ticket(job_id: str) -> tuple[Job, Ticket] | None:
    """Get a job and its associated ticket."""
    with get_sync_db() as db:
        job = (
            db.query(Job)
            .options(selectinload(Job.ticket).selectinload(Ticket.goal))
            .filter(Job.id == job_id)
            .first()
        )
        if job and job.ticket:
            # Expunge to use outside session
            db.expunge(job)
            db.expunge(job.ticket)
            if job.ticket.goal:
                db.expunge(job.ticket.goal)
            return job, job.ticket
        return None


def ensure_workspace_for_ticket(ticket_id: str, goal_id: str) -> tuple[Path | None, str | None]:
    """
    Ensure a workspace exists for a ticket and return paths.

    Returns:
        Tuple of (worktree_path, error_message).
        If successful, worktree_path is set and error_message is None.
        If failed, worktree_path is None and error_message describes the error.
    """
    with get_sync_db() as db:
        workspace_service = WorkspaceService(db)
        try:
            workspace = workspace_service.ensure_workspace(ticket_id, goal_id)
            return Path(workspace.worktree_path), None
        except NotAGitRepositoryError as e:
            return None, e.message
        except WorkspaceError as e:
            return None, e.message
        except Exception as e:
            return None, f"Failed to create workspace: {str(e)}"


def get_log_path_for_job(job_id: str, worktree_path: Path | None) -> tuple[Path, str]:
    """
    Get the log path for a job, preferring worktree location.

    Returns:
        Tuple of (full_log_path, relative_log_path_for_db).
    """
    if worktree_path:
        logs_dir = worktree_path / ".smartkanban" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        full_path = logs_dir / f"{job_id}.log"
        # Store relative path from repo root
        relative_path = f".smartkanban/worktrees/{worktree_path.name}/.smartkanban/logs/{job_id}.log"
        return full_path, relative_path
    else:
        ensure_fallback_logs_dir()
        full_path = get_fallback_log_path(job_id)
        return full_path, f"logs/{job_id}.log"


def update_job_started(job_id: str, log_path: str, timeout_seconds: int | None = None) -> bool:
    """Mark job as running. Returns False if job was canceled."""
    with get_sync_db() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return False

        # Check if job was canceled before it started
        if job.status == JobStatus.CANCELED.value:
            return False

        now = datetime.now(UTC)
        job.status = JobStatus.RUNNING.value
        job.started_at = now
        job.last_heartbeat_at = now
        job.log_path = log_path
        if timeout_seconds:
            job.timeout_seconds = timeout_seconds
        db.commit()
        return True


def update_job_heartbeat(job_id: str) -> bool:
    """Update job heartbeat timestamp. Returns False if job was canceled."""
    with get_sync_db() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return False

        # Check if job was canceled
        if job.status == JobStatus.CANCELED.value:
            return False

        job.last_heartbeat_at = datetime.now(UTC)
        db.commit()
        return True


def update_job_finished(job_id: str, status: JobStatus, exit_code: int = 0) -> None:
    """Mark job as finished with given status and exit code."""
    with get_sync_db() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = status.value
            job.finished_at = datetime.now(UTC)
            job.exit_code = exit_code
            db.commit()


def check_canceled(job_id: str) -> bool:
    """Check if the job has been canceled."""
    with get_sync_db() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        return job is not None and job.status == JobStatus.CANCELED.value


def get_evidence_dir(worktree_path: Path | None, job_id: str, repo_root: Path | None = None) -> Path:
    """Get the directory for storing evidence files.

    Args:
        worktree_path: Path to the worktree (if available)
        job_id: UUID of the job
        repo_root: Path to the main repo root (for validation)

    Returns:
        Path to evidence directory

    Raises:
        ValueError: If evidence_dir would be outside repo_root/.smartkanban
    """
    if worktree_path:
        evidence_dir = worktree_path / ".smartkanban" / "evidence" / job_id
    else:
        evidence_dir = FALLBACK_LOGS_DIR / "evidence" / job_id

    # Hardening: Validate evidence_dir is under repo_root/.smartkanban (if repo_root provided)
    if repo_root and worktree_path:
        import os

        allowed_root = (repo_root / ".smartkanban").resolve(strict=False)
        evidence_canonical = evidence_dir.resolve(strict=False)
        try:
            common = os.path.commonpath([str(evidence_canonical), str(allowed_root)])
            if common != str(allowed_root):
                raise ValueError(f"Evidence dir {evidence_dir} is not under {allowed_root}")
        except ValueError as e:
            if "different drives" in str(e).lower() or "Paths don't have" in str(e):
                raise ValueError(f"Evidence dir {evidence_dir} is not under {allowed_root}") from e
            raise

    evidence_dir.mkdir(parents=True, exist_ok=True)
    return evidence_dir


def run_verification_command(
    command: str,
    cwd: Path | None,
    evidence_dir: Path,
    evidence_id: str,
    repo_root: Path,
    timeout: int = 300,
) -> tuple[int, str, str]:
    """
    Run a verification command and capture output (SECURE - no shell injection).

    SECURITY: Uses shlex.split() to safely parse commands without shell=True.
    Only allows commands from a predefined allowlist to prevent arbitrary execution.

    Args:
        command: The command string to parse and execute
        cwd: Working directory for the command
        evidence_dir: Directory to store stdout/stderr files
        evidence_id: UUID for naming evidence files
        repo_root: Path to repo root (for computing relative paths)
        timeout: Command timeout in seconds

    Returns:
        Tuple of (exit_code, stdout_relpath, stderr_relpath) - paths are relative to repo_root

    Raises:
        ValueError: If command is not in allowlist
    """
    import shlex

    stdout_path = evidence_dir / f"{evidence_id}.stdout"
    stderr_path = evidence_dir / f"{evidence_id}.stderr"

    # Allowlist of permitted commands (prevents arbitrary code execution)
    ALLOWED_COMMANDS = {
        "pytest", "python", "python3", "ruff", "mypy", "black", "isort",
        "npm", "yarn", "pnpm", "node", "cargo", "rustc", "go", "make",
        "eslint", "tsc", "jest", "vitest", "flake8", "pylint",
    }

    try:
        # SECURE: Parse command string into argv array (prevents injection)
        # shlex.split() handles quotes and escaping properly
        cmd_argv = shlex.split(command)

        if not cmd_argv:
            raise ValueError("Empty command")

        # SECURITY CHECK: Validate first argument is in allowlist
        base_command = Path(cmd_argv[0]).name  # Strip path, get command name
        if base_command not in ALLOWED_COMMANDS:
            raise ValueError(
                f"Command '{base_command}' not in allowlist. "
                f"Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}"
            )

        # Run WITHOUT shell=True (SECURE - no command injection possible)
        result = subprocess.run(
            cmd_argv,  # List, not string
            shell=False,  # CRITICAL: No shell metacharacter interpretation
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Write stdout/stderr to files
        stdout_path.write_text(result.stdout or "")
        stderr_path.write_text(result.stderr or "")

        # Return relative paths for DB storage (security: no absolute paths in DB)
        stdout_rel = str(stdout_path.relative_to(repo_root))
        stderr_rel = str(stderr_path.relative_to(repo_root))

        return result.returncode, stdout_rel, stderr_rel

    except subprocess.TimeoutExpired as e:
        # Write partial output if available
        stdout_path.write_text(e.stdout.decode() if e.stdout else "Command timed out")
        stderr_path.write_text(e.stderr.decode() if e.stderr else "")
        stdout_rel = str(stdout_path.relative_to(repo_root))
        stderr_rel = str(stderr_path.relative_to(repo_root))
        return -1, stdout_rel, stderr_rel

    except ValueError as e:
        # Command validation failed (not in allowlist or empty)
        stdout_path.write_text("")
        stderr_path.write_text(f"Command validation failed: {str(e)}")
        stdout_rel = str(stdout_path.relative_to(repo_root))
        stderr_rel = str(stderr_path.relative_to(repo_root))
        return -1, stdout_rel, stderr_rel

    except FileNotFoundError as e:
        # Command not found in PATH
        stdout_path.write_text("")
        stderr_path.write_text(f"Command not found: {cmd_argv[0]}")
        stdout_rel = str(stdout_path.relative_to(repo_root))
        stderr_rel = str(stderr_path.relative_to(repo_root))
        return -1, stdout_rel, stderr_rel

    except Exception as e:
        stdout_path.write_text("")
        stderr_path.write_text(f"Error running command: {str(e)}")

        stdout_rel = str(stdout_path.relative_to(repo_root))
        stderr_rel = str(stderr_path.relative_to(repo_root))
        return -1, stdout_rel, stderr_rel


def create_evidence_record(
    ticket_id: str,
    job_id: str,
    command: str,
    exit_code: int,
    stdout_path: str,
    stderr_path: str,
    evidence_id: str,
    kind: EvidenceKind = EvidenceKind.COMMAND_LOG,
) -> Evidence:
    """Create an Evidence record in the database.

    Args:
        ticket_id: UUID of the ticket
        job_id: UUID of the job
        command: Command that was executed
        exit_code: Exit code from the command
        stdout_path: Path to stdout file
        stderr_path: Path to stderr file
        evidence_id: UUID for this evidence record
        kind: Type of evidence (executor_stdout, git_diff_stat, etc.)

    Returns:
        The created Evidence record
    """
    with get_sync_db() as db:
        evidence = Evidence(
            id=evidence_id,
            ticket_id=ticket_id,
            job_id=job_id,
            kind=kind.value,
            command=command,
            exit_code=exit_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
        db.add(evidence)
        db.commit()
        db.refresh(evidence)
        return evidence


def create_revision_for_job(
    ticket_id: str,
    job_id: str,
    diff_stat_evidence_id: str | None = None,
    diff_patch_evidence_id: str | None = None,
) -> str | None:
    """Create a Revision record for a job that produced changes.

    This function is IDEMPOTENT - if the same job_id is retried, returns existing revision.
    Automatically supersedes any existing open revisions for the ticket.

    Args:
        ticket_id: UUID of the ticket
        job_id: UUID of the job
        diff_stat_evidence_id: Optional evidence ID for git diff stat
        diff_patch_evidence_id: Optional evidence ID for git diff patch

    Returns:
        The revision ID if created/found, None on error
    """
    from app.models.revision import Revision, RevisionStatus

    with get_sync_db() as db:
        try:
            # IDEMPOTENCY CHECK: Return existing revision if job was already processed
            existing = (
                db.query(Revision)
                .filter(
                    Revision.ticket_id == ticket_id,
                    Revision.job_id == job_id,
                )
                .first()
            )
            if existing:
                import logging
                logging.getLogger(__name__).info(
                    f"Revision already exists for job {job_id}: {existing.id}"
                )
                return existing.id

            # Supersede any open revisions (in same transaction)
            open_revisions = (
                db.query(Revision)
                .filter(
                    Revision.ticket_id == ticket_id,
                    Revision.status == RevisionStatus.OPEN.value,
                )
                .all()
            )
            for rev in open_revisions:
                rev.status = RevisionStatus.SUPERSEDED.value

            # Get next revision number
            last_revision = (
                db.query(Revision)
                .filter(Revision.ticket_id == ticket_id)
                .order_by(Revision.number.desc())
                .first()
            )
            next_number = (last_revision.number if last_revision else 0) + 1

            # Create new revision
            revision = Revision(
                ticket_id=ticket_id,
                job_id=job_id,
                number=next_number,
                status=RevisionStatus.OPEN.value,
                diff_stat_evidence_id=diff_stat_evidence_id,
                diff_patch_evidence_id=diff_patch_evidence_id,
            )
            db.add(revision)
            db.commit()
            db.refresh(revision)
            return revision.id
        except Exception as e:
            db.rollback()
            # Log but don't fail the job
            import logging
            logging.getLogger(__name__).error(f"Failed to create revision: {e}")
            return None


def get_feedback_bundle_for_ticket(ticket_id: str) -> dict | None:
    """Get the feedback bundle from the most recent changes_requested revision.

    This is used when re-running an execute job after changes were requested.

    Args:
        ticket_id: UUID of the ticket

    Returns:
        Feedback bundle dict if found, None otherwise
    """
    from app.models.review_comment import ReviewComment
    from app.models.review_summary import ReviewSummary
    from app.models.revision import Revision, RevisionStatus

    with get_sync_db() as db:
        try:
            # Find the most recent revision with changes_requested status
            revision = (
                db.query(Revision)
                .filter(
                    Revision.ticket_id == ticket_id,
                    Revision.status == RevisionStatus.CHANGES_REQUESTED.value,
                )
                .order_by(Revision.number.desc())
                .first()
            )

            if not revision:
                return None

            # Get review summary
            review_summary = (
                db.query(ReviewSummary)
                .filter(ReviewSummary.revision_id == revision.id)
                .first()
            )

            # Get unresolved comments
            comments = (
                db.query(ReviewComment)
                .filter(
                    ReviewComment.revision_id == revision.id,
                    ReviewComment.resolved == False,  # noqa: E712
                )
                .order_by(ReviewComment.created_at)
                .all()
            )

            # Build feedback bundle
            return {
                "ticket_id": ticket_id,
                "revision_id": revision.id,
                "revision_number": revision.number,
                "decision": "changes_requested",
                "summary": review_summary.body if review_summary else "",
                "comments": [
                    {
                        "file_path": c.file_path,
                        "line_number": c.line_number,
                        "anchor": c.anchor,
                        "body": c.body,
                        "line_content": c.line_content,
                    }
                    for c in comments
                ],
            }
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to get feedback bundle: {e}")
            return None


def transition_ticket_sync(
    ticket_id: str,
    to_state: TicketState,
    reason: str | None = None,
    payload: dict | None = None,
    actor_id: str = "worker",
    auto_verify: bool = True,
) -> None:
    """
    Transition a ticket to a new state synchronously.

    Args:
        ticket_id: The UUID of the ticket
        to_state: The target state
        reason: Optional reason for the transition
        payload: Optional payload for the event
        actor_id: The ID of the actor performing the transition
        auto_verify: If True, auto-enqueue verify job when entering verifying state
    """
    with get_sync_db() as db:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            return

        from_state = ticket.state
        ticket.state = to_state.value

        # Create transition event
        event = TicketEvent(
            ticket_id=ticket_id,
            event_type=EventType.TRANSITIONED.value,
            from_state=from_state,
            to_state=to_state.value,
            actor_type=ActorType.EXECUTOR.value,
            actor_id=actor_id,
            reason=reason,
            payload_json=json.dumps(payload) if payload else None,
        )
        db.add(event)
        db.commit()

    # Auto-trigger verification when entering verifying state
    if auto_verify and to_state == TicketState.VERIFYING:
        _enqueue_verify_job_sync(ticket_id)


def _enqueue_verify_job_sync(ticket_id: str) -> str | None:
    """
    Synchronously enqueue a verify job for a ticket (idempotent).

    Idempotency: Only creates a new verify job if there is no active
    (queued or running) verify job for this ticket. This prevents
    duplicate verify jobs from race conditions or retries.

    Returns:
        The job ID if created, None if skipped (already active).
    """
    from app.models.job import Job, JobKind, JobStatus

    with get_sync_db() as db:
        # IDEMPOTENCY CHECK: Is there already an active verify job?
        active_verify = (
            db.query(Job)
            .filter(
                Job.ticket_id == ticket_id,
                Job.kind == JobKind.VERIFY.value,
                Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
            )
            .first()
        )

        if active_verify:
            # Already has an active verify job - skip to avoid duplicates
            return None

        # Get the ticket to inherit board_id
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        board_id = ticket.board_id if ticket else None

        # Create the job record with board_id for permission scoping
        job = Job(
            ticket_id=ticket_id,
            board_id=board_id,
            kind=JobKind.VERIFY.value,
            status=JobStatus.QUEUED.value,
        )
        db.add(job)
        db.flush()
        job_id = job.id

        # Enqueue the Celery task using send_task (safer for forked processes)
        from app.celery_app import celery_app
        task = celery_app.send_task("verify_ticket", args=[job_id])

        # Store the Celery task ID
        job.celery_task_id = task.id
        db.commit()

        return job_id


def run_executor_cli(
    command: list[str],
    cwd: Path,
    evidence_dir: Path,
    evidence_id: str,
    repo_root: Path,
    timeout: int = 600,
    job_id: str | None = None,
    normalize_logs: bool = False,
    stdin_content: str | None = None,
) -> tuple[int, str, str]:
    """
    Run the executor CLI and capture output with real-time streaming.

    Args:
        command: The CLI command to run as a list of arguments
        cwd: Working directory for the command
        evidence_dir: Directory to store stdout/stderr files
        evidence_id: UUID for naming evidence files
        repo_root: Path to repo root (for computing relative paths)
        timeout: Command timeout in seconds
        job_id: Optional job ID for real-time log streaming
        normalize_logs: If True, parse cursor-agent JSON and stream normalized entries
        stdin_content: Optional content to pipe to the process via stdin

    Returns:
        Tuple of (exit_code, stdout_relpath, stderr_relpath) - paths are relative to repo_root
    """
    import json as json_module
    import threading
    
    stdout_path = evidence_dir / f"{evidence_id}.stdout"
    stderr_path = evidence_dir / f"{evidence_id}.stderr"
    
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    
    # Create normalizer if needed
    normalizer = CursorLogNormalizer(str(cwd)) if normalize_logs else None

    try:
        # Use Popen for real-time streaming instead of blocking run()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE if stdin_content else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
        )

        # Write stdin content and close to signal EOF
        if stdin_content and process.stdin:
            process.stdin.write(stdin_content)
            process.stdin.close()
        
        def stream_output(pipe, lines_list, is_stderr=False, stop_event=None):
            """Read and stream output line by line with stop event support."""
            try:
                for line in iter(pipe.readline, ''):
                    # Check if we should stop
                    if stop_event and stop_event.is_set():
                        logger.debug(f"Stream thread stopping due to stop_event ({'stderr' if is_stderr else 'stdout'})")
                        break
                    if not line:
                        break
                    line = line.rstrip('\n')
                    lines_list.append(line)
                    
                    # Stream to Redis for real-time SSE
                    if job_id:
                        try:
                            if is_stderr:
                                log_stream_publisher.push_stderr(job_id, line)
                            elif normalizer:
                                # Parse and stream normalized entries
                                entries = normalizer.process_line(line)
                                for entry in entries:
                                    # Serialize normalized entry as JSON
                                    entry_data = {
                                        "entry_type": entry.entry_type.value,
                                        "content": entry.content,
                                        "sequence": entry.sequence,
                                        "tool_name": entry.tool_name,
                                        "action_type": entry.action_type.value if entry.action_type else None,
                                        "tool_status": entry.tool_status.value if entry.tool_status else None,
                                        "metadata": entry.metadata,
                                    }
                                    log_stream_publisher.push(
                                        job_id, 
                                        LogLevel.NORMALIZED, 
                                        json_module.dumps(entry_data)
                                    )
                            else:
                                log_stream_publisher.push_stdout(job_id, line)
                        except Exception:
                            pass  # Don't fail execution if streaming fails
            finally:
                pipe.close()
        
        # Create stop events for graceful thread termination
        stdout_stop_event = threading.Event()
        stderr_stop_event = threading.Event()

        # Stream stdout and stderr in parallel threads
        # Use daemon=True so threads don't block process exit if they get stuck
        stdout_thread = threading.Thread(
            target=stream_output,
            args=(process.stdout, stdout_lines, False, stdout_stop_event),
            daemon=True,
            name=f"stdout-{job_id[:8] if job_id else 'unknown'}",
        )
        stderr_thread = threading.Thread(
            target=stream_output,
            args=(process.stderr, stderr_lines, True, stderr_stop_event),
            daemon=True,
            name=f"stderr-{job_id[:8] if job_id else 'unknown'}",
        )

        stdout_thread.start()
        stderr_thread.start()

        # Register process for cancellation support
        if job_id:
            register_active_process(job_id, process)

        # Wait for process with timeout AND poll for cancellation
        try:
            start_time = time.time()
            while True:
                # Check if process finished
                exit_code = process.poll()
                if exit_code is not None:
                    break

                # Check if job was canceled
                if job_id and check_canceled(job_id):
                    logger.info(f"Job {job_id} canceled, killing process {process.pid}")
                    process.kill()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()  # Force kill if still alive
                        process.wait()
                    stdout_lines.append(f"\n[CANCELED] Job canceled by user")
                    exit_code = -2  # Special exit code for cancellation
                    break

                # Check timeout
                if time.time() - start_time > timeout:
                    process.kill()
                    process.wait()
                    stdout_lines.append(f"\n[TIMEOUT] Process killed after {timeout} seconds")
                    exit_code = -1
                    break

                # Poll every second
                time.sleep(1)

        finally:
            # Unregister process
            if job_id:
                unregister_active_process(job_id)

            # Signal threads to stop gracefully
            stdout_stop_event.set()
            stderr_stop_event.set()

            # Close pipes to unblock threads waiting on readline()
            if process.stdout:
                try:
                    process.stdout.close()
                except Exception:
                    pass
            if process.stderr:
                try:
                    process.stderr.close()
                except Exception:
                    pass

        # Wait for output threads to finish (with timeout to prevent blocking)
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        # CRITICAL: Warn if threads didn't stop (indicates resource leak)
        if stdout_thread.is_alive():
            logger.warning(
                f"stdout thread for job {job_id[:8] if job_id else 'unknown'} did not stop after 5s timeout - potential resource leak"
            )
        if stderr_thread.is_alive():
            logger.warning(
                f"stderr thread for job {job_id[:8] if job_id else 'unknown'} did not stop after 5s timeout - potential resource leak"
            )
        
        # Write captured output to files
        stdout_path.write_text('\n'.join(stdout_lines))
        stderr_path.write_text('\n'.join(stderr_lines))

        # Return relative paths for secure DB storage
        stdout_rel = str(stdout_path.relative_to(repo_root))
        stderr_rel = str(stderr_path.relative_to(repo_root))
        return exit_code, stdout_rel, stderr_rel

    except subprocess.TimeoutExpired as e:
        # Write partial output if available
        stdout_path.write_text(e.stdout.decode() if e.stdout else f"Command timed out after {timeout} seconds")
        stderr_path.write_text(e.stderr.decode() if e.stderr else "")
        stdout_rel = str(stdout_path.relative_to(repo_root))
        stderr_rel = str(stderr_path.relative_to(repo_root))
        return -1, stdout_rel, stderr_rel

    except FileNotFoundError as e:
        stdout_path.write_text("")
        stderr_path.write_text(f"Executor CLI not found: {str(e)}")
        stdout_rel = str(stdout_path.relative_to(repo_root))
        stderr_rel = str(stderr_path.relative_to(repo_root))
        return -1, stdout_rel, stderr_rel

    except Exception as e:
        stdout_path.write_text("")
        stderr_path.write_text(f"Error running executor CLI: {str(e)}")
        stdout_rel = str(stdout_path.relative_to(repo_root))
        stderr_rel = str(stderr_path.relative_to(repo_root))
        return -1, stdout_rel, stderr_rel


def capture_git_diff(
    cwd: Path,
    evidence_dir: Path,
    evidence_id: str,
    repo_root: Path,
) -> tuple[int, str, str, str, bool]:
    """
    Capture git diff output for changes made in the worktree.

    This function captures both:
    1. Changes to tracked files (via git diff)
    2. New untracked files (via git status --porcelain)

    Args:
        cwd: Working directory (worktree path)
        evidence_dir: Directory to store diff files
        evidence_id: UUID for naming evidence files
        repo_root: Path to repo root (for computing relative paths)

    Returns:
        Tuple of (exit_code, diff_stat_relpath, diff_patch_relpath, diff_stat_text, has_changes)
        has_changes is True if there are uncommitted changes OR new untracked files.
        Paths are relative to repo_root.
    """
    diff_stat_path = evidence_dir / f"{evidence_id}.diff_stat"
    diff_patch_path = evidence_dir / f"{evidence_id}.diff_patch"
    stderr_path = evidence_dir / f"{evidence_id}.stderr"

    diff_stat = ""
    has_changes = False
    has_tracked_changes = False
    has_untracked_files = False
    untracked_files: list[str] = []

    try:
        # First get the diff stat for tracked file changes
        stat_result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        diff_stat = stat_result.stdout.strip() if stat_result.stdout else ""

        # Then get the full patch for tracked files
        patch_result = subprocess.run(
            ["git", "diff"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        diff_patch = patch_result.stdout.strip() if patch_result.stdout else ""
        has_tracked_changes = bool(diff_patch)

        # Also check for untracked files (new files created by executor)
        # These won't show up in git diff but represent real work done
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if status_result.stdout:
            for line in status_result.stdout.strip().split("\n"):
                if line.startswith("??"):
                    # Untracked file - extract path (skip "?? " prefix)
                    file_path = line[3:].strip()
                    # Skip .smartkanban directory (internal files)
                    if not file_path.startswith(".smartkanban"):
                        untracked_files.append(file_path)
            has_untracked_files = len(untracked_files) > 0

        # Determine if there are actual changes (tracked OR untracked)
        has_changes = has_tracked_changes or has_untracked_files

        # Build comprehensive diff stat that includes untracked files
        stat_parts = []
        if diff_stat:
            stat_parts.append(diff_stat)
        if untracked_files:
            stat_parts.append(f"\nNew files (untracked):")
            for f in untracked_files[:20]:  # Limit to 20 files in summary
                stat_parts.append(f"  + {f}")
            if len(untracked_files) > 20:
                stat_parts.append(f"  ... and {len(untracked_files) - 20} more")

        final_diff_stat = "\n".join(stat_parts) if stat_parts else "(no changes)"
        diff_stat_path.write_text(final_diff_stat)

        # For patch, also include untracked file contents if any
        patch_parts = []
        if diff_patch:
            patch_parts.append(diff_patch)
        if untracked_files:
            patch_parts.append("\n\n# === New untracked files ===\n")
            for f in untracked_files[:10]:  # Limit to 10 files to avoid huge patches
                file_full_path = cwd / f
                if file_full_path.is_file():
                    try:
                        content = file_full_path.read_text()
                        # Truncate large files
                        if len(content) > 5000:
                            content = content[:5000] + "\n... (truncated)"
                        patch_parts.append(f"\n# +++ {f}\n{content}")
                    except Exception:
                        patch_parts.append(f"\n# +++ {f} (could not read)")

        final_patch = "\n".join(patch_parts) if patch_parts else "(no changes)"
        diff_patch_path.write_text(final_patch)

        # Combine stderr from commands
        combined_stderr = ""
        if stat_result.stderr:
            combined_stderr += f"git diff --stat stderr:\n{stat_result.stderr}\n"
        if patch_result.stderr:
            combined_stderr += f"git diff stderr:\n{patch_result.stderr}\n"
        if status_result.stderr:
            combined_stderr += f"git status stderr:\n{status_result.stderr}\n"
        stderr_path.write_text(combined_stderr)

        # Return relative paths for secure DB storage
        diff_stat_rel = str(diff_stat_path.relative_to(repo_root))
        diff_patch_rel = str(diff_patch_path.relative_to(repo_root))
        return 0, diff_stat_rel, diff_patch_rel, final_diff_stat, has_changes

    except subprocess.TimeoutExpired:
        diff_stat_path.write_text("Git diff timed out")
        diff_patch_path.write_text("")
        stderr_path.write_text("Git diff command timed out after 60 seconds")
        diff_stat_rel = str(diff_stat_path.relative_to(repo_root))
        diff_patch_rel = str(diff_patch_path.relative_to(repo_root))
        return -1, diff_stat_rel, diff_patch_rel, "(timeout)", False

    except Exception as e:
        diff_stat_path.write_text("")
        diff_patch_path.write_text("")
        stderr_path.write_text(f"Error running git diff: {str(e)}")
        diff_stat_rel = str(diff_stat_path.relative_to(repo_root))
        diff_patch_rel = str(diff_patch_path.relative_to(repo_root))
        return -1, diff_stat_rel, diff_patch_rel, "(error)", False


# =============================================================================
# NO-CHANGES ANALYSIS (LLM-powered)
# =============================================================================

@dataclass
class NoChangesAnalysis:
    """Result of analyzing why no code changes were produced."""
    
    reason: str  # Human-readable explanation
    needs_code_changes: bool  # True if code changes are actually needed
    requires_manual_work: bool  # True if manual human intervention is required
    manual_work_description: str | None  # Description of manual work needed (if any)


def analyze_no_changes_reason(
    ticket_title: str,
    ticket_description: str | None,
    executor_stdout: str,
    planner_config: "PlannerConfig",
) -> NoChangesAnalysis:
    """
    Analyze executor output to determine why no code changes were produced.
    
    Uses LLM to understand the executor's reasoning and categorize the result:
    1. No changes needed - the task doesn't require code modifications
    2. Manual work required - needs human intervention (config, external tools, etc.)
    3. Unclear/error - couldn't determine, needs investigation
    
    Args:
        ticket_title: Title of the ticket being executed
        ticket_description: Description of the ticket
        executor_stdout: The stdout output from the executor
        planner_config: Planner configuration for LLM settings
        
    Returns:
        NoChangesAnalysis with categorized result
    """
    from app.services.llm_service import LLMService
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Truncate executor output to avoid token limits
    max_output_chars = 8000
    truncated_stdout = executor_stdout[:max_output_chars]
    if len(executor_stdout) > max_output_chars:
        truncated_stdout += "\n... (output truncated)"
    
    system_prompt = """You are a technical analyst reviewing why a coding agent completed a task without making any code changes.

Analyze the executor output and categorize the result into ONE of these categories:

1. NO_CHANGES_NEEDED - The task genuinely doesn't require code changes. Examples:
   - The requested functionality already exists
   - The code is already correct as-is
   - The task was a review/analysis that doesn't need modifications
   
2. MANUAL_WORK_REQUIRED - The task requires human intervention that the agent cannot do. Examples:
   - Configuration changes in external systems
   - Running commands that require special permissions
   - Setting up environment variables or secrets
   - Installing system packages
   - Deploying or running external services
   - Manual testing or verification steps
   
3. NEEDS_INVESTIGATION - Unable to determine clearly, needs human review

Your response MUST be valid JSON with this exact structure:
{
  "category": "NO_CHANGES_NEEDED" | "MANUAL_WORK_REQUIRED" | "NEEDS_INVESTIGATION",
  "reason": "Brief explanation of why no code changes were made",
  "manual_work_description": "If MANUAL_WORK_REQUIRED, describe exactly what needs to be done manually. Otherwise null."
}"""

    user_prompt = f"""A coding agent was asked to work on this ticket but produced no code changes.

TICKET TITLE: {ticket_title}

TICKET DESCRIPTION:
{ticket_description or "(no description)"}

EXECUTOR OUTPUT:
{truncated_stdout}

Analyze why no code changes were produced and categorize the result."""

    try:
        llm_service = LLMService(planner_config)
        response = llm_service.call_completion(
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=500,
            system_prompt=system_prompt,
            timeout=30,
        )
        data = llm_service.safe_parse_json(response.content, {})
        
        category = data.get("category", "NEEDS_INVESTIGATION")
        reason = data.get("reason", "Unable to determine why no changes were produced")
        manual_work_desc = data.get("manual_work_description")
        
        return NoChangesAnalysis(
            reason=reason,
            needs_code_changes=(category == "NEEDS_INVESTIGATION"),
            requires_manual_work=(category == "MANUAL_WORK_REQUIRED"),
            manual_work_description=manual_work_desc if category == "MANUAL_WORK_REQUIRED" else None,
        )
        
    except Exception as e:
        logger.error(f"Failed to analyze no-changes reason: {e}")
        # Fallback: treat as needs investigation
        return NoChangesAnalysis(
            reason=f"Analysis failed: {str(e)}",
            needs_code_changes=True,
            requires_manual_work=False,
            manual_work_description=None,
        )


def create_manual_work_followup_sync(
    parent_ticket_id: str,
    parent_ticket_title: str,
    manual_work_description: str,
    goal_id: str,
    board_id: str | None = None,
) -> str | None:
    """
    Create a follow-up ticket for manual work that the agent cannot perform.
    
    The ticket is created in PROPOSED state with a [Manual Work] prefix.
    
    Args:
        parent_ticket_id: ID of the blocked ticket
        parent_ticket_title: Title of the blocked ticket
        manual_work_description: Description of the manual work needed
        goal_id: Goal ID to link the follow-up ticket to
        board_id: Optional board ID for permission scoping
        
    Returns:
        The ID of the created follow-up ticket, or None if creation failed
    """
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        with get_sync_db() as db:
            # Get the parent ticket for priority inheritance
            parent_ticket = db.query(Ticket).filter(Ticket.id == parent_ticket_id).first()
            priority = parent_ticket.priority if parent_ticket else None
            
            # Create follow-up ticket with [Manual Work] prefix
            followup_title = f"[Manual Work] {parent_ticket_title}"
            # Truncate if too long (max 255 chars)
            if len(followup_title) > 255:
                followup_title = followup_title[:252] + "..."
            
            followup_description = f"""This ticket requires manual human intervention that the automated agent cannot perform.

**Original Ticket:** {parent_ticket_title}

**Manual Work Required:**
{manual_work_description}

**Instructions:**
1. Review the manual work description above
2. Perform the required actions manually
3. Mark this ticket as done when complete
"""
            
            followup_ticket = Ticket(
                goal_id=goal_id,
                board_id=board_id,
                title=followup_title,
                description=followup_description,
                state=TicketState.PROPOSED.value,
                priority=priority,
            )
            db.add(followup_ticket)
            db.flush()
            followup_id = followup_ticket.id
            
            # Create creation event for follow-up ticket
            creation_event = TicketEvent(
                ticket_id=followup_id,
                event_type=EventType.CREATED.value,
                from_state=None,
                to_state=TicketState.PROPOSED.value,
                actor_type=ActorType.EXECUTOR.value,
                actor_id="execute_worker",
                reason=f"Manual work follow-up for blocked ticket: {parent_ticket_title}",
                payload_json=json.dumps({
                    "parent_ticket_id": parent_ticket_id,
                    "manual_work": True,
                    "auto_generated": True,
                }),
            )
            db.add(creation_event)
            
            # Create link event on the parent ticket
            link_event = TicketEvent(
                ticket_id=parent_ticket_id,
                event_type=EventType.COMMENT.value,
                from_state=TicketState.BLOCKED.value,
                to_state=TicketState.BLOCKED.value,
                actor_type=ActorType.EXECUTOR.value,
                actor_id="execute_worker",
                reason=f"Created manual work follow-up ticket: {followup_title}",
                payload_json=json.dumps({
                    "followup_ticket_id": followup_id,
                    "manual_work_followup": True,
                }),
            )
            db.add(link_event)
            
            db.commit()
            
            logger.info(f"Created manual work follow-up ticket {followup_id} for blocked ticket {parent_ticket_id}")
            return followup_id
            
    except Exception as e:
        logger.error(f"Failed to create manual work follow-up ticket: {e}")
        return None


def _get_related_tickets_context_sync(ticket_id: str) -> dict | None:
    """
    Get context about related tickets for better prompt building.
    
    Returns dict with:
        - dependencies: list of tickets this ticket depends on
        - completed_tickets: list of DONE tickets in the same goal
        - goal_title: title of the goal this ticket belongs to
    """
    from sqlalchemy.orm import selectinload
    from app.database_sync import sync_engine
    from app.models.ticket import Ticket
    from app.models.goal import Goal
    from app.state_machine import TicketState
    from sqlalchemy.orm import Session
    
    # Use the shared sync_engine instead of creating a new one each time
    # This prevents connection pool exhaustion
    with Session(sync_engine) as db:
        # Get the current ticket with its goal and dependencies
        ticket = db.query(Ticket).options(
            selectinload(Ticket.blocked_by),
            selectinload(Ticket.goal)
        ).filter(Ticket.id == ticket_id).first()
        
        if not ticket or not ticket.goal_id:
            return None
        
        context = {
            "goal_title": ticket.goal.title if ticket.goal else None,
            "dependencies": [],
            "completed_tickets": []
        }
        
        # Add dependency information
        if ticket.blocked_by:
            context["dependencies"].append({
                "title": ticket.blocked_by.title,
                "state": ticket.blocked_by.state
            })
        
        # Get completed tickets in the same goal (for context)
        completed_tickets = db.query(Ticket).filter(
            Ticket.goal_id == ticket.goal_id,
            Ticket.state == TicketState.DONE.value,
            Ticket.id != ticket_id
        ).order_by(Ticket.created_at.asc()).limit(5).all()
        
        for comp_ticket in completed_tickets:
            context["completed_tickets"].append({
                "title": comp_ticket.title,
                "description": comp_ticket.description
            })
        
        return context if (context["dependencies"] or context["completed_tickets"]) else None


@celery_app.task(bind=True, name="execute_ticket")
def execute_ticket_task(self, job_id: str) -> dict:
    """
    Execute task for a ticket using Claude Code CLI (headless) or Cursor CLI (interactive).

    Execution Modes:
        - Claude CLI (headless): Runs automatically, transitions based on result.
        - Cursor CLI (interactive): Prepares workspace + prompt, then hands off to user.

    State Transitions:
        - Headless success with diff → verifying
        - Headless success with NO diff → blocked (reason: no changes produced)
        - Headless failure → blocked
        - Interactive (Cursor) → needs_human immediately

    YOLO Mode:
        If yolo_mode is enabled in config AND the repo is in the allowlist,
        Claude CLI runs with --dangerously-skip-permissions. Otherwise it runs
        in permissioned mode (may require user approval for certain operations).
    """
    # Enable real-time log streaming for this job
    set_current_job(job_id)
    
    try:
        return _execute_ticket_task_impl(job_id)
    finally:
        # Signal streaming finished and clean up
        stream_finished(job_id)
        set_current_job(None)


def _execute_ticket_task_impl(job_id: str) -> dict:
    """Implementation of execute_ticket_task (separated for streaming wrapper)."""
    # Get job and ticket info
    result = get_job_with_ticket(job_id)
    if not result:
        return {"job_id": job_id, "status": "failed", "error": "Job or ticket not found"}

    job, ticket = result
    goal_id = ticket.goal_id
    ticket_id = ticket.id

    # Check if ticket is already in a terminal/blocked state - skip execution if so
    # This prevents re-execution of jobs for already-blocked tickets
    if ticket.state in [TicketState.BLOCKED.value, TicketState.DONE.value, TicketState.ABANDONED.value]:
        import logging
        logging.getLogger(__name__).info(
            f"Skipping execution for job {job_id}: ticket {ticket_id} is already in {ticket.state} state"
        )
        update_job_finished(job_id, JobStatus.FAILED, exit_code=0)
        return {
            "job_id": job_id,
            "status": "skipped",
            "reason": f"Ticket already in {ticket.state} state",
            "ticket_id": ticket_id,
        }

    # Ensure workspace exists
    worktree_path, workspace_error = ensure_workspace_for_ticket(ticket_id, goal_id)

    # Get log path (use worktree if available, fallback otherwise)
    log_path, log_path_relative = get_log_path_for_job(job_id, worktree_path)

    write_log(log_path, "Starting execute task...")

    # Workspace is required for execution
    if workspace_error or not worktree_path:
        write_log(log_path, f"ERROR: Could not create workspace: {workspace_error or 'Unknown error'}")
        write_log(log_path, "Execution requires a valid git worktree. Failing job.")
        update_job_started(job_id, log_path_relative)
        update_job_finished(job_id, JobStatus.FAILED, exit_code=1)
        transition_ticket_sync(
            ticket_id,
            TicketState.BLOCKED,
            reason=f"Execution failed: workspace creation error - {workspace_error}",
            actor_id="execute_worker",
        )
        return {"job_id": job_id, "status": "failed", "error": workspace_error}

    write_log(log_path, f"Workspace ready at: {worktree_path}")

    # Mark as running
    if not update_job_started(job_id, log_path_relative):
        write_log(log_path, "Job was canceled or not found, aborting.")
        raise Ignore()

    # Transition ticket to EXECUTING state BEFORE any execution work begins
    # This is critical - the ticket MUST be in EXECUTING state while running
    # This handles transitions from PLANNED, DONE (changes requested), or NEEDS_HUMAN
    from app.state_machine import validate_transition
    
    with get_sync_db() as db:
        current_ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not current_ticket:
            write_log(log_path, "ERROR: Ticket not found in database")
            update_job_finished(job_id, JobStatus.FAILED, exit_code=1)
            return {"job_id": job_id, "status": "failed", "error": "Ticket not found"}
        
        current_state = TicketState(current_ticket.state)
        write_log(log_path, f"Current ticket state: '{current_state.value}'")
        
        if current_state == TicketState.EXECUTING:
            write_log(log_path, "Ticket already in 'executing' state")
        elif validate_transition(current_state, TicketState.EXECUTING):
            write_log(log_path, f"Transitioning ticket from '{current_state.value}' to 'executing'")
            # Important: Do transition INSIDE the same db context to ensure atomicity
            current_ticket.state = TicketState.EXECUTING.value
            
            # Create transition event
            event = TicketEvent(
                ticket_id=ticket_id,
                event_type=EventType.TRANSITIONED.value,
                from_state=current_state.value,
                to_state=TicketState.EXECUTING.value,
                actor_type=ActorType.EXECUTOR.value,
                actor_id="execute_worker",
                reason=f"Execution started (job {job_id})",
                payload_json=json.dumps({"job_id": job_id}),
            )
            db.add(event)
            db.commit()
            write_log(log_path, "Successfully transitioned to 'executing' state")
        else:
            # This shouldn't happen for valid workflows, but log and continue
            write_log(log_path, f"WARNING: Cannot transition from '{current_state.value}' to 'executing' (invalid transition)")
            write_log(log_path, "Continuing execution anyway...")

    # Check for cancellation
    if check_canceled(job_id):
        write_log(log_path, "Job canceled, stopping execution.")
        raise Ignore()

    # Load configuration from the worktree (where smartkanban.yaml should be)
    # Apply board-level overrides if present
    # Disable cache to ensure we get the latest config
    config_service = ConfigService(worktree_path)

    # Get board config for overrides
    board_config = None
    if ticket.board_id:
        with get_sync_db() as db:
            from app.models.board import Board
            board = db.query(Board).filter(Board.id == ticket.board_id).first()
            if board and board.config:
                board_config = board.config

    # Load config with board overrides applied
    config = config_service.load_config_with_board_overrides(
        board_config=board_config,
        use_cache=False
    )
    execute_config = config.execute_config
    planner_config = config.planner_config

    # Get main repo path for validation
    # Use WorkspaceService.get_repo_path() which knows the actual main repo root
    # (not derived from worktree, which would be wrong for allowlist checking)
    main_repo_path = WorkspaceService.get_repo_path()

    # =========================================================================
    # WORKTREE SAFETY VALIDATION (enforced, not assumed)
    # =========================================================================
    write_log(log_path, "Validating worktree safety...")
    worktree_validator = WorktreeValidator(main_repo_path)
    validation_result = worktree_validator.validate(worktree_path)

    if not validation_result.valid:
        write_log(log_path, f"SAFETY CHECK FAILED: {validation_result.error}")
        write_log(log_path, f"Reason: {validation_result.message}")
        write_log(log_path, "Refusing to execute in unsafe location.")
        update_job_finished(job_id, JobStatus.FAILED, exit_code=1)
        transition_ticket_sync(
            ticket_id,
            TicketState.BLOCKED,
            reason=f"Safety check failed: {validation_result.message}",
            payload={
                "validation_error": validation_result.error,
                "worktree_path": str(worktree_path),
                "main_repo_path": str(main_repo_path),
            },
            actor_id="execute_worker",
        )
        return {
            "job_id": job_id,
            "status": "failed",
            "error": f"Safety check failed: {validation_result.message}",
            "validation_error": validation_result.error,
        }

    write_log(log_path, f"Worktree validated: branch={validation_result.branch}")

    # =========================================================================
    # YOLO MODE CHECK (refuse if enabled but allowlist empty)
    # =========================================================================
    yolo_status = execute_config.check_yolo_status(
        str(worktree_path.resolve()),
        repo_root=str(main_repo_path),
    )
    model_info = f", model={execute_config.executor_model}" if execute_config.executor_model else ""
    write_log(log_path, f"Execute config: timeout={execute_config.timeout}s, preferred_executor={execute_config.preferred_executor}{model_info}")

    if yolo_status == YoloStatus.REFUSED:
        refusal_reason = execute_config.get_yolo_refusal_reason(repo_root=str(main_repo_path))
        write_log(log_path, f"YOLO MODE REFUSED: {refusal_reason}")
        write_log(log_path, "Transitioning to needs_human for manual approval.")
        update_job_finished(job_id, JobStatus.SUCCEEDED, exit_code=0)
        transition_ticket_sync(
            ticket_id,
            TicketState.NEEDS_HUMAN,
            reason=f"YOLO mode refused: {refusal_reason}",
            payload={
                "yolo_refused": True,
                "refusal_reason": refusal_reason,
                "worktree": str(worktree_path),
            },
            actor_id="execute_worker",
        )
        return {
            "job_id": job_id,
            "status": "yolo_refused",
            "worktree": str(worktree_path),
            "reason": refusal_reason,
        }

    yolo_enabled = yolo_status == YoloStatus.ALLOWED
    write_log(log_path, f"YOLO mode: {yolo_status.value}")

    # Detect available executor CLI
    try:
        executor_info = ExecutorService.detect_executor(
            preferred=execute_config.preferred_executor,
            agent_path=planner_config.agent_path,
        )
        write_log(log_path, f"Found executor: {executor_info.executor_type.value} ({executor_info.mode.value}) at {executor_info.path}")
    except ExecutorNotFoundError as e:
        write_log(log_path, f"ERROR: {e.message}")
        write_log(log_path, "No code executor CLI found. Please install Claude Code CLI or Cursor CLI.")
        update_job_finished(job_id, JobStatus.FAILED, exit_code=1)
        transition_ticket_sync(
            ticket_id,
            TicketState.BLOCKED,
            reason=f"Execution failed: {e.message}",
            actor_id="execute_worker",
        )
        return {"job_id": job_id, "status": "failed", "error": e.message}

    # Check for feedback from previous revision (if this is a re-run after changes requested)
    feedback_bundle = get_feedback_bundle_for_ticket(ticket_id)
    if feedback_bundle:
        write_log(log_path, f"Found feedback from revision #{feedback_bundle.get('revision_number', '?')}")
        write_log(log_path, f"  - Summary: {feedback_bundle.get('summary', '')[:100]}...")
        write_log(log_path, f"  - Comments to address: {len(feedback_bundle.get('comments', []))}")
    else:
        write_log(log_path, "No previous revision feedback found (fresh execution)")

    # Check for queued follow-up prompt (from instant follow-up queue)
    from app.services.queued_message_service import queued_message_service
    followup_prompt = queued_message_service.get_followup_prompt(ticket_id)
    additional_context = None
    if followup_prompt:
        write_log(log_path, f"Found queued follow-up: {followup_prompt[:100]}...")
        additional_context = f"\n\n--- FOLLOW-UP REQUEST ---\n{followup_prompt}\n\nPlease address the above follow-up request while continuing work on this ticket."

    # Get related tickets context for better prompt
    related_tickets_context = _get_related_tickets_context_sync(ticket_id)
    if related_tickets_context:
        write_log(log_path, f"Found context: {len(related_tickets_context.get('completed_tickets', []))} completed tickets, {len(related_tickets_context.get('dependencies', []))} dependencies")

    # Build prompt bundle
    write_log(log_path, "Building prompt bundle...")
    from app.executors.spec import ExecutorVariant

    # Get variant from job (default to DEFAULT if not set)
    job_variant = ExecutorVariant.DEFAULT
    if job.variant:
        try:
            job_variant = ExecutorVariant(job.variant)
            write_log(log_path, f"Using execution variant: {job_variant.value}")
        except ValueError:
            write_log(log_path, f"WARNING: Invalid variant '{job.variant}', using default")

    prompt_builder = PromptBundleBuilder(worktree_path, job_id)
    prompt_file = prompt_builder.build_prompt(
        ticket_title=ticket.title,
        ticket_description=ticket.description,
        feedback_bundle=feedback_bundle,
        additional_context=additional_context,
        related_tickets_context=related_tickets_context,
        variant=job_variant,
    )
    write_log(log_path, f"Prompt bundle created at: {prompt_file}")

    # Get evidence directory
    evidence_dir = prompt_builder.get_evidence_dir()
    evidence_records: list[str] = []

    # Check for cancellation before execution
    if check_canceled(job_id):
        write_log(log_path, "Job canceled, stopping execution.")
        raise Ignore()

    # =========================================================================
    # INTERACTIVE EXECUTOR (Cursor) - Hand off to user immediately
    # =========================================================================
    if executor_info.is_interactive():
        write_log(log_path, f"Executor {executor_info.executor_type.value} is INTERACTIVE.")
        write_log(log_path, "Workspace and prompt bundle are ready.")
        write_log(log_path, "Transitioning to 'needs_human' for manual completion.")
        write_log(log_path, "")
        write_log(log_path, "=== INSTRUCTIONS FOR HUMAN ===")
        write_log(log_path, f"1. Open the worktree in your editor: {worktree_path}")
        write_log(log_path, f"2. Read the prompt: {prompt_file}")
        write_log(log_path, "3. Implement the requested changes")
        write_log(log_path, "4. Commit your changes")
        write_log(log_path, "5. Mark the ticket as ready for verification")
        write_log(log_path, "==============================")

        update_job_finished(job_id, JobStatus.SUCCEEDED, exit_code=0)
        transition_ticket_sync(
            ticket_id,
            TicketState.NEEDS_HUMAN,
            reason=f"Interactive executor ({executor_info.executor_type.value}): workspace ready, awaiting human completion",
            payload={
                "executor": executor_info.executor_type.value,
                "mode": executor_info.mode.value,
                "worktree": str(worktree_path),
                "prompt_file": str(prompt_file),
            },
            actor_id="execute_worker",
        )
        return {
            "job_id": job_id,
            "status": "needs_human",
            "worktree": str(worktree_path),
            "executor": executor_info.executor_type.value,
            "mode": executor_info.mode.value,
            "prompt_file": str(prompt_file),
        }

    # =========================================================================
    # HEADLESS EXECUTOR (Claude) - Run automatically
    # =========================================================================
    write_log(log_path, f"Running headless executor: {executor_info.executor_type.value}...")
    executor_evidence_id = str(uuid.uuid4())

    # Check for existing session to continue (session continuity)
    from app.services.agent_session_service import get_session_service
    session_service = get_session_service(worktree_path)
    existing_session = session_service.get_session(ticket_id)
    session_flag = None
    if existing_session:
        session_flag = session_service.get_continue_flag(ticket_id, executor_info.executor_type.value)
        if session_flag:
            write_log(log_path, f"Continuing from session: {existing_session.session_id} (execution #{existing_session.execution_count + 1})")

    # Get the command with YOLO mode and model selection
    # Returns (command, stdin_content) tuple - prompt piped via stdin to avoid ARG_MAX
    executor_command, executor_stdin = executor_info.get_apply_command(
        prompt_file,
        worktree_path,
        yolo_mode=yolo_enabled,
        model=execute_config.executor_model,
    )
    
    # Add session continuation flag if available
    if session_flag:
        executor_command = executor_command + session_flag.split()

    # Log command (without full prompt content)
    if yolo_enabled:
        write_log(log_path, f"Command: {executor_command[0]} --print --dangerously-skip-permissions <prompt>")
    else:
        write_log(log_path, f"Command: {executor_command[0]} --print <prompt>")
        write_log(log_path, "NOTE: Running in permissioned mode. Some operations may require approval.")

    # Track execution timing for metadata
    executor_start_time = time.time()

    # Enable log normalization for cursor-agent (outputs JSON streaming format)
    should_normalize = executor_info.executor_type == ExecutorType.CURSOR_AGENT
    
    executor_exit_code, executor_stdout_path, executor_stderr_path = run_executor_cli(
        command=executor_command,
        cwd=worktree_path,
        evidence_dir=evidence_dir,
        evidence_id=executor_evidence_id,
        repo_root=main_repo_path,
        timeout=execute_config.timeout,
        job_id=job_id,  # Enable real-time streaming
        normalize_logs=should_normalize,  # Parse cursor-agent JSON for nice display
        stdin_content=executor_stdin,  # Pipe prompt via stdin (ARG_MAX safety)
    )

    # Calculate execution duration
    executor_duration_ms = int((time.time() - executor_start_time) * 1000)

    # Create EXECUTOR_META evidence with structured metadata
    executor_meta_id = str(uuid.uuid4())
    executor_meta = {
        "exit_code": executor_exit_code,
        "duration_ms": executor_duration_ms,
        "executor_type": executor_info.executor_type.value,
        "mode": executor_info.mode.value,
        "command": f"{executor_command[0]} --print {'--dangerously-skip-permissions ' if yolo_enabled else ''}<prompt>",
        "yolo_enabled": yolo_enabled,
        "timeout_configured": execute_config.timeout,
    }
    executor_meta_path = evidence_dir / f"{executor_meta_id}.meta.json"
    executor_meta_path.write_text(json.dumps(executor_meta, indent=2))
    # Store relative path for secure DB storage
    executor_meta_relpath = str(executor_meta_path.relative_to(main_repo_path))
    create_evidence_record(
        ticket_id=ticket_id,
        job_id=job_id,
        command="executor_metadata",
        exit_code=executor_exit_code,
        stdout_path=executor_meta_relpath,
        stderr_path="",
        evidence_id=executor_meta_id,
        kind=EvidenceKind.EXECUTOR_META,
    )
    evidence_records.append(executor_meta_id)

    # Create evidence record for executor output (typed)
    create_evidence_record(
        ticket_id=ticket_id,
        job_id=job_id,
        command=f"{executor_command[0]} --print {'--dangerously-skip-permissions ' if yolo_enabled else ''}<prompt>",
        exit_code=executor_exit_code,
        stdout_path=executor_stdout_path,
        stderr_path=executor_stderr_path,
        evidence_id=executor_evidence_id,
        kind=EvidenceKind.EXECUTOR_STDOUT,
    )
    evidence_records.append(executor_evidence_id)

    # Extract and save session ID for continuity
    try:
        stdout_content = (main_repo_path / executor_stdout_path).read_text()
        new_session_id = session_service.extract_session_id_from_output(stdout_content)
        if new_session_id:
            session_service.save_session(
                session_id=new_session_id,
                ticket_id=ticket_id,
                agent_type=executor_info.executor_type.value,
            )
            write_log(log_path, f"Saved session ID for future continuity: {new_session_id[:16]}...")
    except Exception as e:
        logger.debug(f"Could not extract session ID: {e}")

    write_log(log_path, f"Executor completed in {executor_duration_ms}ms")
    if executor_exit_code == 0:
        write_log(log_path, "Executor CLI completed successfully (exit code: 0)")
    else:
        write_log(log_path, f"Executor CLI FAILED (exit code: {executor_exit_code})")
        # Read stderr for more details
        try:
            stderr_content = Path(executor_stderr_path).read_text()[:500]
            if stderr_content:
                write_log(log_path, f"Executor stderr: {stderr_content}")
        except Exception:
            pass

    # Capture git diff regardless of exit code (to see what changes were made)
    write_log(log_path, "Capturing git diff...")
    diff_stat_evidence_id = str(uuid.uuid4())
    diff_patch_evidence_id = str(uuid.uuid4())

    diff_exit_code, diff_stat_path, diff_patch_path, diff_stat, has_changes = capture_git_diff(
        cwd=worktree_path,
        evidence_dir=evidence_dir,
        evidence_id=diff_stat_evidence_id,  # Used for both files with different extensions
        repo_root=main_repo_path,
    )

    # Create typed evidence records for git diff
    create_evidence_record(
        ticket_id=ticket_id,
        job_id=job_id,
        command="git diff --stat",
        exit_code=diff_exit_code,
        stdout_path=diff_stat_path,
        stderr_path="",  # stderr captured in patch record
        evidence_id=diff_stat_evidence_id,
        kind=EvidenceKind.GIT_DIFF_STAT,
    )
    evidence_records.append(diff_stat_evidence_id)

    create_evidence_record(
        ticket_id=ticket_id,
        job_id=job_id,
        command="git diff",
        exit_code=diff_exit_code,
        stdout_path=diff_patch_path,
        stderr_path="",
        evidence_id=diff_patch_evidence_id,
        kind=EvidenceKind.GIT_DIFF_PATCH,
    )
    evidence_records.append(diff_patch_evidence_id)

    write_log(log_path, f"Git diff summary:\n{diff_stat}")
    write_log(log_path, f"Has changes: {has_changes}")

    # Check for cancellation before state transition
    if check_canceled(job_id):
        write_log(log_path, "Job canceled, stopping execution.")
        raise Ignore()

    # =========================================================================
    # STATE TRANSITIONS
    # =========================================================================

    # Case 1: Executor failed
    if executor_exit_code != 0:
        write_log(log_path, f"Execution FAILED with exit code {executor_exit_code}")
        write_log(log_path, "Transitioning ticket to 'blocked'")
        transition_ticket_sync(
            ticket_id,
            TicketState.BLOCKED,
            reason=f"Execution failed: {executor_info.executor_type.value} CLI exited with code {executor_exit_code}",
            payload={
                "executor": executor_info.executor_type.value,
                "exit_code": executor_exit_code,
                "evidence_ids": evidence_records,
                "diff_summary": diff_stat,
                "yolo_mode": yolo_enabled,
            },
            actor_id="execute_worker",
        )
        update_job_finished(job_id, JobStatus.FAILED, exit_code=executor_exit_code)
        return {
            "job_id": job_id,
            "status": "failed",
            "worktree": str(worktree_path),
            "executor": executor_info.executor_type.value,
            "exit_code": executor_exit_code,
            "evidence_ids": evidence_records,
            "diff_summary": diff_stat,
        }

    # Case 2: Executor succeeded but NO CHANGES produced
    if not has_changes:
        write_log(log_path, "Execution completed but NO CHANGES were produced.")
        write_log(log_path, "Analyzing why no code changes were made...")
        
        # Read executor stdout for analysis
        try:
            executor_stdout_content = (main_repo_path / executor_stdout_path).read_text()
        except Exception as e:
            write_log(log_path, f"Warning: Could not read executor output: {e}")
            executor_stdout_content = ""
        
        # Analyze why no changes were produced using LLM
        analysis = analyze_no_changes_reason(
            ticket_title=ticket.title,
            ticket_description=ticket.description,
            executor_stdout=executor_stdout_content,
            planner_config=planner_config,
        )
        
        write_log(log_path, f"Analysis result: {analysis.reason}")
        write_log(log_path, f"  - Needs code changes: {analysis.needs_code_changes}")
        write_log(log_path, f"  - Requires manual work: {analysis.requires_manual_work}")
        
        followup_ticket_id = None
        
        # Handle based on analysis result
        if analysis.requires_manual_work and analysis.manual_work_description:
            # Create a [Manual Work] follow-up ticket
            write_log(log_path, "Creating [Manual Work] follow-up ticket...")
            followup_ticket_id = create_manual_work_followup_sync(
                parent_ticket_id=ticket_id,
                parent_ticket_title=ticket.title,
                manual_work_description=analysis.manual_work_description,
                goal_id=goal_id,
                board_id=ticket.board_id,
            )
            if followup_ticket_id:
                write_log(log_path, f"Created follow-up ticket: {followup_ticket_id}")
            else:
                write_log(log_path, "Warning: Failed to create follow-up ticket")
            
            # Block the original ticket with reference to manual work
            reason = f"Requires manual work: {analysis.reason}"
            payload = {
                "executor": executor_info.executor_type.value,
                "evidence_ids": evidence_records,
                "diff_summary": diff_stat,
                "no_changes": True,
                "yolo_mode": yolo_enabled,
                "requires_manual_work": True,
                "manual_work_followup_id": followup_ticket_id,
                "analysis_reason": analysis.reason,
            }
            
        elif not analysis.needs_code_changes:
            # No changes needed - mark as blocked with skip_followup flag
            write_log(log_path, "No code changes needed. Blocking without follow-up.")
            reason = f"No changes required: {analysis.reason}"
            payload = {
                "executor": executor_info.executor_type.value,
                "evidence_ids": evidence_records,
                "diff_summary": diff_stat,
                "no_changes": True,
                "yolo_mode": yolo_enabled,
                "no_changes_needed": True,
                "skip_followup": True,  # Signal to planner to not create follow-ups
                "analysis_reason": analysis.reason,
            }
            
        else:
            # Needs investigation - use original behavior (planner may create follow-up)
            write_log(log_path, "Needs investigation. Blocking for review.")
            reason = f"Execution completed but no code changes were produced: {analysis.reason}"
            payload = {
                "executor": executor_info.executor_type.value,
                "evidence_ids": evidence_records,
                "diff_summary": diff_stat,
                "no_changes": True,
                "yolo_mode": yolo_enabled,
                "needs_investigation": True,
                "analysis_reason": analysis.reason,
            }
        
        write_log(log_path, f"Transitioning ticket to 'blocked' (reason: {reason[:100]}...)")
        transition_ticket_sync(
            ticket_id,
            TicketState.BLOCKED,
            reason=reason,
            payload=payload,
            actor_id="execute_worker",
        )
        update_job_finished(job_id, JobStatus.SUCCEEDED, exit_code=0)
        
        result_payload = {
            "job_id": job_id,
            "status": "no_changes",
            "worktree": str(worktree_path),
            "executor": executor_info.executor_type.value,
            "evidence_ids": evidence_records,
            "diff_summary": diff_stat,
            "analysis": {
                "reason": analysis.reason,
                "needs_code_changes": analysis.needs_code_changes,
                "requires_manual_work": analysis.requires_manual_work,
            },
        }
        if followup_ticket_id:
            result_payload["manual_work_followup_id"] = followup_ticket_id
            
        return result_payload

    # Case 3: Executor succeeded with changes → verifying
    write_log(log_path, "Execution completed successfully with changes!")

    # Create revision for this execution
    revision_id = create_revision_for_job(
        ticket_id=ticket_id,
        job_id=job_id,
        diff_stat_evidence_id=diff_stat_evidence_id,
        diff_patch_evidence_id=diff_patch_evidence_id,
    )
    if revision_id:
        write_log(log_path, f"Created revision {revision_id}")
    else:
        write_log(log_path, "WARNING: Failed to create revision record")

    write_log(log_path, "Transitioning ticket to 'verifying'")
    transition_ticket_sync(
        ticket_id,
        TicketState.VERIFYING,
        reason=f"Execution completed by {executor_info.executor_type.value} CLI with changes",
        payload={
            "executor": executor_info.executor_type.value,
            "evidence_ids": evidence_records,
            "diff_summary": diff_stat,
            "has_changes": True,
            "yolo_mode": yolo_enabled,
            "revision_id": revision_id,
        },
        actor_id="execute_worker",
    )
    update_job_finished(job_id, JobStatus.SUCCEEDED, exit_code=0)
    return {
        "job_id": job_id,
        "status": "succeeded",
        "worktree": str(worktree_path),
        "executor": executor_info.executor_type.value,
        "evidence_ids": evidence_records,
        "diff_summary": diff_stat,
        "has_changes": True,
        "revision_id": revision_id,
    }


@celery_app.task(bind=True, name="verify_ticket")
def verify_ticket_task(self, job_id: str) -> dict:
    """
    Verify task for a ticket.

    This task:
    1. Ensures a worktree exists for the ticket
    2. Loads verification commands from smartkanban.yaml
    3. Runs each command in the isolated worktree directory
    4. Creates Evidence records with captured stdout/stderr
    5. Transitions ticket based on verification outcome
    """
    # Get job and ticket info
    result = get_job_with_ticket(job_id)
    if not result:
        return {"job_id": job_id, "status": "failed", "error": "Job or ticket not found"}

    job, ticket = result
    goal_id = ticket.goal_id
    ticket_id = ticket.id

    # Check if ticket is already in a terminal/blocked state - skip verification if so
    if ticket.state in [TicketState.BLOCKED.value, TicketState.DONE.value, TicketState.ABANDONED.value]:
        import logging
        logging.getLogger(__name__).info(
            f"Skipping verification for job {job_id}: ticket {ticket_id} is already in {ticket.state} state"
        )
        update_job_finished(job_id, JobStatus.FAILED, exit_code=0)
        return {
            "job_id": job_id,
            "status": "skipped",
            "reason": f"Ticket already in {ticket.state} state",
            "ticket_id": ticket_id,
        }

    # Ensure workspace exists
    worktree_path, workspace_error = ensure_workspace_for_ticket(ticket_id, goal_id)

    # Get log path (use worktree if available, fallback otherwise)
    log_path, log_path_relative = get_log_path_for_job(job_id, worktree_path)

    write_log(log_path, "Starting verify task...")

    if workspace_error:
        write_log(log_path, f"WARNING: Could not create workspace: {workspace_error}")
        write_log(log_path, "Continuing with fallback execution...")
    else:
        write_log(log_path, f"Workspace ready at: {worktree_path}")

    # Mark as running
    if not update_job_started(job_id, log_path_relative):
        write_log(log_path, "Job was canceled or not found, aborting.")
        raise Ignore()

    # Check for cancellation
    if check_canceled(job_id):
        write_log(log_path, "Job canceled, stopping execution.")
        raise Ignore()

    # Load configuration from the worktree (where smartkanban.yaml should be)
    # Apply board-level overrides if present
    # Disable cache to ensure we get the latest config
    config_service = ConfigService(worktree_path)

    # Get board config for overrides
    board_config = None
    if ticket.board_id:
        with get_sync_db() as db:
            from app.models.board import Board
            board = db.query(Board).filter(Board.id == ticket.board_id).first()
            if board and board.config:
                board_config = board.config

    # Load config with board overrides applied
    config = config_service.load_config_with_board_overrides(
        board_config=board_config,
        use_cache=False
    )
    verify_config = config.verify_config
    verify_commands = verify_config.commands

    # Get repo root for relative path computation
    repo_root = config_service.get_repo_root()

    write_log(log_path, f"Loaded {len(verify_commands)} verification command(s)")
    write_log(log_path, "On success: transition to 'needs_human' (requires user approval to move to done)")

    if not verify_commands:
        write_log(log_path, "No verification commands configured, skipping verification.")
        # No commands = success, always transition to needs_human for review
        write_log(log_path, "Transitioning ticket to 'needs_human' for review")
        transition_ticket_sync(ticket_id, TicketState.NEEDS_HUMAN, reason="Verification passed (no commands configured), awaiting human approval")
        update_job_finished(job_id, JobStatus.SUCCEEDED, exit_code=0)
        return {"job_id": job_id, "status": "succeeded", "worktree": str(worktree_path) if worktree_path else None}

    # Get evidence directory (with validation against repo_root)
    evidence_dir = get_evidence_dir(worktree_path, job_id, repo_root=repo_root)

    # Run verification commands with timing
    verify_start_time = time.time()
    all_succeeded = True
    failed_commands: list[dict] = []
    command_results: list[dict] = []
    evidence_records: list[str] = []

    for i, command in enumerate(verify_commands):
        # Check for cancellation before each command
        if check_canceled(job_id):
            write_log(log_path, "Job canceled, stopping execution.")
            raise Ignore()

        write_log(log_path, f"Running command {i + 1}/{len(verify_commands)}: {command}")

        # Generate evidence ID
        evidence_id = str(uuid.uuid4())
        cmd_start_time = time.time()

        # Run the command (returns relative paths for secure DB storage)
        exit_code, stdout_path, stderr_path = run_verification_command(
            command=command,
            cwd=worktree_path,
            evidence_dir=evidence_dir,
            evidence_id=evidence_id,
            repo_root=repo_root,
            timeout=300,
        )

        cmd_duration_ms = int((time.time() - cmd_start_time) * 1000)

        # Track command result for metadata
        command_results.append({
            "command": command,
            "exit_code": exit_code,
            "duration_ms": cmd_duration_ms,
            "evidence_id": evidence_id,
        })

        # Create evidence record (typed as verification output)
        create_evidence_record(
            ticket_id=ticket_id,
            job_id=job_id,
            command=command,
            exit_code=exit_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            evidence_id=evidence_id,
            kind=EvidenceKind.VERIFY_STDOUT,
        )
        evidence_records.append(evidence_id)

        if exit_code == 0:
            write_log(log_path, f"Command succeeded (exit code: 0, {cmd_duration_ms}ms)")
        else:
            write_log(log_path, f"Command FAILED (exit code: {exit_code}, {cmd_duration_ms}ms)")
            all_succeeded = False
            failed_commands.append({
                "command": command,
                "exit_code": exit_code,
                "evidence_id": evidence_id,
            })
            # Stop on first failure
            write_log(log_path, "Stopping verification due to failure.")
            break

    # Calculate total verification duration
    verify_duration_ms = int((time.time() - verify_start_time) * 1000)

    # Create VERIFY_META evidence with structured metadata
    verify_meta_id = str(uuid.uuid4())
    verify_meta = {
        "total_duration_ms": verify_duration_ms,
        "commands_configured": verify_commands,
        "commands_run": len(command_results),
        "all_succeeded": all_succeeded,
        "results": command_results,
    }
    verify_meta_path = evidence_dir / f"{verify_meta_id}.meta.json"
    verify_meta_path.write_text(json.dumps(verify_meta, indent=2))
    # Store relative path for secure DB storage
    verify_meta_relpath = str(verify_meta_path.relative_to(repo_root))
    create_evidence_record(
        ticket_id=ticket_id,
        job_id=job_id,
        command="verify_metadata",
        exit_code=0 if all_succeeded else 1,
        stdout_path=verify_meta_relpath,
        stderr_path="",
        evidence_id=verify_meta_id,
        kind=EvidenceKind.VERIFY_META,
    )
    evidence_records.append(verify_meta_id)

    write_log(log_path, f"Total verification time: {verify_duration_ms}ms")

    # Transition ticket based on outcome
    if all_succeeded:
        write_log(log_path, "All verification commands passed!")
        # Always transition to needs_human for review - user must explicitly approve to move to done
        write_log(log_path, "Transitioning ticket to 'needs_human' for review")
        transition_ticket_sync(
            ticket_id,
            TicketState.NEEDS_HUMAN,
            reason=f"Verification passed: {len(verify_commands)} command(s) succeeded, awaiting human approval",
            payload={"evidence_ids": evidence_records, "duration_ms": verify_duration_ms},
        )
        update_job_finished(job_id, JobStatus.SUCCEEDED, exit_code=0)
        return {
            "job_id": job_id,
            "status": "succeeded",
            "worktree": str(worktree_path) if worktree_path else None,
            "evidence_ids": evidence_records,
        }
    else:
        # Verification failed
        failure_summary = "; ".join([f"'{fc['command']}' failed with exit code {fc['exit_code']}" for fc in failed_commands])
        write_log(log_path, f"Verification FAILED: {failure_summary}")
        write_log(log_path, "Transitioning ticket to 'blocked'")

        transition_ticket_sync(
            ticket_id,
            TicketState.BLOCKED,
            reason=f"Verification failed: {failure_summary}",
            payload={
                "evidence_ids": evidence_records,
                "failed_commands": failed_commands,
            },
        )

        # Use the exit code of the first failed command
        final_exit_code = failed_commands[0]["exit_code"] if failed_commands else 1
        update_job_finished(job_id, JobStatus.FAILED, exit_code=final_exit_code)

        return {
            "job_id": job_id,
            "status": "failed",
            "worktree": str(worktree_path) if worktree_path else None,
            "evidence_ids": evidence_records,
            "failed_commands": failed_commands,
        }


@celery_app.task(bind=True, name="job_watchdog")
def job_watchdog_task(self) -> dict:
    """
    Periodic task to monitor and recover stuck jobs.

    This task runs every minute via Celery Beat and checks for:
    1. RUNNING jobs with stale heartbeat (no update in 2 minutes)
    2. RUNNING jobs that exceeded their timeout
    3. QUEUED jobs stuck in queue for over 10 minutes

    For each stuck job, it marks the job as FAILED and transitions
    the associated ticket to BLOCKED.
    """
    from app.services.job_watchdog_service import run_job_watchdog

    result = run_job_watchdog()

    return {
        "stale_jobs_recovered": result.stale_jobs_recovered,
        "timed_out_jobs_recovered": result.timed_out_jobs_recovered,
        "stuck_queued_jobs_failed": result.stuck_queued_jobs_failed,
        "tickets_blocked": result.tickets_blocked,
        "details": result.details,
    }


@celery_app.task(bind=True, name="planner_tick")
def planner_tick_task(self) -> dict:
    """
    Periodic task to run a planner tick and pick up next tickets.

    This task runs every 5 seconds via Celery Beat and:
    1. Checks if any PLANNED tickets are ready to execute
    2. If no ticket is currently EXECUTING/VERIFYING, queues the next one
    3. Handles follow-ups for BLOCKED tickets (if LLM configured)

    This ensures tickets automatically flow through the queue without
    requiring the /planner/start HTTP request to stay connected.
    """
    from app.services.planner_tick_sync import run_planner_tick_sync, PlannerLockError

    try:
        result = run_planner_tick_sync()
        return {
            "status": "success",
            "executed": result.get("executed", 0),
            "followups_created": result.get("followups_created", 0),
            "reflections_added": result.get("reflections_added", 0),
        }
    except PlannerLockError:
        # Lock conflict - another tick is running, this is fine
        return {"status": "skipped", "reason": "Another tick in progress"}
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Planner tick failed: {e}")
        return {"status": "error", "error": str(e)[:200]}


@celery_app.task(bind=True, name="resume_ticket")
def resume_ticket_task(self, job_id: str) -> dict:
    """
    Resume a ticket after human completion (interactive executor flow).

    This task is used when a ticket was transitioned to 'needs_human' by an
    interactive executor (like Cursor). The human has made their changes, and
    now wants to continue the workflow.

    This task:
    1. Validates the ticket is in 'needs_human' state
    2. Captures the git diff as evidence
    3. Checks if there are any changes
    4. Transitions to 'verifying' if changes exist, or 'blocked' if no changes
    """
    # Get job and ticket info
    result = get_job_with_ticket(job_id)
    if not result:
        return {"job_id": job_id, "status": "failed", "error": "Job or ticket not found"}

    job, ticket = result
    goal_id = ticket.goal_id
    ticket_id = ticket.id

    # Ensure workspace exists
    worktree_path, workspace_error = ensure_workspace_for_ticket(ticket_id, goal_id)

    # Get log path (use worktree if available, fallback otherwise)
    log_path, log_path_relative = get_log_path_for_job(job_id, worktree_path)

    write_log(log_path, "Starting resume task...")

    # Workspace is required
    if workspace_error or not worktree_path:
        write_log(log_path, f"ERROR: Could not find workspace: {workspace_error or 'Unknown error'}")
        update_job_started(job_id, log_path_relative)
        update_job_finished(job_id, JobStatus.FAILED, exit_code=1)
        return {"job_id": job_id, "status": "failed", "error": workspace_error}

    write_log(log_path, f"Workspace found at: {worktree_path}")

    # Mark as running
    if not update_job_started(job_id, log_path_relative):
        write_log(log_path, "Job was canceled or not found, aborting.")
        raise Ignore()

    # Validate ticket is in needs_human state
    if ticket.state != TicketState.NEEDS_HUMAN.value:
        write_log(log_path, f"ERROR: Ticket is in '{ticket.state}' state, expected 'needs_human'")
        write_log(log_path, "Resume can only be called on tickets in 'needs_human' state.")
        update_job_finished(job_id, JobStatus.FAILED, exit_code=1)
        return {
            "job_id": job_id,
            "status": "failed",
            "error": f"Ticket must be in 'needs_human' state to resume, got '{ticket.state}'",
        }

    # Get evidence directory
    evidence_dir = worktree_path / ".smartkanban" / "jobs" / job_id / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_records: list[str] = []

    # Capture git diff
    write_log(log_path, "Capturing git diff...")
    diff_stat_evidence_id = str(uuid.uuid4())
    diff_patch_evidence_id = str(uuid.uuid4())

    # Get repo root for relative path computation
    repo_root = WorkspaceService.get_repo_path()

    diff_exit_code, diff_stat_path, diff_patch_path, diff_stat, has_changes = capture_git_diff(
        cwd=worktree_path,
        evidence_dir=evidence_dir,
        evidence_id=diff_stat_evidence_id,
        repo_root=repo_root,
    )

    # Create typed evidence records for git diff
    create_evidence_record(
        ticket_id=ticket_id,
        job_id=job_id,
        command="git diff --stat",
        exit_code=diff_exit_code,
        stdout_path=diff_stat_path,
        stderr_path="",
        evidence_id=diff_stat_evidence_id,
        kind=EvidenceKind.GIT_DIFF_STAT,
    )
    evidence_records.append(diff_stat_evidence_id)

    create_evidence_record(
        ticket_id=ticket_id,
        job_id=job_id,
        command="git diff",
        exit_code=diff_exit_code,
        stdout_path=diff_patch_path,
        stderr_path="",
        evidence_id=diff_patch_evidence_id,
        kind=EvidenceKind.GIT_DIFF_PATCH,
    )
    evidence_records.append(diff_patch_evidence_id)

    write_log(log_path, f"Git diff summary:\n{diff_stat}")
    write_log(log_path, f"Has changes: {has_changes}")

    # Determine outcome
    if not has_changes:
        write_log(log_path, "No changes detected in worktree.")
        write_log(log_path, "Transitioning to 'blocked' (reason: no changes)")
        transition_ticket_sync(
            ticket_id,
            TicketState.BLOCKED,
            reason="Resume completed but no code changes were found in worktree",
            payload={
                "evidence_ids": evidence_records,
                "diff_summary": diff_stat,
                "no_changes": True,
            },
            actor_id="resume_worker",
        )
        update_job_finished(job_id, JobStatus.SUCCEEDED, exit_code=0)
        return {
            "job_id": job_id,
            "status": "no_changes",
            "worktree": str(worktree_path),
            "evidence_ids": evidence_records,
        }

    # Changes exist - transition to verifying
    write_log(log_path, "Changes detected! Transitioning to 'verifying'")
    transition_ticket_sync(
        ticket_id,
        TicketState.VERIFYING,
        reason="Human completed changes, ready for verification",
        payload={
            "evidence_ids": evidence_records,
            "diff_summary": diff_stat,
            "resumed_from_interactive": True,
        },
        actor_id="resume_worker",
    )
    update_job_finished(job_id, JobStatus.SUCCEEDED, exit_code=0)

    write_log(log_path, "Resume completed successfully!")
    return {
        "job_id": job_id,
        "status": "succeeded",
        "worktree": str(worktree_path),
        "evidence_ids": evidence_records,
        "diff_summary": diff_stat,
    }


@celery_app.task(name="poll_pr_statuses")
def poll_pr_statuses():
    """
    Periodic task to poll GitHub PR statuses for tickets.
    
    This task runs every 5 minutes and:
    1. Finds tickets with open PRs
    2. Checks PR status on GitHub
    3. Auto-transitions tickets if PR is merged
    """
    from pathlib import Path
    from datetime import datetime
    from app.models.workspace import Workspace
    from app.services.github_service import get_github_service
    from app.state_machine import TicketState
    import subprocess
    
    # First, collect ticket info without holding DB connection during network calls
    tickets_to_check = []
    
    with get_sync_db() as db:
        # Find tickets with open PRs
        tickets_with_prs = (
            db.query(Ticket)
            .filter(
                Ticket.pr_number.isnot(None),
                Ticket.pr_state.in_(["OPEN", "CLOSED"]),
            )
            .all()
        )
        
        if not tickets_with_prs:
            return {"message": "No PRs to poll", "checked": 0}
        
        for ticket in tickets_with_prs:
            # Get workspace for repo path
            workspace = (
                db.query(Workspace)
                .filter(Workspace.ticket_id == ticket.id)
                .first()
            )
            
            if workspace and workspace.worktree_path:
                repo_path = Path(workspace.worktree_path)
                if repo_path.exists():
                    tickets_to_check.append({
                        "ticket_id": ticket.id,
                        "pr_number": ticket.pr_number,
                        "pr_state": ticket.pr_state,
                        "pr_merged_at": ticket.pr_merged_at,
                        "repo_path": str(repo_path),
                    })
    
    if not tickets_to_check:
        return {"message": "No valid tickets to poll", "checked": 0}
    
    github_service = get_github_service()
    
    # Check if GitHub CLI is available
    if not github_service.is_available():
        return {
            "message": "GitHub CLI not available, skipping poll",
            "checked": 0,
        }
    
    updated_count = 0
    merged_count = 0
    errors = []
    
    # Poll GitHub outside of DB session to avoid blocking
    for ticket_info in tickets_to_check:
        try:
            repo_path = Path(ticket_info["repo_path"])
            pr_number = ticket_info["pr_number"]
            
            # Use synchronous subprocess call with timeout instead of asyncio.run()
            result = subprocess.run(
                ["gh", "pr", "view", str(pr_number), "--json", "state,merged"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,  # 30 second timeout per PR check
            )
            
            if result.returncode != 0:
                continue
            
            pr_details = json.loads(result.stdout)
            ticket_info["new_state"] = pr_details.get("state", "OPEN")
            ticket_info["merged"] = pr_details.get("merged", False)
            
        except subprocess.TimeoutExpired:
            errors.append(f"Timeout checking PR for ticket {ticket_info['ticket_id']}")
            continue
        except Exception as e:
            errors.append(f"Error polling PR for ticket {ticket_info['ticket_id']}: {e}")
            continue
    
    # Now update DB with results (quick operation)
    with get_sync_db() as db:
        for ticket_info in tickets_to_check:
            if "new_state" not in ticket_info:
                continue  # Skip if we didn't get PR details
            
            try:
                ticket = db.query(Ticket).filter(Ticket.id == ticket_info["ticket_id"]).first()
                if not ticket:
                    continue
                
                old_state = ticket.pr_state
                ticket.pr_state = ticket_info["new_state"]
                
                if ticket_info.get("merged") and not ticket.pr_merged_at:
                    ticket.pr_merged_at = datetime.now()
                    merged_count += 1
                
                # Auto-transition ticket if PR was merged
                if ticket_info.get("merged") and old_state != "MERGED":
                    ticket.state = TicketState.DONE.value
                    ticket.pr_state = "MERGED"
                    
                    # Create event
                    event = TicketEvent(
                        ticket_id=ticket.id,
                        event_type=EventType.TRANSITIONED.value,
                        from_state=old_state or "REVIEW",
                        to_state=TicketState.DONE.value,
                        actor_type=ActorType.SYSTEM.value,
                        actor_id="poll_pr_statuses",
                        reason=f"PR #{ticket.pr_number} was merged",
                    )
                    db.add(event)
                
                updated_count += 1
                
            except Exception as e:
                errors.append(f"Error updating ticket {ticket_info['ticket_id']}: {e}")
                continue
    
    return {
        "message": "PR polling completed",
        "checked": len(tickets_to_check),
        "updated": updated_count,
        "merged": merged_count,
        "errors": errors[:10] if errors else [],  # Limit error list
    }
