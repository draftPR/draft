#!/usr/bin/env python3
"""Seed the database with demo data for first-time users.

This script creates:
- A demo board pointing to the demo-repo
- A demo goal with realistic description
- Pre-configured for immediate evaluation

Run with: python -m scripts.seed_demo
"""

import asyncio
import sys
import uuid
from pathlib import Path

# Add backend to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.database import async_session_maker, init_db
from app.models.board import Board
from app.models.goal import Goal


async def seed_demo_data():
    """Seed the database with demo board and goal."""

    # Initialize database (create tables if needed)
    await init_db()

    async with async_session_maker() as session:
        # Check if demo board already exists
        result = await session.execute(
            select(Board).where(Board.id == "demo-board")
        )
        existing_board = result.scalar_one_or_none()

        if existing_board:
            print("✅ Demo board already exists, skipping seed.")
            return

        # Get the project root (where demo-repo lives)
        project_root = Path(__file__).parent.parent.parent.resolve()
        demo_repo_path = project_root / "demo-repo"

        # Create demo board
        demo_board = Board(
            id="demo-board",
            name="Demo Calculator Project",
            description=(
                "A demonstration board showing Alma Kanban's autonomous delivery system. "
                "This board contains a simple calculator app with intentional bugs and TODOs."
            ),
            repo_root=str(demo_repo_path),
            default_branch="main",
        )
        session.add(demo_board)

        # Create demo goal
        demo_goal = Goal(
            id=str(uuid.uuid4()),
            board_id="demo-board",
            title="Fix the calculator bugs and add missing tests",
            description="""The demo calculator app has several critical bugs and missing features:

**Bugs to Fix:**
1. **Division by zero crashes** - `divide()` method has no error handling
2. **Negative square root crashes** - `square_root()` doesn't validate input
3. **Modulo by zero crashes** - `modulo()` method lacks error handling

**Test Coverage Gaps:**
- No tests for division by zero edge case
- No tests for negative square root input
- No tests for modulo by zero
- Missing tests for error messages

**TODOs to Implement:**
- Add percentage calculation method
- Add factorial calculation method
- Add logarithm calculation method
- Improve input parsing in utils.py

**Acceptance Criteria:**
- All division operations properly handle zero divisor
- Square root validates non-negative input
- Comprehensive test coverage (>90%)
- All existing tests continue to pass
- Error messages are user-friendly

**Codebase Context:**
- Main calculator logic: `src/calculator.py`
- Utility functions: `src/utils.py`
- Test suite: `tests/test_calculator.py`
- Python project with pytest for testing

This is a realistic but constrained problem - perfect for demonstrating Alma Kanban's end-to-end autonomous delivery pipeline!
""",
        )
        session.add(demo_goal)

        # Commit the demo data
        await session.commit()

        print("✅ Demo data seeded successfully!")
        print()
        print("Demo Board Details:")
        print(f"  ID: {demo_board.id}")
        print(f"  Name: {demo_board.name}")
        print(f"  Repo: {demo_board.repo_root}")
        print()
        print("Demo Goal Details:")
        print(f"  ID: {demo_goal.id}")
        print(f"  Title: {demo_goal.title}")
        print()
        print("Next Steps:")
        print("  1. Start Alma Kanban: docker compose up")
        print("  2. Open UI: http://localhost:3000")
        print("  3. Look for the demo goal and click 'Generate Tickets'")
        print("  4. Watch autonomous execution!")
        print()


async def clear_demo_data():
    """Clear demo data (useful for resetting)."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(Board).where(Board.id == "demo-board")
        )
        demo_board = result.scalar_one_or_none()

        if demo_board:
            await session.delete(demo_board)
            await session.commit()
            print("✅ Demo data cleared.")
        else:
            print("ℹ️  No demo data found.")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Seed demo data for Alma Kanban")
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
