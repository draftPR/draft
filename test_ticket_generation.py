#!/usr/bin/env python3
"""
Test script to debug ticket generation issues.

Usage:
    cd backend && source venv/bin/activate
    python ../test_ticket_generation.py <goal_id>
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

async def test_generation(goal_id: str):
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.services.ticket_generation_service import TicketGenerationService
    from app.services.config_service import ConfigService
    from app.database import get_database_url

    # Create async engine
    engine = create_async_engine(get_database_url())
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        service = TicketGenerationService(session)
        config = ConfigService().load_config()
        repo_root = Path(config.project.repo_root)

        print(f"\n{'='*80}")
        print(f"Testing Ticket Generation for Goal: {goal_id}")
        print(f"Repo Root: {repo_root}")
        print(f"Agent Path: {config.get_agent_path()}")
        print(f"Validation Enabled: {config.planner_config.features.validate_tickets}")
        print(f"{'='*80}\n")

        try:
            result = await service.generate_from_goal(
                goal_id=goal_id,
                repo_root=repo_root,
                include_readme=False,
                validate_tickets=False,  # Disable validation for testing
            )

            print(f"\n{'='*80}")
            print(f"RESULT: Generated {len(result.tickets)} tickets")
            print(f"{'='*80}\n")

            if len(result.tickets) == 0:
                print("❌ No tickets generated!")
                print("\nTroubleshooting:")
                print("1. Check if the agent CLI is working:")
                print(f"   {config.get_agent_path()} --version")
                print("2. Check if the goal exists in the database")
                print("3. Check backend logs for errors")
            else:
                for i, ticket in enumerate(result.tickets, 1):
                    print(f"{i}. {ticket.title}")
                    print(f"   Priority: {ticket.priority_bucket.value} ({ticket.priority})")
                    if ticket.description:
                        print(f"   Description: {ticket.description[:100]}...")
                    print()

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_ticket_generation.py <goal_id>")
        print("\nTo find goal IDs:")
        print("  cd backend && source venv/bin/activate")
        print("  python -c 'from app.database_sync import *; from app.models.goal import Goal; from sqlalchemy import create_engine, select; from sqlalchemy.orm import Session; engine = create_engine(get_database_url()); session = Session(engine); print(\"\\n\".join([f\"{g.id}: {g.title}\" for g in session.execute(select(Goal)).scalars().all()]))'")
        sys.exit(1)

    goal_id = sys.argv[1]
    asyncio.run(test_generation(goal_id))
