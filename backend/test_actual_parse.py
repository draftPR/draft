#!/usr/bin/env python3
"""Test parsing the actual agent response."""

import json
import re
import sys

sys.path.insert(0, '.')

# Read the actual agent response
with open('/tmp/tmpi59wry37_agent_response.txt') as f:
    response = f.read()

print(f"Response length: {len(response)} chars")
print(f"First 200 chars: {response[:200]}")
print()

# Try to find JSON in code blocks first (same logic as the service)
json_block_pattern = r"```(?:json)?\s*(\{[\s\S]*?\})\s*```"
matches = re.findall(json_block_pattern, response)

print(f"Found {len(matches)} JSON blocks")

for i, match in enumerate(matches, 1):
    print(f"\nBlock {i} length: {len(match)} chars")
    print(f"First 100 chars: {match[:100]}")

    try:
        data = json.loads(match)
        if "tickets" in data:
            print("✅ Valid JSON with tickets!")
            print(f"Tickets: {len(data['tickets'])}")
            for ticket in data['tickets']:
                print(f"  - {ticket.get('title', 'NO TITLE')[:80]}")
        else:
            print("❌ JSON valid but no 'tickets' key")
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        print(f"Error at position {e.pos}")
        if e.pos < len(match):
            print(f"Context: ...{match[max(0, e.pos-50):e.pos+50]}...")
