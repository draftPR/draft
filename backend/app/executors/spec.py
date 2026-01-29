"""
Smart Kanban Executor Adapter Specification v1.0

This defines the interface for adding new AI coding agents to Smart Kanban.
Implement this interface to create a new executor plugin.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional, AsyncIterator
from enum import Enum


class ExecutorCapability(str, Enum):
    """Capabilities an executor may support."""
    STREAMING_OUTPUT = "streaming_output"    # Real-time stdout
    SESSION_RESUME = "session_resume"        # Continue previous sessions
    YOLO_MODE = "yolo_mode"                  # Auto-approve all actions
    MCP_SERVERS = "mcp_servers"              # Model Context Protocol
    COST_TRACKING = "cost_tracking"          # Token/cost reporting
    INTERACTIVE = "interactive"              # Requires human interaction


@dataclass
class ExecutorMetadata:
    """Metadata about an executor."""
    name: str                                # e.g., "claude", "codex"
    display_name: str                        # e.g., "Claude Code", "OpenAI Codex"
    version: str                             # Executor adapter version
    agent_version: Optional[str] = None      # Underlying agent version if detectable
    capabilities: List[ExecutorCapability] = field(default_factory=list)
    config_schema: Dict = field(default_factory=dict)  # JSON Schema for configuration
    documentation_url: Optional[str] = None
    author: Optional[str] = None             # Plugin author
    license: Optional[str] = None            # Plugin license


@dataclass
class ExecutionRequest:
    """Request to execute a task."""
    prompt: str
    working_directory: str
    timeout_seconds: int = 600
    yolo_mode: bool = False
    session_id: Optional[str] = None         # For session resume
    environment: Dict[str, str] = field(default_factory=dict)  # Additional env vars
    mcp_servers: List[Dict] = field(default_factory=list)      # MCP server configs
    config: Dict[str, any] = field(default_factory=dict)       # Executor-specific config


@dataclass
class ExecutionResult:
    """Result of an execution."""
    exit_code: int
    stdout: str
    stderr: str
    session_id: Optional[str] = None         # For future resume
    files_changed: List[str] = field(default_factory=list)
    cost_usd: Optional[float] = None
    tokens_used: Optional[Dict[str, int]] = None  # {"input": X, "output": Y}
    duration_seconds: float = 0.0
    metadata: Dict[str, any] = field(default_factory=dict)  # Executor-specific data


class ExecutorAdapter(ABC):
    """
    Abstract base class for executor adapters.

    Implement this to add a new AI coding agent to Smart Kanban.
    """

    @abstractmethod
    def get_metadata(self) -> ExecutorMetadata:
        """Return metadata about this executor.

        Returns:
            ExecutorMetadata with name, capabilities, etc.
        """
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the underlying agent is installed and accessible.

        Returns:
            True if executor can be used, False otherwise
        """
        pass

    @abstractmethod
    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a task and return the result.

        Args:
            request: ExecutionRequest with prompt, working directory, etc.

        Returns:
            ExecutionResult with exit code, stdout, stderr, etc.

        Raises:
            ExecutorError: If execution fails
        """
        pass

    async def stream_output(
        self,
        request: ExecutionRequest
    ) -> AsyncIterator[str]:
        """
        Stream output in real-time. Optional - implement if your agent supports it.

        Default implementation runs execute() and yields all output at once.

        Args:
            request: ExecutionRequest

        Yields:
            str: Output lines as they're produced
        """
        result = await self.execute(request)
        yield result.stdout
        if result.stderr:
            yield result.stderr

    def get_mcp_config_path(self) -> Optional[str]:
        """Return the path to this agent's MCP config file, if applicable.

        Returns:
            Path to MCP config or None
        """
        return None

    def supports_capability(self, capability: ExecutorCapability) -> bool:
        """Check if this executor supports a capability.

        Args:
            capability: ExecutorCapability to check

        Returns:
            True if supported
        """
        metadata = self.get_metadata()
        return capability in metadata.capabilities

    async def validate_config(self, config: Dict) -> bool:
        """Validate executor-specific configuration.

        Args:
            config: Configuration dict to validate

        Returns:
            True if valid

        Raises:
            ValueError: If config is invalid
        """
        # Default: no validation
        return True


class ExecutorError(Exception):
    """Base exception for executor errors."""
    pass


class ExecutorNotFoundError(ExecutorError):
    """Raised when executor CLI is not found."""
    pass


class ExecutorInvocationError(ExecutorError):
    """Raised when executor CLI invocation fails."""

    def __init__(self, message: str, exit_code: Optional[int] = None, stderr: Optional[str] = None):
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr


class ExecutorTimeoutError(ExecutorError):
    """Raised when executor execution times out."""
    pass
