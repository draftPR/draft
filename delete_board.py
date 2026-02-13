#!/usr/bin/env python3
"""
Script to delete a board and all its associated data.

Usage:
    cd backend && source venv/bin/activate
    python ../delete_board.py <board_id>
    python ../delete_board.py --list  # List all boards

WARNING: This will permanently delete:
- The board
- All goals in the board
- All tickets (and their jobs, revisions, workspaces, evidence)
- All associated data

This action CANNOT be undone!
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models.board import Board
from app.database_sync import get_database_url


def list_boards():
    """List all boards."""
    engine = create_engine(get_database_url())

    with Session(engine) as session:
        result = session.execute(select(Board))
        boards = result.scalars().all()

        if not boards:
            print("No boards found.")
            return

        print("\nAvailable boards:")
        print("-" * 80)
        for board in boards:
            print(f"ID: {board.id}")
            print(f"Name: {board.name}")
            if board.description:
                print(f"Description: {board.description}")
            print(f"Repo: {board.repo_root}")
            print("-" * 80)


def delete_board(board_id: str):
    """Delete a board and all its associated data."""
    engine = create_engine(get_database_url())

    with Session(engine) as session:
        # Find the board
        result = session.execute(select(Board).where(Board.id == board_id))
        board = result.scalar_one_or_none()

        if not board:
            print(f"❌ Error: Board '{board_id}' not found.")
            print("\nUse --list to see available boards.")
            sys.exit(1)

        # Show board info
        print(f"\n⚠️  WARNING: You are about to DELETE board:")
        print("-" * 80)
        print(f"ID: {board.id}")
        print(f"Name: {board.name}")
        if board.description:
            print(f"Description: {board.description}")
        print(f"Repo: {board.repo_root}")
        print("-" * 80)

        # Count related data
        from app.models.goal import Goal
        from app.models.ticket import Ticket
        from app.models.job import Job

        goal_count = session.execute(
            select(Goal).where(Goal.board_id == board_id)
        ).scalars().all()

        ticket_count = session.execute(
            select(Ticket).where(Ticket.board_id == board_id)
        ).scalars().all()

        job_count = session.execute(
            select(Job).where(Job.board_id == board_id)
        ).scalars().all()

        print(f"\nThis will delete:")
        print(f"  • {len(goal_count)} goal(s)")
        print(f"  • {len(ticket_count)} ticket(s)")
        print(f"  • {len(job_count)} job(s)")
        print(f"  • All revisions, workspaces, and evidence files")
        print(f"\n⚠️  THIS ACTION CANNOT BE UNDONE!")

        # Confirm deletion
        print(f"\nTo confirm, type the board ID: {board.id}")
        confirmation = input("Board ID: ").strip()

        if confirmation != board.id:
            print("\n❌ Deletion cancelled - board ID did not match.")
            sys.exit(1)

        # Delete the board (cascade will handle related records)
        print(f"\n🗑️  Deleting board '{board.name}'...")
        session.delete(board)
        session.commit()

        print(f"✅ Board '{board.name}' has been deleted successfully.")
        print("\nNote: Worktree directories must be cleaned up manually if needed:")
        print(f"  git worktree list")
        print(f"  git worktree remove <path>")


def main():
    if len(sys.argv) < 2:
        print("Delete Board Script")
        print("-" * 80)
        print("Usage:")
        print("  cd backend && source venv/bin/activate")
        print("  python ../delete_board.py <board_id>")
        print("  python ../delete_board.py --list")
        print("\nFirst activate the backend virtual environment before running this script.")
        sys.exit(1)

    if sys.argv[1] == "--list":
        list_boards()
    else:
        board_id = sys.argv[1]
        delete_board(board_id)


if __name__ == "__main__":
    main()
