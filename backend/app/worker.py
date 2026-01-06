"""Celery worker tasks for Smart Kanban."""

import json
import subprocess
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
from app.services.config_service import ConfigService
from app.services.executor_service import ExecutorService, PromptBundleBuilder
from app.services.workspace_service import WorkspaceService
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
) -> Evidence:
    """Create an Evidence record in the database."""
    with get_sync_db() as db:
        evidence = Evidence(
            id=evidence_id,
            ticket_id=ticket_id,
            job_id=job_id,
            kind=EvidenceKind.COMMAND_LOG.value,
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
) -> tuple[int, str, str, str]:
    """
    Capture git diff output for changes made in the worktree.

    Args:
        cwd: Working directory (worktree path)
        evidence_dir: Directory to store diff files
        evidence_id: UUID for naming evidence files

    Returns:
        Tuple of (exit_code, stdout_path, stderr_path, diff_stat)
    """
    diff_stat_path = evidence_dir / f"{evidence_id}.diff_stat"
    diff_patch_path = evidence_dir / f"{evidence_id}.diff_patch"
    stderr_path = evidence_dir / f"{evidence_id}.stderr"

    diff_stat = ""

    try:
        # First get the diff stat for summary
        stat_result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        diff_stat = stat_result.stdout or "(no changes)"
        diff_stat_path.write_text(diff_stat)

        # Then get the full patch
        patch_result = subprocess.run(
            ["git", "diff"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        diff_patch_path.write_text(patch_result.stdout or "(no changes)")

        # Combine stderr from both commands
        combined_stderr = ""
        if stat_result.stderr:
            combined_stderr += f"git diff --stat stderr:\n{stat_result.stderr}\n"
        if patch_result.stderr:
            combined_stderr += f"git diff stderr:\n{patch_result.stderr}\n"
        stderr_path.write_text(combined_stderr)

        # Return the patch path as stdout for evidence storage
        return 0, str(diff_patch_path), str(stderr_path), diff_stat

    except subprocess.TimeoutExpired:
        diff_stat_path.write_text("Git diff timed out")
        diff_patch_path.write_text("")
        stderr_path.write_text("Git diff command timed out after 60 seconds")
        return -1, str(diff_patch_path), str(stderr_path), "(timeout)"

    except Exception as e:
        diff_stat_path.write_text("")
        diff_patch_path.write_text("")
        stderr_path.write_text(f"Error running git diff: {str(e)}")
        return -1, str(diff_patch_path), str(stderr_path), "(error)"


@celery_app.task(bind=True, name="execute_ticket")
def execute_ticket_task(self, job_id: str) -> dict:
    """
    Execute task for a ticket using Cursor CLI or Claude Code CLI.

    This task:
    1. Ensures a worktree exists for the ticket
    2. Detects available executor CLI (Cursor or Claude fallback)
    3. Builds a prompt bundle with ticket details
    4. Invokes the executor CLI in the worktree directory
    5. Captures execution logs and git diff
    6. Creates Evidence records for logs and diff
    7. Transitions ticket to 'verifying' on success or 'blocked' on failure
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

    # Load configuration
    config_service = ConfigService(worktree_path.parent.parent if worktree_path else None)
    execute_config = config_service.get_execute_config()
    write_log(log_path, f"Execute config: timeout={execute_config.timeout}s, preferred_executor={execute_config.preferred_executor}")

    # Detect available executor CLI
    try:
        executor_info = ExecutorService.detect_executor(preferred=execute_config.preferred_executor)
        write_log(log_path, f"Found executor: {executor_info.executor_type.value} at {executor_info.path}")
    except ExecutorNotFoundError as e:
        write_log(log_path, f"ERROR: {e.message}")
        write_log(log_path, "No code executor CLI found. Please install Cursor CLI or Claude Code CLI.")
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

    # Run the executor CLI
    write_log(log_path, f"Invoking executor CLI: {executor_info.executor_type.value}...")
    executor_evidence_id = str(uuid.uuid4())
    executor_command = executor_info.get_apply_command(prompt_file)
    write_log(log_path, f"Command: {' '.join(executor_command)}")

    executor_exit_code, executor_stdout_path, executor_stderr_path = run_executor_cli(
        command=executor_command,
        cwd=worktree_path,
        evidence_dir=evidence_dir,
        evidence_id=executor_evidence_id,
        timeout=execute_config.timeout,
    )

    # Create evidence record for executor output
    create_evidence_record(
        ticket_id=ticket_id,
        job_id=job_id,
        command=" ".join(executor_command),
        exit_code=executor_exit_code,
        stdout_path=executor_stdout_path,
        stderr_path=executor_stderr_path,
        evidence_id=executor_evidence_id,
    )
    evidence_records.append(executor_evidence_id)

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
    diff_evidence_id = str(uuid.uuid4())
    diff_exit_code, diff_stdout_path, diff_stderr_path, diff_stat = capture_git_diff(
        cwd=worktree_path,
        evidence_dir=evidence_dir,
        evidence_id=diff_evidence_id,
    )

    # Create evidence record for git diff
    create_evidence_record(
        ticket_id=ticket_id,
        job_id=job_id,
        command="git diff",
        exit_code=diff_exit_code,
        stdout_path=diff_stdout_path,
        stderr_path=diff_stderr_path,
        evidence_id=diff_evidence_id,
    )
    evidence_records.append(diff_evidence_id)

    write_log(log_path, f"Git diff summary:\n{diff_stat}")

    # Check for cancellation before state transition
    if check_canceled(job_id):
        write_log(log_path, "Job canceled, stopping execution.")
        raise Ignore()

    # Determine outcome and transition ticket
    if executor_exit_code == 0:
        write_log(log_path, "Execution completed successfully!")
        write_log(log_path, "Transitioning ticket to 'verifying'")
        transition_ticket_sync(
            ticket_id,
            TicketState.VERIFYING,
            reason=f"Execution completed by {executor_info.executor_type.value} CLI",
            payload={
                "executor": executor_info.executor_type.value,
                "evidence_ids": evidence_records,
                "diff_summary": diff_stat,
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
        }
    else:
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

    # Load configuration
    config_service = ConfigService(worktree_path.parent.parent if worktree_path else None)
    config = config_service.load_config()
    verify_commands = config.verify_commands
    auto_transition = config.auto_transition_on_success

    write_log(log_path, f"Loaded {len(verify_commands)} verification command(s)")
    write_log(log_path, f"Auto-transition on success: {auto_transition}")

    if not verify_commands:
        write_log(log_path, "No verification commands configured, skipping verification.")
        # No commands = success, transition based on policy
        if auto_transition:
            write_log(log_path, "Transitioning ticket to 'done'")
            transition_ticket_sync(ticket_id, TicketState.DONE, reason="Verification passed (no commands configured)")
        else:
            write_log(log_path, "Transitioning ticket to 'needs_human' for review")
            transition_ticket_sync(ticket_id, TicketState.NEEDS_HUMAN, reason="Verification passed (no commands configured)")
        update_job_finished(job_id, JobStatus.SUCCEEDED, exit_code=0)
        return {"job_id": job_id, "status": "succeeded", "worktree": str(worktree_path) if worktree_path else None}

    # Get evidence directory
    evidence_dir = get_evidence_dir(worktree_path, job_id)

    # Run verification commands
    all_succeeded = True
    failed_commands: list[dict] = []
    evidence_records: list[str] = []

    for i, command in enumerate(verify_commands):
        # Check for cancellation before each command
        if check_canceled(job_id):
            write_log(log_path, "Job canceled, stopping execution.")
            raise Ignore()

        write_log(log_path, f"Running command {i + 1}/{len(verify_commands)}: {command}")

        # Generate evidence ID
        evidence_id = str(uuid.uuid4())

        # Run the command
        exit_code, stdout_path, stderr_path = run_verification_command(
            command=command,
            cwd=worktree_path,
            evidence_dir=evidence_dir,
            evidence_id=evidence_id,
            timeout=300,
        )

        # Create evidence record
        create_evidence_record(
            ticket_id=ticket_id,
            job_id=job_id,
            command=command,
            exit_code=exit_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            evidence_id=evidence_id,
        )
        evidence_records.append(evidence_id)

        if exit_code == 0:
            write_log(log_path, f"Command succeeded (exit code: 0)")
        else:
            write_log(log_path, f"Command FAILED (exit code: {exit_code})")
            all_succeeded = False
            failed_commands.append({
                "command": command,
                "exit_code": exit_code,
                "evidence_id": evidence_id,
            })
            # Stop on first failure
            write_log(log_path, "Stopping verification due to failure.")
            break

    # Transition ticket based on outcome
    if all_succeeded:
        write_log(log_path, "All verification commands passed!")
        if auto_transition:
            write_log(log_path, "Transitioning ticket to 'done'")
            transition_ticket_sync(
                ticket_id,
                TicketState.DONE,
                reason=f"Verification passed: {len(verify_commands)} command(s) succeeded",
                payload={"evidence_ids": evidence_records},
            )
        else:
            write_log(log_path, "Transitioning ticket to 'needs_human' for review")
            transition_ticket_sync(
                ticket_id,
                TicketState.NEEDS_HUMAN,
                reason=f"Verification passed: {len(verify_commands)} command(s) succeeded, awaiting human review",
                payload={"evidence_ids": evidence_records},
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
