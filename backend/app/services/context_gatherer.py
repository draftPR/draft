"""Secure, metadata-first repository context gathering.

This module provides safe context gathering for LLM-based ticket generation.
It follows these principles:

1. METADATA-FIRST: Returns file paths, line counts, and small excerpts only.
   Never returns full file contents except for small, capped excerpts.

2. STRICT CAPS: Hard limits on files scanned, bytes read, and excerpt sizes
   to prevent runaway prompts and cost explosions.

3. SECURITY: Excludes sensitive paths (.env, keys, secrets) and skips symlinks
   to prevent secret leakage to third-party LLM providers.
"""

import fnmatch
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FileMetadata:
    """Metadata about a single file."""

    path: str  # Relative to repo root
    line_count: int
    language: str | None  # Detected from extension
    size_bytes: int


@dataclass
class GatherStats:
    """Statistics from the context gathering operation."""

    files_scanned: int = 0
    bytes_read: int = 0
    skipped_excluded: int = 0
    skipped_symlinks: int = 0
    skipped_binary: int = 0
    skipped_too_large: int = 0
    todo_lines_found: int = 0
    # Observability: track what was excluded and what was scanned
    excluded_by_pattern: dict[str, int] = field(default_factory=dict)  # pattern -> count
    extensions_scanned: dict[str, int] = field(default_factory=dict)  # extension -> count


@dataclass
class RepoContext:
    """Gathered repository context for LLM consumption."""

    file_tree: list[FileMetadata]
    project_type: str  # "python", "node", "mixed", "unknown"
    todo_count: int
    todo_excerpts: list[str]  # Max 50, each max 200 chars
    readme_excerpt: str | None  # Max 500 chars if enabled
    stats: GatherStats = field(default_factory=GatherStats)

    def to_prompt_string(self) -> str:
        """Convert to a string suitable for LLM prompts."""
        parts = []

        # Project type
        parts.append(f"Project type: {self.project_type}")

        # File tree summary (top directories + file counts by type)
        if self.file_tree:
            # Group by directory
            dir_counts: dict[str, int] = {}
            ext_counts: dict[str, int] = {}
            for f in self.file_tree:
                # Get top-level directory
                path_parts = f.path.split("/")
                if len(path_parts) > 1:
                    top_dir = path_parts[0]
                    dir_counts[top_dir] = dir_counts.get(top_dir, 0) + 1
                # Count extensions
                if f.language:
                    ext_counts[f.language] = ext_counts.get(f.language, 0) + 1

            if dir_counts:
                top_dirs = sorted(dir_counts.items(), key=lambda x: -x[1])[:10]
                parts.append(
                    f"Top directories: {', '.join(f'{d} ({c} files)' for d, c in top_dirs)}"
                )

            if ext_counts:
                top_exts = sorted(ext_counts.items(), key=lambda x: -x[1])[:8]
                parts.append(
                    f"File types: {', '.join(f'{e} ({c})' for e, c in top_exts)}"
                )

            parts.append(f"Total files indexed: {len(self.file_tree)}")

        # README excerpt
        if self.readme_excerpt:
            parts.append(f"README excerpt:\n{self.readme_excerpt}")

        # TODOs
        if self.todo_count > 0:
            parts.append(f"TODO/FIXME comments found: {self.todo_count}")
            if self.todo_excerpts:
                parts.append("Sample TODOs:")
                for excerpt in self.todo_excerpts[:10]:
                    parts.append(f"  - {excerpt}")

        # Stats
        parts.append(
            f"Scan stats: {self.stats.files_scanned} files scanned, "
            f"{self.stats.skipped_excluded} excluded, "
            f"{self.stats.skipped_symlinks} symlinks skipped"
        )

        return "\n".join(parts)


