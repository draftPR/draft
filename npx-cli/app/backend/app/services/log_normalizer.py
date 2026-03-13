"""Service for parsing raw agent logs into structured entries."""

import difflib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.normalized_log import LogEntryType, NormalizedLogEntry


@dataclass
class ParsedEntry:
    """Temporary structure before DB insert."""

    entry_type: LogEntryType
    content: str
    metadata: dict[str, Any]
    timestamp: datetime | None = None


class ClaudeLogParser:
    """Parser for Claude Code CLI output format."""

    # Regex patterns for Claude's output format
    THINKING_PATTERN = re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL)
    TOOL_USE_PATTERN = re.compile(r"<tool_use>(.*?)</tool_use>", re.DOTALL)
    FILE_EDIT_PATTERN = re.compile(
        r"<file_edit>\s*<path>(.*?)</path>\s*<content>(.*?)</content>\s*</file_edit>",
        re.DOTALL,
    )
    FILE_CREATE_PATTERN = re.compile(
        r"<file_create>\s*<path>(.*?)</path>\s*<content>(.*?)</content>\s*</file_create>",
        re.DOTALL,
    )
    FILE_DELETE_PATTERN = re.compile(
        r"<file_delete>\s*<path>(.*?)</path>\s*</file_delete>", re.DOTALL
    )
    COMMAND_PATTERN = re.compile(r"<command>(.*?)</command>", re.DOTALL)
    ERROR_PATTERN = re.compile(r"Error:(.*?)(?=\n\n|\Z)", re.DOTALL)

    def parse(self, raw_log: str) -> list[ParsedEntry]:
        """Parse raw log into structured entries."""
        entries: list[ParsedEntry] = []
        position = 0

        # Split log by major sections
        while position < len(raw_log):
            # Try to match patterns in order of priority

            # 1. Tool use (contains file edits, commands, etc.)
            tool_match = self.TOOL_USE_PATTERN.search(raw_log, position)
            if tool_match and tool_match.start() == position:
                tool_content = tool_match.group(1)
                entries.extend(self._parse_tool_use(tool_content))
                position = tool_match.end()
                continue

            # 2. Thinking blocks
            thinking_match = self.THINKING_PATTERN.search(raw_log, position)
            if thinking_match and thinking_match.start() == position:
                thinking = thinking_match.group(1).strip()
                entries.append(
                    ParsedEntry(
                        entry_type=LogEntryType.THINKING,
                        content=thinking,
                        metadata={"collapsed": True},  # Start collapsed
                    )
                )
                position = thinking_match.end()
                continue

            # 3. Errors
            error_match = self.ERROR_PATTERN.search(raw_log, position)
            if error_match and error_match.start() == position:
                error_text = error_match.group(1).strip()
                entries.append(
                    ParsedEntry(
                        entry_type=LogEntryType.ERROR,
                        content=error_text,
                        metadata={"highlight": True},
                    )
                )
                position = error_match.end()
                continue

            # 4. Plain text (system messages, outputs, etc.)
            next_special = self._find_next_special(raw_log, position)
            if next_special > position:
                plain_text = raw_log[position:next_special].strip()
                if plain_text:
                    entries.append(
                        ParsedEntry(
                            entry_type=LogEntryType.SYSTEM_MESSAGE,
                            content=plain_text,
                            metadata={},
                        )
                    )
                position = next_special
            else:
                # No more special patterns, capture remaining text
                remaining = raw_log[position:].strip()
                if remaining:
                    entries.append(
                        ParsedEntry(
                            entry_type=LogEntryType.SYSTEM_MESSAGE,
                            content=remaining,
                            metadata={},
                        )
                    )
                break

        return entries

    def _parse_tool_use(self, tool_content: str) -> list[ParsedEntry]:
        """Parse tool use block (may contain multiple operations)."""
        entries: list[ParsedEntry] = []

        # File edits
        for match in self.FILE_EDIT_PATTERN.finditer(tool_content):
            file_path = match.group(1).strip()
            content = match.group(2).strip()

            # Generate diff if we have original file
            diff = self._generate_diff(file_path, content)

            entries.append(
                ParsedEntry(
                    entry_type=LogEntryType.FILE_EDIT,
                    content=f"Edited {file_path}",
                    metadata={
                        "file_path": file_path,
                        "new_content": content,
                        "diff": diff,
                        "language": self._detect_language(file_path),
                    },
                )
            )

        # File creates
        for match in self.FILE_CREATE_PATTERN.finditer(tool_content):
            file_path = match.group(1).strip()
            content = match.group(2).strip()

            entries.append(
                ParsedEntry(
                    entry_type=LogEntryType.FILE_CREATE,
                    content=f"Created {file_path}",
                    metadata={
                        "file_path": file_path,
                        "new_content": content,
                        "language": self._detect_language(file_path),
                    },
                )
            )

        # File deletes
        for match in self.FILE_DELETE_PATTERN.finditer(tool_content):
            file_path = match.group(1).strip()

            entries.append(
                ParsedEntry(
                    entry_type=LogEntryType.FILE_DELETE,
                    content=f"Deleted {file_path}",
                    metadata={"file_path": file_path},
                )
            )

        # Commands
        for match in self.COMMAND_PATTERN.finditer(tool_content):
            command = match.group(1).strip()

            # Try to extract result if present
            result_pattern = re.compile(
                rf"<command>{re.escape(command)}</command>.*?<result>(.*?)</result>",
                re.DOTALL,
            )
            result_match = result_pattern.search(tool_content)
            output = result_match.group(1).strip() if result_match else None

            # Simple heuristic for exit code
            exit_code = (
                0 if output and "error" not in output.lower() else 1 if output else 0
            )

            entries.append(
                ParsedEntry(
                    entry_type=LogEntryType.COMMAND_RUN,
                    content=command,
                    metadata={
                        "command": command,
                        "output": output,
                        "exit_code": exit_code,
                    },
                )
            )

        return entries

    def _generate_diff(self, file_path: str, new_content: str) -> str | None:
        """Generate unified diff if original file exists."""
        try:
            path = Path(file_path)
            if not path.exists():
                return None

            original = path.read_text()
            diff_lines = difflib.unified_diff(
                original.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm="",
            )
            return "".join(diff_lines)
        except Exception:
            return None

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".rb": "ruby",
            ".php": "php",
            ".sql": "sql",
            ".sh": "bash",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".md": "markdown",
        }
        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, "text")

    def _find_next_special(self, text: str, start: int) -> int:
        """Find the next position of any special pattern."""
        patterns = [self.THINKING_PATTERN, self.TOOL_USE_PATTERN, self.ERROR_PATTERN]

        min_pos = len(text)
        for pattern in patterns:
            match = pattern.search(text, start)
            if match:
                min_pos = min(min_pos, match.start())

        return min_pos


