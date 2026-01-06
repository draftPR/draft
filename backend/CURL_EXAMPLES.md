# Smart Kanban API - Example curl Commands

This document provides example curl commands to interact with the Smart Kanban API.

## Prerequisites

Start the backend server:

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

## Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "ok"}
```

## Goals

### Create a Goal

```bash
curl -X POST http://localhost:8000/goals \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Implement User Authentication",
    "description": "Add login, registration, and session management to the application"
  }'
```

Expected response:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Implement User Authentication",
  "description": "Add login, registration, and session management to the application",
  "created_at": "2026-01-05T10:00:00",
  "updated_at": "2026-01-05T10:00:00"
}
```

### List All Goals

```bash
curl http://localhost:8000/goals
```

Expected response:
```json
{
  "goals": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "Implement User Authentication",
      "description": "Add login, registration, and session management to the application",
      "created_at": "2026-01-05T10:00:00",
      "updated_at": "2026-01-05T10:00:00"
    }
  ],
  "total": 1
}
```

### Get a Single Goal

```bash
curl http://localhost:8000/goals/{goal_id}
```

Replace `{goal_id}` with the actual goal UUID.

## Tickets

### Create a Ticket

```bash
curl -X POST http://localhost:8000/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "goal_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Design login form UI",
    "description": "Create a responsive login form with email and password fields",
    "priority": 80,
    "actor_type": "human",
    "actor_id": "user-123"
  }'
```

Expected response:
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "goal_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Design login form UI",
  "description": "Create a responsive login form with email and password fields",
  "state": "proposed",
  "priority": 80,
  "created_at": "2026-01-05T10:05:00",
  "updated_at": "2026-01-05T10:05:00"
}
```

### Get a Ticket

```bash
curl http://localhost:8000/tickets/{ticket_id}
```

Replace `{ticket_id}` with the actual ticket UUID.

### Transition a Ticket (Valid)

Move from `proposed` to `planned`:

```bash
curl -X POST http://localhost:8000/tickets/{ticket_id}/transition \
  -H "Content-Type: application/json" \
  -d '{
    "to_state": "planned",
    "actor_type": "planner",
    "actor_id": "ai-planner-1",
    "reason": "Task has been reviewed and broken down"
  }'
```

Expected response (ticket with updated state):
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "goal_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Design login form UI",
  "description": "Create a responsive login form with email and password fields",
  "state": "planned",
  "priority": 80,
  "created_at": "2026-01-05T10:05:00",
  "updated_at": "2026-01-05T10:10:00"
}
```

### Complete Workflow: proposed → planned → executing → verifying → done

```bash
# Start executing (planned → executing)
curl -X POST http://localhost:8000/tickets/{ticket_id}/transition \
  -H "Content-Type: application/json" \
  -d '{
    "to_state": "executing",
    "actor_type": "executor",
    "actor_id": "ai-executor-1",
    "reason": "Starting implementation"
  }'

# Submit for verification (executing → verifying)
curl -X POST http://localhost:8000/tickets/{ticket_id}/transition \
  -H "Content-Type: application/json" \
  -d '{
    "to_state": "verifying",
    "actor_type": "executor",
    "actor_id": "ai-executor-1",
    "reason": "Implementation complete, ready for review"
  }'

# Mark as done (verifying → done)
curl -X POST http://localhost:8000/tickets/{ticket_id}/transition \
  -H "Content-Type: application/json" \
  -d '{
    "to_state": "done",
    "actor_type": "human",
    "actor_id": "user-123",
    "reason": "Verified and approved"
  }'
```

### Transition a Ticket (Invalid - Should Fail)

Try to go directly from `proposed` to `done`:

```bash
curl -X POST http://localhost:8000/tickets/{ticket_id}/transition \
  -H "Content-Type: application/json" \
  -d '{
    "to_state": "done",
    "actor_type": "human",
    "actor_id": "user-123",
    "reason": "Trying to skip states"
  }'
```

Expected error response (HTTP 400):
```json
{
  "detail": "Invalid transition from 'proposed' to 'done'",
  "error_type": "invalid_state_transition",
  "from_state": "proposed",
  "to_state": "done"
}
```

### Get Ticket Events (Audit Log)

```bash
curl http://localhost:8000/tickets/{ticket_id}/events
```

Expected response:
```json
{
  "events": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440001",
      "ticket_id": "660e8400-e29b-41d4-a716-446655440001",
      "event_type": "created",
      "from_state": null,
      "to_state": "proposed",
      "actor_type": "human",
      "actor_id": "user-123",
      "reason": "Ticket created",
      "payload": {
        "title": "Design login form UI",
        "description": "Create a responsive login form with email and password fields",
        "goal_id": "550e8400-e29b-41d4-a716-446655440000",
        "priority": 80
      },
      "created_at": "2026-01-05T10:05:00"
    },
    {
      "id": "770e8400-e29b-41d4-a716-446655440002",
      "ticket_id": "660e8400-e29b-41d4-a716-446655440001",
      "event_type": "transitioned",
      "from_state": "proposed",
      "to_state": "planned",
      "actor_type": "planner",
      "actor_id": "ai-planner-1",
      "reason": "Task has been reviewed and broken down",
      "payload": null,
      "created_at": "2026-01-05T10:10:00"
    }
  ],
  "total": 2
}
```

## Board View

### Get Board (All Tickets Grouped by State)

```bash
curl http://localhost:8000/board
```

Expected response:
```json
{
  "columns": [
    {
      "state": "proposed",
      "tickets": []
    },
    {
      "state": "planned",
      "tickets": [
        {
          "id": "660e8400-e29b-41d4-a716-446655440001",
          "goal_id": "550e8400-e29b-41d4-a716-446655440000",
          "title": "Design login form UI",
          "description": "Create a responsive login form",
          "state": "planned",
          "priority": 80,
          "created_at": "2026-01-05T10:05:00",
          "updated_at": "2026-01-05T10:10:00"
        }
      ]
    },
    {
      "state": "executing",
      "tickets": []
    },
    {
      "state": "verifying",
      "tickets": []
    },
    {
      "state": "needs_human",
      "tickets": []
    },
    {
      "state": "blocked",
      "tickets": []
    },
    {
      "state": "done",
      "tickets": []
    },
    {
      "state": "abandoned",
      "tickets": []
    }
  ],
  "total_tickets": 1
}
```

## State Machine Reference

### Valid State Transitions

| From State    | Valid Next States                        |
|---------------|------------------------------------------|
| proposed      | planned, abandoned                       |
| planned       | executing, blocked, abandoned            |
| executing     | verifying, needs_human, blocked          |
| verifying     | done, executing, needs_human             |
| needs_human   | executing, planned, abandoned            |
| blocked       | planned, abandoned                       |
| done          | (terminal state - no transitions)        |
| abandoned     | (terminal state - no transitions)        |

### Actor Types

- `human` - Human user action
- `planner` - AI planner agent
- `executor` - AI executor agent
- `system` - Automated system action

