"""Service for browsing worktree file trees."""

from pathlib import Path

# Directories to always skip
SKIP_DIRS = {
    ".git",
    ".draft",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".next",
    ".nuxt",
}

# Max depth to prevent extremely deep traversal
MAX_DEPTH = 8
# Max total entries to return
MAX_ENTRIES = 500


def build_file_tree(
    root_path: str,
    max_depth: int = MAX_DEPTH,
    max_entries: int = MAX_ENTRIES,
) -> dict | None:
    """Build a file tree dictionary from a worktree path.

    Args:
        root_path: Absolute path to the worktree root.
        max_depth: Maximum directory depth to traverse.
        max_entries: Maximum total entries to include.

    Returns:
        Dict with name, path, is_dir, children, size fields.
        None if the path doesn't exist.
    """
    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        return None

    entry_count = [0]  # Use list for mutation in nested function

    def _build(path: Path, depth: int) -> dict | None:
        if entry_count[0] >= max_entries:
            return None

        entry_count[0] += 1
        rel_path = str(path.relative_to(root))
        node = {
            "name": path.name or root_path.split("/")[-1],
            "path": rel_path if rel_path != "." else "",
            "is_dir": path.is_dir(),
        }

        if path.is_dir():
            if depth >= max_depth:
                node["children"] = []
                return node

            children = []
            try:
                entries = sorted(
                    path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
                )
                for entry in entries:
                    if entry.name in SKIP_DIRS:
                        continue
                    if entry.name.startswith(".") and entry.is_dir():
                        continue  # Skip hidden directories
                    child = _build(entry, depth + 1)
                    if child:
                        children.append(child)
            except PermissionError:
                pass

            node["children"] = children
        else:
            try:
                node["size"] = path.stat().st_size
            except OSError:
                node["size"] = 0

        return node

    return _build(root, 0)