class ContextGatherer:
    """Metadata-first repo context with strict caps and exclusions.

    This class gathers repository context safely for LLM consumption:
    - Never reads full file contents (only line counts and small excerpts)
    - Excludes sensitive files (secrets, env, keys)
    - Enforces hard caps on all operations
    - Skips symlinks entirely
    """

    # Hard caps - non-negotiable limits
    MAX_FILES_SCANNED = 500
    MAX_BYTES_TOTAL = 50_000  # ~50KB of excerpts
    MAX_TODO_LINES = 50
    MAX_EXCERPT_CHARS = 200
    MAX_README_CHARS = 500
    MAX_FILE_SIZE_FOR_SCAN = 100_000  # Skip files > 100KB for TODO scanning

    # Sensitive path patterns to exclude (glob-style)
    EXCLUDED_PATTERNS = [
        # Environment and secrets
        ".env",
        ".env.*",
        "*.env",
        ".envrc",
        "secrets.*",
        "*secret*",
        "*password*",
        # Keys and certificates
        "*.pem",
        "*.key",
        "*.crt",
        "*.p12",
        "*.pfx",
        "id_rsa*",
        "id_ed25519*",
        "*.pub",
        # Config files that might contain secrets
        "credentials*",
        "*_credentials*",
        "auth.json",
        "config.local.*",
        # Package directories
        "node_modules/",
        "venv/",
        ".venv/",
        "__pycache__/",
        ".git/",
        ".svn/",
        ".hg/",
        # Build artifacts
        "dist/",
        "build/",
        "*.pyc",
        "*.pyo",
        "*.so",
        "*.dylib",
        "*.dll",
        # Logs and data
        "*.log",
        "*.sqlite",
        "*.db",
        # IDE and editor
        ".idea/",
        ".vscode/",
        "*.swp",
        "*.swo",
        # Coverage and test artifacts
        "coverage/",
        ".coverage",
        "htmlcov/",
        ".pytest_cache/",
        ".mypy_cache/",
        # Binary files
        "*.jpg",
        "*.jpeg",
        "*.png",
        "*.gif",
        "*.ico",
        "*.pdf",
        "*.zip",
        "*.tar",
        "*.gz",
        "*.woff",
        "*.woff2",
        "*.ttf",
        "*.eot",
    ]

    # Extension to language mapping
    EXTENSION_LANGUAGES = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".kt": "kotlin",
        ".rb": "ruby",
        ".php": "php",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".swift": "swift",
        ".sh": "shell",
        ".bash": "shell",
        ".zsh": "shell",
        ".sql": "sql",
        ".md": "markdown",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".xml": "xml",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".less": "less",
    }

    def __init__(
        self,
        max_files: int | None = None,
        max_bytes: int | None = None,
        max_todos: int | None = None,
        additional_exclusions: list[str] | None = None,
    ):
        """Initialize the context gatherer.

        Args:
            max_files: Override MAX_FILES_SCANNED (can only decrease).
            max_bytes: Override MAX_BYTES_TOTAL (can only decrease).
            max_todos: Override MAX_TODO_LINES (can only decrease).
            additional_exclusions: Additional glob patterns to exclude.
        """
        self.max_files = min(max_files or self.MAX_FILES_SCANNED, self.MAX_FILES_SCANNED)
        self.max_bytes = min(max_bytes or self.MAX_BYTES_TOTAL, self.MAX_BYTES_TOTAL)
        self.max_todos = min(max_todos or self.MAX_TODO_LINES, self.MAX_TODO_LINES)

        self.exclusions = list(self.EXCLUDED_PATTERNS)
        if additional_exclusions:
            self.exclusions.extend(additional_exclusions)

    def gather(
        self,
        repo_root: Path | str,
        include_readme_excerpt: bool = False,
    ) -> RepoContext:
        """Gather repository context.

        Args:
            repo_root: Path to the repository root.
            include_readme_excerpt: Whether to include README excerpt (default OFF).

        Returns:
            RepoContext with metadata about the repository.
        """
        repo_root = Path(repo_root).resolve()
        if not repo_root.exists():
            logger.warning(f"Repository root does not exist: {repo_root}")
            return RepoContext(
                file_tree=[],
                project_type="unknown",
                todo_count=0,
                todo_excerpts=[],
                readme_excerpt=None,
            )

        stats = GatherStats()
        file_tree: list[FileMetadata] = []
        todo_excerpts: list[str] = []
        readme_excerpt: str | None = None

        # Detect project type
        project_type = self._detect_project_type(repo_root)

        # Scan files
        bytes_read = 0
        for file_path in self._walk_files(repo_root, stats):
            if stats.files_scanned >= self.max_files:
                break

            try:
                # Get file metadata (no content read yet)
                rel_path = str(file_path.relative_to(repo_root))
                file_size = file_path.stat().st_size
                extension = file_path.suffix.lower()
                language = self.EXTENSION_LANGUAGES.get(extension)

                # Count lines without reading entire file into memory
                line_count = self._count_lines(file_path)
                if line_count is None:
                    stats.skipped_binary += 1
                    continue

                file_tree.append(
                    FileMetadata(
                        path=rel_path,
                        line_count=line_count,
                        language=language,
                        size_bytes=file_size,
                    )
                )
                stats.files_scanned += 1

                # Scan for TODOs if file is small enough and we haven't hit the cap
                if (
                    len(todo_excerpts) < self.max_todos
                    and file_size < self.MAX_FILE_SIZE_FOR_SCAN
                    and bytes_read < self.max_bytes
                    and language in ("python", "javascript", "typescript", "go", "rust", "java")
                ):
                    new_todos, bytes_used = self._extract_todos(
                        file_path, rel_path, self.max_todos - len(todo_excerpts)
                    )
                    todo_excerpts.extend(new_todos)
                    bytes_read += bytes_used
                    stats.todo_lines_found += len(new_todos)

            except (OSError, PermissionError) as e:
                logger.debug(f"Failed to read {file_path}: {e}")
                continue

        # Get README excerpt if requested
        if include_readme_excerpt:
            readme_excerpt = self._get_readme_excerpt(repo_root)
            if readme_excerpt:
                bytes_read += len(readme_excerpt.encode("utf-8", errors="replace"))

        stats.bytes_read = bytes_read

        return RepoContext(
            file_tree=file_tree,
            project_type=project_type,
            todo_count=stats.todo_lines_found,
            todo_excerpts=todo_excerpts,
            readme_excerpt=readme_excerpt,
            stats=stats,
        )

    def _walk_files(self, repo_root: Path, stats: GatherStats):
        """Walk repository files, respecting exclusions and caps.

        Yields file paths, updating stats as it goes.
        """
        for item in repo_root.rglob("*"):
            # Skip directories
            if item.is_dir():
                continue

            # Skip symlinks entirely (security)
            if item.is_symlink():
                stats.skipped_symlinks += 1
                continue

            # Check exclusions (returns matching pattern if excluded)
            rel_path = str(item.relative_to(repo_root))
            matched_pattern = self._get_exclusion_match(rel_path, item.name)
            if matched_pattern:
                stats.skipped_excluded += 1
                # Track which patterns are matching (for debugging bad suggestions)
                stats.excluded_by_pattern[matched_pattern] = (
                    stats.excluded_by_pattern.get(matched_pattern, 0) + 1
                )
                continue

            # Track extension for filetype histogram
            ext = item.suffix.lower() or "(no extension)"
            stats.extensions_scanned[ext] = stats.extensions_scanned.get(ext, 0) + 1

            yield item

    def _get_exclusion_match(self, rel_path: str, filename: str) -> str | None:
        """Check if a path matches any exclusion pattern.
        
        Returns the matching pattern if excluded, None otherwise.
        """
        for pattern in self.exclusions:
            # Check against full relative path
            if fnmatch.fnmatch(rel_path, pattern):
                return pattern
            if fnmatch.fnmatch(rel_path, f"**/{pattern}"):
                return pattern
            # Check against filename only
            if fnmatch.fnmatch(filename, pattern):
                return pattern
            # Check if path contains the pattern as a directory
            if pattern.endswith("/") and pattern[:-1] in rel_path.split("/"):
                return pattern
        return None

    def _is_excluded(self, rel_path: str, filename: str) -> bool:
        """Check if a path matches any exclusion pattern."""
        return self._get_exclusion_match(rel_path, filename) is not None

    def _count_lines(self, file_path: Path) -> int | None:
        """Count lines in a file without loading it all into memory.

        Returns None if the file appears to be binary.
        """
        try:
            line_count = 0
            with open(file_path, "rb") as f:
                # Read first 8KB to check if binary
                sample = f.read(8192)
                if b"\x00" in sample:
                    return None  # Binary file

                # Count newlines in sample
                line_count = sample.count(b"\n")

                # Continue counting for rest of file
                for chunk in iter(lambda: f.read(65536), b""):
                    line_count += chunk.count(b"\n")

            return line_count
        except Exception:
            return None

    def _extract_todos(
        self, file_path: Path, rel_path: str, max_count: int
    ) -> tuple[list[str], int]:
        """Extract TODO/FIXME comments from a file.

        Returns (list of excerpts, bytes read).
        """
        todos: list[str] = []
        bytes_read = 0
        todo_pattern = re.compile(r"#\s*(TODO|FIXME|XXX|HACK)\b[:\s]*(.*)", re.IGNORECASE)

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, 1):
                    bytes_read += len(line.encode("utf-8", errors="replace"))

                    match = todo_pattern.search(line)
                    if match:
                        tag = match.group(1).upper()
                        message = match.group(2).strip()[:self.MAX_EXCERPT_CHARS]
                        # Sanitize - remove any potential secrets
                        if not self._looks_like_secret(message):
                            excerpt = f"{rel_path}:{line_num} [{tag}] {message}"
                            todos.append(excerpt[:self.MAX_EXCERPT_CHARS])

                            if len(todos) >= max_count:
                                break

                    # Cap bytes read per file
                    if bytes_read > self.MAX_FILE_SIZE_FOR_SCAN:
                        break

        except Exception as e:
            logger.debug(f"Failed to extract TODOs from {file_path}: {e}")

        return todos, bytes_read

    def _looks_like_secret(self, text: str) -> bool:
        """Check if text looks like it might contain a secret."""
        text_lower = text.lower()
        secret_indicators = [
            "password",
            "secret",
            "api_key",
            "apikey",
            "token",
            "credential",
            "auth",
            "bearer",
            "private_key",
        ]
        # Check for key=value patterns with these words
        for indicator in secret_indicators:
            if indicator in text_lower and "=" in text:
                return True
        # Check for long hex strings (possible keys/tokens)
        if re.search(r"[a-fA-F0-9]{32,}", text):
            return True
        return False

    def _detect_project_type(self, repo_root: Path) -> str:
        """Detect the project type from configuration files."""
        indicators = {
            "python": ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
            "node": ["package.json", "yarn.lock", "pnpm-lock.yaml"],
            "go": ["go.mod", "go.sum"],
            "rust": ["Cargo.toml"],
            "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
            "ruby": ["Gemfile", "Rakefile"],
        }

        detected = []
        for lang, files in indicators.items():
            for f in files:
                if (repo_root / f).exists():
                    detected.append(lang)
                    break

        if not detected:
            return "unknown"
        if len(detected) == 1:
            return detected[0]
        return "mixed"

    def _get_readme_excerpt(self, repo_root: Path) -> str | None:
        """Get a capped excerpt from the README file."""
        readme_names = ["README.md", "README.rst", "README.txt", "README"]

        for name in readme_names:
            readme_path = repo_root / name
            if readme_path.exists() and readme_path.is_file():
                try:
                    with open(readme_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read(self.MAX_README_CHARS + 100)
                        if len(content) > self.MAX_README_CHARS:
                            # Truncate at word boundary
                            content = content[:self.MAX_README_CHARS]
                            last_space = content.rfind(" ")
                            if last_space > self.MAX_README_CHARS - 50:
                                content = content[:last_space]
                            content += "..."
                        return content
                except Exception as e:
                    logger.debug(f"Failed to read README {readme_path}: {e}")

        return None

