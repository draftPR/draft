"""Safe artifact reading utilities.

Security Policy:
    - Only reads files under central data dir or <repo_root>/.smartkanban (legacy)
    - Rejects absolute paths (unless under central data dir)
    - Resolves canonical paths (follows symlinks)
    - Caps file size to prevent memory exhaustion
"""

import os
from pathlib import Path

# Maximum artifact file size to read (2MB)
MAX_ARTIFACT_BYTES = 2_000_000


def _is_under(target: Path, allowed_root: Path) -> bool:
    """Check if target path is under allowed_root using canonical paths."""
    try:
        common = os.path.commonpath(
            [str(target.resolve(strict=False)), str(allowed_root.resolve(strict=False))]
        )
    except ValueError:
        return False
    return common == str(allowed_root.resolve(strict=False))


def _read_with_cap(target: Path) -> str | None:
    """Read a file with size cap to prevent memory exhaustion."""
    if not target.is_file():
        return None
    try:
        size = target.stat().st_size
        if size > MAX_ARTIFACT_BYTES:
            with target.open("rb") as f:
                data = f.read(MAX_ARTIFACT_BYTES)
            return data.decode("utf-8", errors="replace") + "\n\n[truncated]"
        return target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def read_artifact(repo_root: Path, relpath: str | None) -> str | None:
    """Safely read an artifact file, enforcing security constraints.

    Security Policy:
        - Accepts absolute paths under central data dir (~/.telem/)
        - Accepts relative paths under <repo_root>/.smartkanban (legacy)
        - Resolves canonical path (follows symlinks)
        - Caps file size to prevent memory exhaustion

    Args:
        repo_root: Absolute path to the repository root
        relpath: Path to the artifact (absolute under data dir, or relative)

    Returns:
        File content if safe and exists, None otherwise
    """
    if not relpath:
        return None

    from app.data_dir import get_data_dir

    rel = Path(relpath)

    # If absolute path, check if it's under the central data dir
    if rel.is_absolute():
        data_dir = get_data_dir()
        if _is_under(rel, data_dir):
            return _read_with_cap(rel)
        return None

    # Try central data dir first (new paths)
    data_dir = get_data_dir()
    target = (data_dir / rel).resolve(strict=False)
    if _is_under(target, data_dir):
        result = _read_with_cap(target)
        if result is not None:
            return result

    # Fall back to legacy <repo_root>/.smartkanban
    allowed_root = (repo_root / ".smartkanban").resolve(strict=False)
    target = (repo_root / rel).resolve(strict=False)
    if _is_under(target, allowed_root):
        return _read_with_cap(target)

    return None
