#!/usr/bin/env python3
"""Seed the database with demo data for first-time users.

This script creates:
- A demo board pointing to the demo-repo
- Demo goals with realistic descriptions (no pre-seeded tickets)
- Ready for live ticket generation demo

Run with: python -m scripts.seed_demo
"""

import asyncio
import sys
import uuid
from pathlib import Path

import yaml

# Add backend to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.database import async_session_maker, init_db
from app.models.board import Board
from app.models.goal import Goal
from app.services.config_service import SmartKanbanConfig

BOARD_ID = "demo-board"


def _load_demo_config(demo_repo_path: Path) -> dict:
    """Load demo-repo/smartkanban.yaml and set dynamic paths.

    Reads the YAML config and sets the yolo_allowlist to the actual
    demo-repo path so it works on any machine.
    """
    yaml_path = demo_repo_path / "smartkanban.yaml"
    if yaml_path.exists():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    # Parse through SmartKanbanConfig for proper defaults, then convert back
    config = SmartKanbanConfig.from_dict(raw)
    config_dict = config.to_dict()

    # Set yolo_allowlist dynamically to the resolved demo-repo path
    config_dict["execute_config"]["yolo_allowlist"] = [str(demo_repo_path)]

    return config_dict


async def seed_demo_data():
    """Seed the database with demo board and goals (no tickets).

    Creates a clean board with goals ready for live ticket generation.
    """
    await init_db()

    async with async_session_maker() as session:
        # Check if demo board already exists
        result = await session.execute(select(Board).where(Board.id == BOARD_ID))
        existing_board = result.scalar_one_or_none()

        if existing_board:
            print("Demo board already exists, skipping seed.")
            print("Run with --clear first to reset.")
            return

        # Get the project root (where demo-repo lives)
        project_root = Path(__file__).parent.parent.parent.resolve()
        demo_repo_path = project_root / "demo-repo"

        if not demo_repo_path.exists():
            print(f"ERROR: demo-repo not found at {demo_repo_path}")
            return

        # Load demo config from smartkanban.yaml and set dynamic yolo_allowlist
        board_config = _load_demo_config(demo_repo_path)

        # Create demo board
        demo_board = Board(
            id=BOARD_ID,
            name="Calculator Bug Fix",
            description=(
                "A simple calculator app with intentional bugs. "
                "Use the goals below to generate tickets and watch AI fix everything."
            ),
            repo_root=str(demo_repo_path),
            default_branch="main",
            config=board_config,
        )
        session.add(demo_board)

        # --- Goals (no tickets - generate them live!) ---

        goals = [
            Goal(
                id=str(uuid.uuid4()),
                board_id=BOARD_ID,
                title="Fix all calculator bugs",
                description=(
                    "The calculator has three critical bugs that crash the app:\n"
                    "\n"
                    "1. Division by zero - divide() raises ZeroDivisionError\n"
                    "2. Negative square root - square_root() raises ValueError\n"
                    "3. Modulo by zero - modulo() raises ZeroDivisionError\n"
                    "\n"
                    "Each bug needs proper error handling that returns a clear\n"
                    "error message instead of crashing. Add tests for each fix."
                ),
            ),
            Goal(
                id=str(uuid.uuid4()),
                board_id=BOARD_ID,
                title="Add missing calculator features",
                description=(
                    "The calculator is missing several features marked as TODOs:\n"
                    "\n"
                    "- percentage(value, percent) - calculate percentage of a value\n"
                    "- factorial(n) - compute n! iteratively\n"
                    "- logarithm(x, base) - compute log with given base\n"
                    "\n"
                    "Each new method needs input validation and tests."
                ),
            ),
        ]

        for goal in goals:
            session.add(goal)

        await session.commit()

        print("Demo data seeded successfully!")
        print()
        print(f"  Board: {demo_board.name} (ID: {BOARD_ID})")
        print(f"  Repo:  {demo_board.repo_root}")
        print(f"  Goals: {len(goals)}")
        for g in goals:
            print(f"    - {g.title}")
        print()
        print("Next Steps:")
        print("  1. make run")
        print("  2. Open http://localhost:5173")
        print("  3. Select the 'Calculator Bug Fix' board")
        print("  4. Click a goal -> 'Generate Tickets'")
        print()


async def clear_demo_data():
    """Clear demo data (useful for resetting)."""
    await init_db()

    async with async_session_maker() as session:
        result = await session.execute(select(Board).where(Board.id == BOARD_ID))
        demo_board = result.scalar_one_or_none()

        if demo_board:
            await session.delete(demo_board)
            await session.commit()
            print("Demo data cleared.")
        else:
            print("No demo data found.")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Seed demo data for Draft")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing demo data instead of seeding",
    )
    args = parser.parse_args()

    if args.clear:
        asyncio.run(clear_demo_data())
    else:
        asyncio.run(seed_demo_data())


if __name__ == "__main__":
    main()
