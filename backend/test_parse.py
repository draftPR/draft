#!/usr/bin/env python3
"""Test parsing the agent response."""

import json
import re

# Sample agent output (based on what we saw in the stream)
agent_output = """Now I understand the context. This is the Draft backend project, and the goal is to add calculator functionality (multiplication and division) to the `app/utils` module. Based on the existing code structure and the previous ticket examples I found, I'll generate appropriate tickets.

```json
{
  "tickets": [
    {
      "title": "Test ticket",
      "description": "Test description",
      "priority_bucket": "P1",
      "priority_rationale": "Test rationale",
      "verification": ["test command"],
      "notes": "Test notes",
      "blocked_by": null
    }
  ]
}
```"""

print("Testing JSON extraction...")

# Try to extract JSON from markdown code block
json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", agent_output, re.DOTALL)
if json_match:
    json_str = json_match.group(1)
    print(f"Found JSON in markdown: {len(json_str)} chars")
    print(f"JSON preview: {json_str[:200]}...")

    try:
        data = json.loads(json_str)
        print("✅ Parsed successfully!")
        print(f"Tickets: {len(data.get('tickets', []))}")
        for ticket in data.get("tickets", []):
            print(f"  - {ticket.get('title')}")
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
else:
    print("❌ No JSON found in markdown block")

# Also try parsing the full output
try:
    data = json.loads(agent_output)
    print(f"✅ Direct parse successful: {len(data.get('tickets', []))} tickets")
except:
    print("❌ Direct parse failed (expected)")
