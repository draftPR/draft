#!/usr/bin/env python3
"""Test script to verify streaming callback works."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import get_db
from app.services.ticket_generation_service import TicketGenerationService

async def test_streaming():
    """Test streaming callback."""
    print("Testing streaming...")

    # Get DB session
    async for db in get_db():
        service = TicketGenerationService(db)

        # Goal ID from earlier
        goal_id = "b7e723f4-030f-45d9-8c6b-eae97fd5d72f"

        received_lines = []

        def stream_callback(line: str):
            print(f"CALLBACK: {line}")
            received_lines.append(line)

        try:
            result = await service.generate_from_goal(
                goal_id=goal_id,
                include_readme=False,
                validate_tickets=False,  # Skip validation for test
                stream_callback=stream_callback,
            )

            print(f"\nReceived {len(received_lines)} lines from agent")
            print(f"Generated {len(result.tickets)} tickets")

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_streaming())
