# Draft SDK

Python SDK for [Draft](https://trydraft.dev) — the AI-powered kanban board for autonomous code delivery.

## Install

```bash
pip install draft-sdk
```

## Quick Start

```python
from draft_sdk import DraftClient

client = DraftClient("http://localhost:8000")

# One-liner: create goal → generate tickets → execute → wait for completion
result = client.run_goal("Add dark mode support", auto_approve=True, wait=True)
print(f"Status: {result.status}, Tickets: {len(result.tickets)}")
```

## Granular Control

```python
from draft_sdk import DraftClient

client = DraftClient("http://localhost:8000")

# Create a goal
goal = client.goals.create(title="Add user auth", board_id="your-board-id")

# Generate tickets from the goal
tickets = client.goals.generate_tickets(goal.id)

# Approve specific tickets
good = [t.id for t in tickets if t.priority and t.priority >= 50]
client.tickets.accept(good)

# Execute and wait for each ticket
for tid in good:
    job = client.tickets.execute(tid)
    done = client.jobs.wait(job.id, timeout=600)
    print(f"Job {done.id}: {done.status}")

# Review revisions
for tid in good:
    revisions = client.revisions.list(tid)
    if revisions:
        diff = client.revisions.get_diff(revisions[0].id)
        client.revisions.review(revisions[0].id, decision="approved")
```

## Progress Tracking

```python
def on_progress(event, data):
    print(f"[{event}] {data}")

result = client.run_goal(
    "Refactor auth module",
    auto_approve=True,
    on_progress=on_progress,
)
```

## Resources

- `client.boards` — Board management
- `client.goals` — Goal CRUD + ticket generation
- `client.tickets` — Ticket CRUD + state transitions + execution
- `client.jobs` — Job monitoring + logs + wait
- `client.revisions` — Code review + diffs + comments
- `client.planner` — Autopilot control

## Documentation

Full docs at [docs.trydraft.dev/sdk/overview](https://docs.trydraft.dev/sdk/overview)

## License

BSL-1.1 — see [LICENSE](../LICENSE) for details.
