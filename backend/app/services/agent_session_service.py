"""Agent session continuity service.

Tracks Claude CLI session IDs to enable multi-turn conversations across executions.
When the same ticket executes multiple times, the agent can continue from where
it left off instead of starting fresh.

Session IDs are stored per-worktree in .smartkanban/agent_session.json
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SESSION_DIR = ".smartkanban"
SESSION_FILE = "agent_session.json"

# Regex patterns to extract session ID from Claude CLI output
# Claude CLI outputs session info in various formats
SESSION_PATTERNS = [
    # "Session: abc123-def456"
    r"Session:\s*([a-zA-Z0-9_-]+)",
    # "Continuing session abc123-def456"
    r"Continuing session\s+([a-zA-Z0-9_-]+)",
    # "session_id: abc123-def456"
    r"session_id:\s*['\"]?([a-zA-Z0-9_-]+)['\"]?",
    # JSON output: {"session_id": "abc123"}
    r'"session_id"\s*:\s*"([a-zA-Z0-9_-]+)"',
    # "--resume abc123" flag echoed
    r"--resume\s+([a-zA-Z0-9_-]+)",
]


@dataclass
class AgentSession:
    """Represents a stored agent session."""
    session_id: str
    agent_type: str  # "claude", "cursor", etc.
    ticket_id: str
    created_at: datetime
    last_used_at: datetime
    execution_count: int = 1

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "ticket_id": self.ticket_id,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat(),
            "execution_count": self.execution_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentSession":
        return cls(
            session_id=data["session_id"],
            agent_type=data["agent_type"],
            ticket_id=data["ticket_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_used_at=datetime.fromisoformat(data["last_used_at"]),
            execution_count=data.get("execution_count", 1),
        )


class AgentSessionService:
    """Manages agent session continuity for a worktree."""

    def __init__(self, worktree_path: Path):
        self.worktree_path = worktree_path
        self.session_dir = worktree_path / SESSION_DIR
        self.session_file = self.session_dir / SESSION_FILE

    def _ensure_dir(self) -> None:
        """Ensure the session directory exists."""
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Add to .gitignore if not already
        gitignore = self.worktree_path / ".gitignore"
        marker = f"/{SESSION_DIR}/"
        if gitignore.exists():
            content = gitignore.read_text()
            if marker not in content:
                with open(gitignore, "a") as f:
                    f.write(f"\n# SmartKanban session data\n{marker}\n")
        else:
            gitignore.write_text(f"# SmartKanban session data\n{marker}\n")

    def get_session(self, ticket_id: str) -> AgentSession | None:
        """Get the stored session for a ticket.

        Args:
            ticket_id: The ticket ID to get session for

        Returns:
            AgentSession if found and matches ticket, None otherwise
        """
        if not self.session_file.exists():
            return None

        try:
            data = json.loads(self.session_file.read_text())
            session = AgentSession.from_dict(data)

            # Only return if it's for the same ticket
            if session.ticket_id == ticket_id:
                return session

            logger.debug(f"Session exists but for different ticket ({session.ticket_id} != {ticket_id})")
            return None

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to read session file: {e}")
            return None

    def save_session(
        self,
        session_id: str,
        ticket_id: str,
        agent_type: str = "claude",
    ) -> AgentSession:
        """Save or update a session.

        Args:
            session_id: The agent's session ID
            ticket_id: The ticket this session is for
            agent_type: Type of agent ("claude", "cursor", etc.)

        Returns:
            The saved AgentSession
        """
        self._ensure_dir()

        now = datetime.now(UTC)

        # Check if updating existing session
        existing = self.get_session(ticket_id)
        if existing and existing.session_id == session_id:
            existing.last_used_at = now
            existing.execution_count += 1
            session = existing
        else:
            session = AgentSession(
                session_id=session_id,
                agent_type=agent_type,
                ticket_id=ticket_id,
                created_at=now,
                last_used_at=now,
                execution_count=1,
            )

        self.session_file.write_text(json.dumps(session.to_dict(), indent=2))
        logger.info(f"Saved session {session_id} for ticket {ticket_id} (count: {session.execution_count})")

        return session

    def clear_session(self) -> None:
        """Clear the stored session (e.g., when ticket is done)."""
        if self.session_file.exists():
            self.session_file.unlink()
            logger.info("Cleared agent session")

    def extract_session_id_from_output(self, output: str) -> str | None:
        """Extract session ID from agent CLI output.

        Parses various output formats to find the session ID.

        Args:
            output: The stdout/stderr from the agent CLI

        Returns:
            Session ID if found, None otherwise
        """
        for pattern in SESSION_PATTERNS:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                session_id = match.group(1)
                logger.debug(f"Extracted session ID: {session_id}")
                return session_id

        return None

    def get_continue_flag(self, ticket_id: str, agent_type: str = "claude") -> str | None:
        """Get the CLI flag to continue an existing session.

        Args:
            ticket_id: The ticket ID
            agent_type: Type of agent

        Returns:
            CLI flag string if session exists (e.g., "--resume abc123"), None otherwise
        """
        session = self.get_session(ticket_id)
        if not session:
            return None

        if agent_type == "claude":
            return f"--resume {session.session_id}"
        elif agent_type == "cursor":
            # Cursor uses different flag
            return f"--continue {session.session_id}"

        return None


def get_session_service(worktree_path: Path) -> AgentSessionService:
    """Factory function to get session service for a worktree."""
    return AgentSessionService(worktree_path)
