"""Cursor agent JSON log normalizer.

Parses cursor-agent's stream-json output and converts it to normalized
log entries for display in the UI. Modeled after vibe-kanban's Rust implementation.
"""

import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class NormalizedEntryType(StrEnum):
    """Types of normalized log entries."""

    SYSTEM_MESSAGE = "system_message"
    ASSISTANT_MESSAGE = "assistant_message"
    THINKING = "thinking"
    TOOL_USE = "tool_use"
    ERROR_MESSAGE = "error_message"


class ToolStatus(StrEnum):
    """Status of a tool call."""

    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolActionType(StrEnum):
    """Type of action a tool performs."""

    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    EDIT_FILE = "edit_file"
    LIST_DIR = "list_dir"
    SEARCH = "search"
    SHELL = "shell"
    UNKNOWN = "unknown"


@dataclass
class NormalizedEntry:
    """A normalized log entry for display."""

    entry_type: NormalizedEntryType
    content: str
    sequence: int = 0
    tool_name: str | None = None
    action_type: ToolActionType | None = None
    tool_status: ToolStatus | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class CursorLogNormalizer:
    """Normalizes cursor-agent JSON streaming output.

    Handles message coalescing (combining streaming deltas into complete messages)
    and converts various JSON event types into normalized entries.
    """

    def __init__(self, worktree_path: str = ""):
        self.worktree_path = worktree_path
        self.sequence = 0

        # Coalescing state
        self.current_thinking_buffer = ""
        self.current_thinking_sequence: int | None = None
        self.current_assistant_buffer = ""
        self.current_assistant_sequence: int | None = None

        # Track tool calls by call_id
        self.tool_call_sequences: dict[str, int] = {}

        # Model info
        self.model_reported = False
        self.session_id_reported = False
        self.session_id: str | None = None

    def _next_sequence(self) -> int:
        """Get next sequence number."""
        seq = self.sequence
        self.sequence += 1
        return seq

    def _strip_worktree_prefix(self, path: str) -> str:
        """Strip worktree path prefix from file paths for cleaner display."""
        if self.worktree_path and path.startswith(self.worktree_path):
            return path[len(self.worktree_path) :].lstrip("/")
        return path

    def process_line(self, line: str) -> list[NormalizedEntry]:
        """Process a single JSON line and return normalized entries.

        Returns a list because some lines may produce multiple entries
        (e.g., flushing buffers when switching message types).
        """
        if not line.strip():
            return []

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            # Non-JSON line - treat as system message
            if line.strip():
                return [
                    NormalizedEntry(
                        entry_type=NormalizedEntryType.SYSTEM_MESSAGE,
                        content=line.strip(),
                        sequence=self._next_sequence(),
                    )
                ]
            return []

        entries: list[NormalizedEntry] = []
        msg_type = data.get("type", "")

        # Extract session_id if present
        if not self.session_id_reported:
            session_id = data.get("session_id")
            if session_id:
                self.session_id = session_id
                self.session_id_reported = True

        # Check if we need to flush buffers (switching message types)
        is_thinking = msg_type == "thinking"
        is_assistant = msg_type == "assistant"

        if not is_thinking and self.current_thinking_sequence is not None:
            # Flush thinking buffer
            self.current_thinking_sequence = None
            self.current_thinking_buffer = ""

        if not is_assistant and self.current_assistant_sequence is not None:
            # Flush assistant buffer
            self.current_assistant_sequence = None
            self.current_assistant_buffer = ""

        # Process by message type
        if msg_type == "system":
            entries.extend(self._process_system(data))
        elif msg_type == "user":
            # Skip user messages (just the prompt echo)
            pass
        elif msg_type == "assistant":
            entries.extend(self._process_assistant(data))
        elif msg_type == "thinking":
            entries.extend(self._process_thinking(data))
        elif msg_type == "tool_call":
            entries.extend(self._process_tool_call(data))
        elif msg_type == "result":
            entries.extend(self._process_result(data))
        else:
            # Unknown type - log as system message
            entries.append(
                NormalizedEntry(
                    entry_type=NormalizedEntryType.SYSTEM_MESSAGE,
                    content=f"[{msg_type}] {json.dumps(data)}",
                    sequence=self._next_sequence(),
                )
            )

        return entries

    def _process_system(self, data: dict) -> list[NormalizedEntry]:
        """Process system initialization message."""
        entries = []

        if not self.model_reported:
            model = data.get("model")
            if model:
                entries.append(
                    NormalizedEntry(
                        entry_type=NormalizedEntryType.SYSTEM_MESSAGE,
                        content=f"🤖 Model: {model}",
                        sequence=self._next_sequence(),
                        metadata={"model": model},
                    )
                )
                self.model_reported = True

        return entries

    def _process_assistant(self, data: dict) -> list[NormalizedEntry]:
        """Process assistant message (may be streaming chunks)."""
        message = data.get("message", {})
        content_parts = message.get("content", [])

        # Extract text from content parts
        text = ""
        for part in content_parts:
            if isinstance(part, dict) and part.get("type") == "text":
                text += part.get("text", "")
            elif isinstance(part, str):
                text += part

        if not text:
            return []

        # Coalesce streaming messages
        self.current_assistant_buffer += text

        if self.current_assistant_sequence is None:
            self.current_assistant_sequence = self._next_sequence()

        return [
            NormalizedEntry(
                entry_type=NormalizedEntryType.ASSISTANT_MESSAGE,
                content=self.current_assistant_buffer,
                sequence=self.current_assistant_sequence,
            )
        ]

    def _process_thinking(self, data: dict) -> list[NormalizedEntry]:
        """Process thinking message (streaming deltas)."""
        subtype = data.get("subtype", "")

        if subtype == "delta":
            text = data.get("text", "")
            if text:
                self.current_thinking_buffer += text

                if self.current_thinking_sequence is None:
                    self.current_thinking_sequence = self._next_sequence()

                return [
                    NormalizedEntry(
                        entry_type=NormalizedEntryType.THINKING,
                        content=self.current_thinking_buffer,
                        sequence=self.current_thinking_sequence,
                        metadata={"collapsed": True},
                    )
                ]
        elif subtype == "completed":
            # Thinking completed - keep current buffer
            pass

        return []

    def _process_tool_call(self, data: dict) -> list[NormalizedEntry]:
        """Process tool call start/complete."""
        subtype = data.get("subtype", "")
        call_id = data.get("call_id", "")
        tool_call = data.get("tool_call", {})

        # Determine tool name and action type
        tool_name, action_type, content = self._parse_tool_call(tool_call)

        if subtype == "started":
            seq = self._next_sequence()
            if call_id:
                self.tool_call_sequences[call_id] = seq

            return [
                NormalizedEntry(
                    entry_type=NormalizedEntryType.TOOL_USE,
                    content=content,
                    sequence=seq,
                    tool_name=tool_name,
                    action_type=action_type,
                    tool_status=ToolStatus.CREATED,
                )
            ]
        elif subtype == "completed":
            # Update existing entry with result
            seq = self.tool_call_sequences.get(call_id, self._next_sequence())

            # Extract result info
            result_content = self._extract_tool_result(tool_call)
            if result_content:
                content = f"{content}\n→ {result_content}"

            return [
                NormalizedEntry(
                    entry_type=NormalizedEntryType.TOOL_USE,
                    content=content,
                    sequence=seq,
                    tool_name=tool_name,
                    action_type=action_type,
                    tool_status=ToolStatus.COMPLETED,
                )
            ]

        return []

    def _parse_tool_call(self, tool_call: dict) -> tuple[str, ToolActionType, str]:
        """Parse tool call data to extract name, action type, and display content."""
        # Check various tool call formats
        if "readToolCall" in tool_call:
            args = tool_call["readToolCall"].get("args", {})
            path = self._strip_worktree_prefix(args.get("path", "unknown"))
            return "read_file", ToolActionType.READ_FILE, f"📖 Read: {path}"

        if "editToolCall" in tool_call:
            args = tool_call["editToolCall"].get("args", {})
            path = self._strip_worktree_prefix(args.get("path", "unknown"))
            return "edit_file", ToolActionType.EDIT_FILE, f"✏️ Edit: {path}"

        if "lsToolCall" in tool_call:
            args = tool_call["lsToolCall"].get("args", {})
            path = self._strip_worktree_prefix(args.get("path", "."))
            return "list_dir", ToolActionType.LIST_DIR, f"📁 List: {path}"

        if "globToolCall" in tool_call:
            args = tool_call["globToolCall"].get("args", {})
            pattern = args.get("globPattern", "*")
            return "glob", ToolActionType.SEARCH, f"🔍 Glob: {pattern}"

        if "grepToolCall" in tool_call:
            args = tool_call["grepToolCall"].get("args", {})
            pattern = args.get("pattern", "")
            return "grep", ToolActionType.SEARCH, f"🔍 Grep: {pattern}"

        if "shellToolCall" in tool_call:
            args = tool_call["shellToolCall"].get("args", {})
            command = args.get("command", "")
            return "shell", ToolActionType.SHELL, f"💻 Shell: {command}"

        # Generic/unknown tool
        return (
            "unknown",
            ToolActionType.UNKNOWN,
            f"🔧 Tool call: {json.dumps(tool_call)[:100]}",
        )

    def _extract_tool_result(self, tool_call: dict) -> str:
        """Extract a summary of tool result for display."""
        for key in [
            "readToolCall",
            "editToolCall",
            "lsToolCall",
            "globToolCall",
            "grepToolCall",
            "shellToolCall",
        ]:
            if key in tool_call:
                result = tool_call[key].get("result", {})
                if "success" in result:
                    success = result["success"]
                    if key == "editToolCall":
                        lines_added = success.get("linesAdded", 0)
                        lines_removed = success.get("linesRemoved", 0)
                        return f"+{lines_added} -{lines_removed} lines"
                    elif key == "shellToolCall":
                        exit_code = success.get("exitCode", 0)
                        return f"exit code: {exit_code}"
                    elif key == "globToolCall":
                        total = success.get("totalFiles", 0)
                        return f"{total} files"
                elif "error" in result:
                    return f"❌ {result['error'][:50]}"
        return ""

    def _process_result(self, data: dict) -> list[NormalizedEntry]:
        """Process final result message."""
        result = data.get("result", {})
        if isinstance(result, dict):
            outcome = result.get("outcome", "unknown")
            return [
                NormalizedEntry(
                    entry_type=NormalizedEntryType.SYSTEM_MESSAGE,
                    content=f"✅ Completed: {outcome}",
                    sequence=self._next_sequence(),
                    metadata={"outcome": outcome},
                )
            ]
        return []

    def finalize(self) -> list[NormalizedEntry]:
        """Finalize and return any remaining buffered entries."""
        entries = []

        if self.current_thinking_buffer and self.current_thinking_sequence is not None:
            entries.append(
                NormalizedEntry(
                    entry_type=NormalizedEntryType.THINKING,
                    content=self.current_thinking_buffer,
                    sequence=self.current_thinking_sequence,
                )
            )

        if (
            self.current_assistant_buffer
            and self.current_assistant_sequence is not None
        ):
            entries.append(
                NormalizedEntry(
                    entry_type=NormalizedEntryType.ASSISTANT_MESSAGE,
                    content=self.current_assistant_buffer,
                    sequence=self.current_assistant_sequence,
                )
            )

        return entries


def normalize_cursor_output(
    raw_output: str, worktree_path: str = ""
) -> list[NormalizedEntry]:
    """Convenience function to normalize complete cursor output.

    Args:
        raw_output: Raw stdout from cursor-agent with JSON lines.
        worktree_path: Optional worktree path to strip from file paths.

    Returns:
        List of normalized entries.
    """
    normalizer = CursorLogNormalizer(worktree_path)
    entries = []

    for line in raw_output.splitlines():
        entries.extend(normalizer.process_line(line))

    entries.extend(normalizer.finalize())

    # Deduplicate by sequence (keep latest version)
    seen_sequences: dict[int, NormalizedEntry] = {}
    for entry in entries:
        seen_sequences[entry.sequence] = entry

    return sorted(seen_sequences.values(), key=lambda e: e.sequence)
