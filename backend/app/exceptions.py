"""Custom exceptions for Smart Kanban."""


class SmartKanbanError(Exception):
    """Base exception for Smart Kanban."""

    pass


class InvalidStateTransitionError(SmartKanbanError):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: str, to_state: str, message: str | None = None):
        self.from_state = from_state
        self.to_state = to_state
        self.message = (
            message or f"Invalid transition from '{from_state}' to '{to_state}'"
        )
        super().__init__(self.message)


class ResourceNotFoundError(SmartKanbanError):
    """Raised when a requested resource is not found."""

    def __init__(self, resource_type: str, resource_id: str):
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.message = f"{resource_type} with id '{resource_id}' not found"
        super().__init__(self.message)


class ValidationError(SmartKanbanError):
    """Raised when validation fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class ConflictError(SmartKanbanError):
    """Raised when an operation conflicts with current resource state.

    Typically maps to HTTP 409 Conflict.
    Example: Attempting to comment on a superseded revision.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class WorkspaceError(SmartKanbanError):
    """Base exception for workspace-related errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class NotAGitRepositoryError(WorkspaceError):
    """Raised when the configured path is not a git repository."""

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"Repository at '{path}' is not a git repository")


class WorktreeCreationError(WorkspaceError):
    """Raised when worktree creation fails."""

    def __init__(self, message: str, git_error: str | None = None):
        self.git_error = git_error
        full_message = message
        if git_error:
            full_message = f"{message}: {git_error}"
        super().__init__(full_message)


class BranchNotFoundError(WorkspaceError):
    """Raised when the base branch is not found."""

    def __init__(self, branch: str):
        self.branch = branch
        super().__init__(f"Base branch '{branch}' not found in repository")


class ExecutorError(SmartKanbanError):
    """Base exception for executor-related errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class ExecutorNotFoundError(ExecutorError):
    """Raised when no supported code executor CLI is found."""

    def __init__(self, message: str | None = None):
        default_message = (
            "No supported code executor CLI found. "
            "Please install Cursor CLI or Claude Code CLI."
        )
        super().__init__(message or default_message)


class ExecutorInvocationError(ExecutorError):
    """Raised when the executor CLI invocation fails."""

    def __init__(
        self,
        message: str,
        exit_code: int | None = None,
        stderr: str | None = None,
    ):
        self.exit_code = exit_code
        self.stderr = stderr
        full_message = message
        if exit_code is not None:
            full_message = f"{message} (exit code: {exit_code})"
        if stderr:
            full_message = f"{full_message}\nError output: {stderr}"
        super().__init__(full_message)


class ConfigurationError(SmartKanbanError):
    """Raised when required configuration is missing or invalid."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class PlannerError(SmartKanbanError):
    """Base exception for planner-related errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class LLMAPIError(PlannerError):
    """Raised when an LLM API call fails."""

    def __init__(self, message: str, provider: str, status_code: int | None = None):
        self.provider = provider
        self.status_code = status_code
        full_message = f"[{provider}] {message}"
        if status_code:
            full_message = f"{full_message} (status: {status_code})"
        super().__init__(full_message)
