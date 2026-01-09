"""Pydantic schemas for Evidence entity."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EvidenceKind(str, Enum):
    """Enum representing the kind of evidence.

    Metadata evidence (JSON in stdout_path):
    - EXECUTOR_META: JSON with exit_code, duration, executor_type, mode, command
    - VERIFY_META: JSON with exit_code, commands_run, duration, results per command

    Evidence types for execution:
    - EXECUTOR_STDOUT: stdout from executor CLI (Claude/Cursor)
    - EXECUTOR_STDERR: stderr from executor CLI
    - GIT_DIFF_STAT: output of `git diff --stat`
    - GIT_DIFF_PATCH: full git diff patch

    Evidence types for verification:
    - VERIFY_STDOUT: stdout from verification command
    - VERIFY_STDERR: stderr from verification command

    Legacy types (kept for backwards compatibility):
    - COMMAND_LOG: generic command output
    - TEST_REPORT: test framework report
    """

    # Metadata evidence (JSON)
    EXECUTOR_META = "executor_meta"
    VERIFY_META = "verify_meta"

    # Executor evidence
    EXECUTOR_STDOUT = "executor_stdout"
    EXECUTOR_STDERR = "executor_stderr"

    # Git diff evidence
    GIT_DIFF_STAT = "git_diff_stat"
    GIT_DIFF_PATCH = "git_diff_patch"

    # Verification evidence
    VERIFY_STDOUT = "verify_stdout"
    VERIFY_STDERR = "verify_stderr"

    # Merge evidence
    MERGE_STDOUT = "merge_stdout"
    MERGE_STDERR = "merge_stderr"
    MERGE_META = "merge_meta"

    # Legacy types (backwards compatibility)
    COMMAND_LOG = "command_log"
    TEST_REPORT = "test_report"


class EvidenceResponse(BaseModel):
    """Schema for evidence response."""

    id: str
    ticket_id: str
    job_id: str
    kind: EvidenceKind
    command: str
    exit_code: int
    stdout_path: str | None
    stderr_path: str | None
    created_at: datetime
    succeeded: bool = Field(description="Whether the command succeeded (exit_code == 0)")

    model_config = {"from_attributes": True}


class EvidenceDetailResponse(EvidenceResponse):
    """Schema for detailed evidence response including stdout/stderr content."""

    stdout: str | None = Field(None, description="Content of stdout (if available)")
    stderr: str | None = Field(None, description="Content of stderr (if available)")


class EvidenceListResponse(BaseModel):
    """Schema for list of evidence records."""

    evidence: list[EvidenceResponse]
    total: int

