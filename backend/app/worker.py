"""Celery worker tasks for Smart Kanban."""

import json
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from celery.exceptions import Ignore
from sqlalchemy.orm import selectinload

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
from app.services.executor_service import ExecutorService, ExecutorMode, PromptBundleBuilder
from app.services.workspace_service import WorkspaceService
from app.services.worktree_validator import WorktreeValidator
from app.state_machine import ActorType, EventType, TicketState

# Fallback logs directory (used when worktree is not available)
FALLBACK_LOGS_DIR = Path(__file__).parent.parent / "logs"


def ensure_fallback_logs_dir() -> None:
    """Ensure the fallback logs directory exists."""
    FALLBACK_LOGS_DIR.mkdir(exist_ok=True)


def get_fallback_log_path(job_id: str) -> Path:
    """Get the fallback log file path for a job."""
    return FALLBACK_LOGS_DIR / f"{job_id}.log"


def write_log(log_path: Path, message: str) -> None:
    """Write a timestamped message to the log file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat()
    with open(log_path, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


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


def update_job_started(job_id: str, log_path: str) -> bool:
    """Mark job as running. Returns False if job was canceled."""
    with get_sync_db() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return False

        # Check if job was canceled before it started
        if job.status == JobStatus.CANCELED.value:
            return False

        job.status = JobStatus.RUNNING.value
        job.started_at = datetime.now(UTC)
        job.log_path = log_path
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


def get_evidence_dir(worktree_path: Path | None, job_id: str) -> Path:
    """Get the directory for storing evidence files."""
    if worktree_path:
        evidence_dir = worktree_path / ".smartkanban" / "evidence" / job_id
    else:
        evidence_dir = FALLBACK_LOGS_DIR / "evidence" / job_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    return evidence_dir


def run_verification_command(
    command: str,
    cwd: Path | None,
    evidence_dir: Path,
    evidence_id: str,
    timeout: int = 300,
) -> tuple[int, str, str]:
    """
    Run a verification command and capture output.

    Args:
        command: The shell command to run
        cwd: Working directory for the command
        evidence_dir: Directory to store stdout/stderr files
        evidence_id: UUID for naming evidence files
        timeout: Command timeout in seconds

    Returns:
        Tuple of (exit_code, stdout_path, stderr_path)
    """
    stdout_path = evidence_dir / f"{evidence_id}.stdout"
    stderr_path = evidence_dir / f"{evidence_id}.stderr"

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Write stdout/stderr to files
        stdout_path.write_text(result.stdout or "")
        stderr_path.write_text(result.stderr or "")

        return result.returncode, str(stdout_path), str(stderr_path)

    except subprocess.TimeoutExpired as e:
        # Write partial output if available
        stdout_path.write_text(e.stdout.decode() if e.stdout else "Command timed out")
        stderr_path.write_text(e.stderr.decode() if e.stderr else "")
        return -1, str(stdout_path), str(stderr_path)

    except Exception as e:
        stdout_path.write_text("")
        stderr_path.write_text(f"Error running command: {str(e)}")
        return -1, str(stdout_path), str(stderr_path)


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


def transition_ticket_sync(
    ticket_id: str,
    to_state: TicketState,
    reason: str | None = None,
    payload: dict | None = None,
    actor_id: str = "worker",
) -> None:
    """
    Transition a ticket to a new state synchronously.

    Args:
        ticket_id: The UUID of the ticket
        to_state: The target state
        reason: Optional reason for the transition
        payload: Optional payload for the event
        actor_id: The ID of the actor performing the transition
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


def run_executor_cli(
    command: list[str],
    cwd: Path,
    evidence_dir: Path,
    evidence_id: str,
    timeout: int = 600,
) -> tuple[int, str, str]:
    """
    Run the executor CLI and capture output.

    Args:
        command: The CLI command to run as a list of arguments
        cwd: Working directory for the command
        evidence_dir: Directory to store stdout/stderr files
        evidence_id: UUID for naming evidence files
        timeout: Command timeout in seconds

    Returns:
        Tuple of (exit_code, stdout_path, stderr_path)
    """
    stdout_path = evidence_dir / f"{evidence_id}.stdout"
    stderr_path = evidence_dir / f"{evidence_id}.stderr"

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Write stdout/stderr to files
        stdout_path.write_text(result.stdout or "")
        stderr_path.write_text(result.stderr or "")

        return result.returncode, str(stdout_path), str(stderr_path)

    except subprocess.TimeoutExpired as e:
        # Write partial output if available
        stdout_path.write_text(e.stdout.decode() if e.stdout else f"Command timed out after {timeout} seconds")
        stderr_path.write_text(e.stderr.decode() if e.stderr else "")
        return -1, str(stdout_path), str(stderr_path)

    except FileNotFoundError as e:
        stdout_path.write_text("")
        stderr_path.write_text(f"Executor CLI not found: {str(e)}")
        return -1, str(stdout_path), str(stderr_path)

    except Exception as e:
        stdout_path.write_text("")
        stderr_path.write_text(f"Error running executor CLI: {str(e)}")
        return -1, str(stdout_path), str(stderr_path)


