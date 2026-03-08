"""seed_board_configs_from_yaml

Revision ID: 0c2d89fff3b1
Revises: 82ecd978cc70
Create Date: 2026-03-01 12:00:00.000000

Seed migration: populates Board.config for all existing boards.

For each board:
  1. Load draft.yaml from board.repo_root (if it exists)
  2. Deep-merge: DraftConfig defaults ← YAML values ← existing board.config overrides
  3. Write the full merged config back to Board.config

This ensures every board has a complete, self-contained config in the DB
so the system no longer needs to read from YAML at runtime.
"""

import json
import logging
from pathlib import Path

import yaml
from sqlalchemy import text

from alembic import op

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = "0c2d89fff3b1"
down_revision: str | None = "82ecd978cc70"
branch_labels: str | None = None
depends_on: str | None = None

CONFIG_FILENAME = "draft.yaml"


def deep_merge_dicts(base: dict, override: dict) -> dict:
    """Deep merge two dicts. override wins on conflicts."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml_config(repo_root: str) -> dict | None:
    """Try to load draft.yaml from a repo root. Returns None on failure."""
    config_path = Path(repo_root) / CONFIG_FILENAME
    if not config_path.exists():
        return None
    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning("Failed to load %s: %s", config_path, e)
    return None


def _get_defaults() -> dict:
    """Build the full default config dict.

    We inline the defaults here to make the migration self-contained and
    deterministic — importing from app code could break if the dataclass
    structure changes in a future version.
    """
    return {
        "project": {
            "name": "SmartKanban Project",
            "repo_root": ".",
        },
        "execute_config": {
            "executor": "claude",
            "executor_model": "sonnet",
            "timeout": 600,
            "max_retries": 2,
            "use_yolo": False,
            "yolo_allowlist": [],
        },
        "verify_config": {
            "commands": [],
            "timeout": 300,
            "stop_on_first_failure": True,
        },
        "planner_config": {
            "enabled": False,
            "model": "anthropic/claude-sonnet-4-20250514",
            "interval_seconds": 2,
            "max_followups_per_ticket": 2,
            "max_followups_per_tick": 3,
            "reflection_enabled": True,
            "auto_verify": True,
            "max_parallel_jobs": 1,
            "features": {
                "auto_execute": False,
                "auto_followup": True,
                "auto_reflection": True,
                "validate_tickets": False,
            },
            "udar": {
                "enabled": False,
                "max_self_corrections": 3,
                "significance_threshold": 0.2,
            },
        },
        "cleanup_config": {
            "worktree_ttl_days": 7,
            "evidence_ttl_days": 30,
            "auto_cleanup_terminal": True,
        },
        "merge_config": {
            "strategy": "merge",
            "delete_branch_after_merge": True,
            "pull_before_merge": True,
            "require_pull_success": False,
        },
        "autonomy_config": {
            "enabled": False,
            "max_diff_lines": 500,
            "sensitive_file_patterns": [
                "*.env*",
                "*secret*",
                "*credential*",
                "*password*",
                "*.pem",
                "*.key",
            ],
        },
        "executor_profiles": {},
    }


def upgrade() -> None:
    """Seed Board.config for all existing boards."""
    conn = op.get_bind()

    rows = conn.execute(text("SELECT id, repo_root, config FROM boards")).fetchall()

    if not rows:
        logger.info("No boards found — nothing to seed.")
        return

    defaults = _get_defaults()
    updated = 0

    for row in rows:
        board_id = row[0]
        repo_root = row[1]
        existing_config = row[2]

        # Parse existing config (may be JSON string or dict depending on driver)
        if existing_config is None:
            existing = {}
        elif isinstance(existing_config, str):
            try:
                existing = json.loads(existing_config)
            except (json.JSONDecodeError, TypeError):
                existing = {}
        elif isinstance(existing_config, dict):
            existing = existing_config
        else:
            existing = {}

        # Try loading YAML from repo_root
        yaml_config = _load_yaml_config(repo_root) if repo_root else None

        # Deep-merge: defaults ← YAML ← existing board overrides
        merged = defaults.copy()
        if yaml_config:
            merged = deep_merge_dicts(merged, yaml_config)
        if existing:
            merged = deep_merge_dicts(merged, existing)

        # Write back
        conn.execute(
            text("UPDATE boards SET config = :config WHERE id = :id"),
            {"config": json.dumps(merged), "id": board_id},
        )
        updated += 1

        source = "defaults"
        if yaml_config and existing:
            source = "defaults + YAML + existing overrides"
        elif yaml_config:
            source = "defaults + YAML"
        elif existing:
            source = "defaults + existing overrides"
        logger.info("Board %s: seeded config from %s", board_id, source)

    logger.info("Seeded config for %d board(s).", updated)


def downgrade() -> None:
    """Revert boards to their pre-seed config state.

    We cannot perfectly restore the original state (we don't know what
    it was), so we set config to NULL which means 'use defaults'.
    This is safe because the old code path falls back to defaults anyway.
    """
    conn = op.get_bind()
    conn.execute(text("UPDATE boards SET config = NULL"))
    logger.info("Cleared Board.config for all boards (reverted to NULL/defaults).")