class CursorLogParser:
    """Parser for Cursor Agent CLI output."""

    def parse(self, raw_log: str) -> list[ParsedEntry]:
        """Parse Cursor Agent output (similar structure to Claude)."""
        # For now, use similar parsing logic as Claude
        # Can be customized later for Cursor-specific format
        return ClaudeLogParser().parse(raw_log)


class LogNormalizerService:
    """Main service for log normalization."""

    def __init__(self):
        self.parsers = {
            "claude": ClaudeLogParser(),
            "cursor": CursorLogParser(),
            # Add more as needed
        }

    async def normalize_and_store(
        self,
        db: AsyncSession,
        job_id: str,
        raw_log: str,
        agent_type: str = "claude",
    ) -> list[NormalizedLogEntry]:
        """
        Parse raw log and store normalized entries.

        Args:
            db: Database session
            job_id: The job ID
            raw_log: Raw log content
            agent_type: Type of agent (determines parser)

        Returns:
            List of created NormalizedLogEntry objects
        """
        parser = self.parsers.get(agent_type)
        if not parser:
            # Fallback to Claude parser
            parser = self.parsers["claude"]

        # Parse
        parsed_entries = parser.parse(raw_log)

        # Store in DB
        db_entries = []
        for i, parsed in enumerate(parsed_entries):
            entry = NormalizedLogEntry(
                job_id=job_id,
                sequence=i,
                entry_type=parsed.entry_type,
                content=parsed.content,
                entry_metadata=parsed.metadata,
                timestamp=parsed.timestamp or datetime.utcnow(),
                collapsed=parsed.metadata.get("collapsed", False),
                highlight=parsed.metadata.get("highlight", False),
            )
            db.add(entry)
            db_entries.append(entry)

        await db.commit()

        # Refresh to get IDs
        for entry in db_entries:
            await db.refresh(entry)

        return db_entries

    async def get_normalized_logs(
        self, db: AsyncSession, job_id: str
    ) -> list[NormalizedLogEntry]:
        """Retrieve all normalized logs for a job."""
        from sqlalchemy import select

        result = await db.execute(
            select(NormalizedLogEntry)
            .where(NormalizedLogEntry.job_id == job_id)
            .order_by(NormalizedLogEntry.sequence)
        )
        return list(result.scalars().all())