def capture_git_diff(
    cwd: Path,
    evidence_dir: Path,
    evidence_id: str,
) -> tuple[int, str, str, str, bool]:
    """
    Capture git diff output for changes made in the worktree.

    Args:
        cwd: Working directory (worktree path)
        evidence_dir: Directory to store diff files
        evidence_id: UUID for naming evidence files

    Returns:
        Tuple of (exit_code, diff_stat_path, diff_patch_path, diff_stat_text, has_changes)
        has_changes is True if there are uncommitted changes in the worktree.
    """
    diff_stat_path = evidence_dir / f"{evidence_id}.diff_stat"
    diff_patch_path = evidence_dir / f"{evidence_id}.diff_patch"
    stderr_path = evidence_dir / f"{evidence_id}.stderr"

    diff_stat = ""
    has_changes = False

    try:
        # First get the diff stat for summary
        stat_result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        diff_stat = stat_result.stdout.strip() if stat_result.stdout else ""
        diff_stat_path.write_text(diff_stat or "(no changes)")

        # Then get the full patch
        patch_result = subprocess.run(
            ["git", "diff"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        diff_patch = patch_result.stdout.strip() if patch_result.stdout else ""
        diff_patch_path.write_text(diff_patch or "(no changes)")

        # Determine if there are actual changes
        has_changes = bool(diff_patch)

        # Combine stderr from both commands
        combined_stderr = ""
        if stat_result.stderr:
            combined_stderr += f"git diff --stat stderr:\n{stat_result.stderr}\n"
        if patch_result.stderr:
            combined_stderr += f"git diff stderr:\n{patch_result.stderr}\n"
        stderr_path.write_text(combined_stderr)

        return 0, str(diff_stat_path), str(diff_patch_path), diff_stat or "(no changes)", has_changes

    except subprocess.TimeoutExpired:
        diff_stat_path.write_text("Git diff timed out")
        diff_patch_path.write_text("")
        stderr_path.write_text("Git diff command timed out after 60 seconds")
        return -1, str(diff_stat_path), str(diff_patch_path), "(timeout)", False

    except Exception as e:
        diff_stat_path.write_text("")
        diff_patch_path.write_text("")
        stderr_path.write_text(f"Error running git diff: {str(e)}")
        return -1, str(diff_stat_path), str(diff_patch_path), "(error)", False


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

    # Check for cancellation
    if check_canceled(job_id):
        write_log(log_path, "Job canceled, stopping execution.")
        raise Ignore()

    # Load configuration from the worktree (where smartkanban.yaml should be)
    # Disable cache to ensure we get the latest config
    config_service = ConfigService(worktree_path)
    config = config_service.load_config(use_cache=False)
    execute_config = config.execute_config

    # Get main repo path for validation
    main_repo_path = config.project.get_absolute_repo_root(worktree_path)

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
    yolo_status = execute_config.check_yolo_status(str(worktree_path.resolve()))
    write_log(log_path, f"Execute config: timeout={execute_config.timeout}s, preferred_executor={execute_config.preferred_executor}")

    if yolo_status == YoloStatus.REFUSED:
        refusal_reason = execute_config.get_yolo_refusal_reason()
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
        executor_info = ExecutorService.detect_executor(preferred=execute_config.preferred_executor)
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

    # Build prompt bundle
    write_log(log_path, "Building prompt bundle...")
    prompt_builder = PromptBundleBuilder(worktree_path, job_id)
    prompt_file = prompt_builder.build_prompt(
        ticket_title=ticket.title,
        ticket_description=ticket.description,
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

    # Get the command with YOLO mode if allowed
    executor_command = executor_info.get_apply_command(
        prompt_file,
        worktree_path,
        yolo_mode=yolo_enabled,
    )

    # Log command (without full prompt content)
    if yolo_enabled:
        write_log(log_path, f"Command: {executor_command[0]} --print --dangerously-skip-permissions <prompt>")
    else:
        write_log(log_path, f"Command: {executor_command[0]} --print <prompt>")
        write_log(log_path, "NOTE: Running in permissioned mode. Some operations may require approval.")

    # Track execution timing for metadata
    executor_start_time = time.time()

    executor_exit_code, executor_stdout_path, executor_stderr_path = run_executor_cli(
        command=executor_command,
        cwd=worktree_path,
        evidence_dir=evidence_dir,
        evidence_id=executor_evidence_id,
        timeout=execute_config.timeout,
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
    create_evidence_record(
        ticket_id=ticket_id,
        job_id=job_id,
        command="executor_metadata",
        exit_code=executor_exit_code,
        stdout_path=str(executor_meta_path),
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
        write_log(log_path, "Transitioning ticket to 'blocked' (reason: no diff)")
        transition_ticket_sync(
            ticket_id,
            TicketState.BLOCKED,
            reason="Execution completed but no code changes were produced",
            payload={
                "executor": executor_info.executor_type.value,
                "evidence_ids": evidence_records,
                "diff_summary": diff_stat,
                "no_changes": True,
                "yolo_mode": yolo_enabled,
            },
            actor_id="execute_worker",
        )
        update_job_finished(job_id, JobStatus.SUCCEEDED, exit_code=0)
        return {
            "job_id": job_id,
            "status": "no_changes",
            "worktree": str(worktree_path),
            "executor": executor_info.executor_type.value,
            "evidence_ids": evidence_records,
            "diff_summary": diff_stat,
        }

    # Case 3: Executor succeeded with changes → verifying
    write_log(log_path, "Execution completed successfully with changes!")
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
    # Disable cache to ensure we get the latest config
    config_service = ConfigService(worktree_path)
    config = config_service.load_config(use_cache=False)
    verify_config = config.verify_config
    verify_commands = verify_config.commands
    on_success_state = verify_config.on_success  # "needs_human" or "done"

    write_log(log_path, f"Loaded {len(verify_commands)} verification command(s)")
    write_log(log_path, f"On success: transition to '{on_success_state}'")

    if not verify_commands:
        write_log(log_path, "No verification commands configured, skipping verification.")
        # No commands = success, transition based on policy
        if on_success_state == "done":
            write_log(log_path, "Transitioning ticket to 'done'")
            transition_ticket_sync(ticket_id, TicketState.DONE, reason="Verification passed (no commands configured)")
        else:
            write_log(log_path, "Transitioning ticket to 'needs_human' for review")
            transition_ticket_sync(ticket_id, TicketState.NEEDS_HUMAN, reason="Verification passed (no commands configured)")
        update_job_finished(job_id, JobStatus.SUCCEEDED, exit_code=0)
        return {"job_id": job_id, "status": "succeeded", "worktree": str(worktree_path) if worktree_path else None}

    # Get evidence directory
    evidence_dir = get_evidence_dir(worktree_path, job_id)

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

        # Run the command
        exit_code, stdout_path, stderr_path = run_verification_command(
            command=command,
            cwd=worktree_path,
            evidence_dir=evidence_dir,
            evidence_id=evidence_id,
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
        "on_success_configured": on_success_state,
    }
    verify_meta_path = evidence_dir / f"{verify_meta_id}.meta.json"
    verify_meta_path.write_text(json.dumps(verify_meta, indent=2))
    create_evidence_record(
        ticket_id=ticket_id,
        job_id=job_id,
        command="verify_metadata",
        exit_code=0 if all_succeeded else 1,
        stdout_path=str(verify_meta_path),
        stderr_path="",
        evidence_id=verify_meta_id,
        kind=EvidenceKind.VERIFY_META,
    )
    evidence_records.append(verify_meta_id)

    write_log(log_path, f"Total verification time: {verify_duration_ms}ms")

    # Transition ticket based on outcome
    if all_succeeded:
        write_log(log_path, "All verification commands passed!")
        if on_success_state == "done":
            write_log(log_path, "Transitioning ticket to 'done'")
            transition_ticket_sync(
                ticket_id,
                TicketState.DONE,
                reason=f"Verification passed: {len(verify_commands)} command(s) succeeded",
                payload={"evidence_ids": evidence_records, "duration_ms": verify_duration_ms},
            )
        else:
            write_log(log_path, "Transitioning ticket to 'needs_human' for review")
            transition_ticket_sync(
                ticket_id,
                TicketState.NEEDS_HUMAN,
                reason=f"Verification passed: {len(verify_commands)} command(s) succeeded, awaiting human review",
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

    diff_exit_code, diff_stat_path, diff_patch_path, diff_stat, has_changes = capture_git_diff(
        cwd=worktree_path,
        evidence_dir=evidence_dir,
        evidence_id=diff_stat_evidence_id,
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
