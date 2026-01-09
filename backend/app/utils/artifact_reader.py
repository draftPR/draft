"""Safe artifact reading utilities.

Security Policy:
    - Only reads files under <repo_root>/.smartkanban
    - Rejects absolute paths
    - Resolves canonical paths (follows symlinks)
    - Caps file size to prevent memory exhaustion
"""

import os
from pathlib import Path

# Maximum artifact file size to read (2MB)
MAX_ARTIFACT_BYTES = 2_000_000


def read_artifact(repo_root: Path, relpath: str | None) -> str | None:
    """Safely read an artifact file, enforcing security constraints.

    Security Policy:
        - Rejects absolute paths
        - Resolves canonical path (follows symlinks)
        - Enforces file is under <repo_root>/.smartkanban
        - Caps file size to prevent memory exhaustion

    Args:
        repo_root: Absolute path to the repository root
        relpath: Relative path to the artifact (from DB)

    Returns:
        File content if safe and exists, None otherwise
    """
    if not relpath:
        return None

    rel = Path(relpath)

    # SECURITY: Reject absolute paths - DB should only store relative paths
    if rel.is_absolute():
        return None

    # Resolve allowed root to canonical absolute path
    allowed_root = (repo_root / ".smartkanban").resolve(strict=False)

    # Resolve target to canonical absolute path (follows symlinks)
    target = (repo_root / rel).resolve(strict=False)

    # SECURITY: Enforce target is under allowed_root using commonpath
    try:
        common = os.path.commonpath([str(target), str(allowed_root)])
    except ValueError:
        # Different drives on Windows or no common path
        return None

    if common != str(allowed_root):
        return None

    # Check file exists and is a regular file
    if not target.is_file():
        return None

    # Read with size cap to prevent memory exhaustion
    try:
        size = target.stat().st_size
        if size > MAX_ARTIFACT_BYTES:
            with target.open("rb") as f:
                data = f.read(MAX_ARTIFACT_BYTES)
            return data.decode("utf-8", errors="replace") + "\n\n[truncated]"
        return target.read_text(encoding="utf-8", errors="replace")
    except (OSError, IOError):
        return None


