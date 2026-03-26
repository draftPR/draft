# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Draft is an AI-powered local-first kanban board that uses AI agents to automatically implement tickets. It creates isolated git worktrees for each ticket, runs AI code tools (Claude CLI, Cursor Agent, Codex, or Gemini) to implement changes, verifies the changes, and manages the workflow through a state machine. Supports **multi-agent team execution** where specialized agent roles (Team Lead, PM, Developer, Code Reviewer, QA, etc.) collaborate via tmux sessions and an inter-agent message board.

**Tech Stack:**
- Backend: FastAPI + SQLAlchemy (async) + SQLite
- Frontend: React + Vite + TypeScript + Tailwind CSS + shadcn/ui
- Database: SQLite with Alembic migrations
- Background Jobs: In-process SQLiteWorker (ThreadPoolExecutor)
- AI Executors: Claude Code CLI, Cursor Agent CLI, Codex, Gemini
- Multi-Agent: tmux-based orchestration with PULSE status protocol

## Development Commands

```bash
make setup              # Install all dependencies (backend venv + frontend npm)
make run                # Start backend + frontend (2 processes)
make db-migrate         # Run Alembic migrations (alembic upgrade head)
make lint               # Run ruff (backend) + ESLint (frontend)
make format             # Format with ruff + Prettier

# Manual service startup (2 terminals)
make dev-backend        # Terminal 1: FastAPI at http://localhost:8000
make dev-frontend       # Terminal 2: Vite at http://localhost:5173

# Testing
cd backend && source venv/bin/activate
pytest tests -v                            # All tests
pytest tests/test_middleware.py -v          # Specific file
pytest tests/test_middleware.py::test_name -v  # Specific test

# Database migrations
cd backend && source venv/bin/activate
alembic revision --autogenerate -m "description"
alembic upgrade head

# Health checks
curl http://localhost:8000/health
```

API docs auto-generated at http://localhost:8000/docs

## High-Level Architecture

### State Machine & Ticket Lifecycle

Tickets flow through a strict state machine defined in `backend/app/state_machine.py`:

```
PROPOSED → PLANNED → EXECUTING → VERIFYING → NEEDS_HUMAN → DONE
              ↓           ↓           ↓            ↓          ↓
           BLOCKED    BLOCKED     BLOCKED     ABANDONED  (can go back to EXECUTING)
              ↓
          ABANDONED
```

- `PROPOSED`: New ticket, awaiting human review
- `PLANNED`: Approved, ready to execute
- `EXECUTING`: AI agent actively implementing changes
- `VERIFYING`: Running verification commands (tests, lints)
- `NEEDS_HUMAN`: Awaiting human review/approval
- `BLOCKED`: Execution or verification failed
- `DONE` / `ABANDONED`: Terminal states (worktrees auto-cleaned)

Always validate transitions before applying:
```python
from app.state_machine import validate_transition
if not validate_transition(ticket.state, new_state):
    raise InvalidStateTransitionError(ticket.state, new_state)
```

### Ticket Dependencies (DAG)

Tickets can depend on each other via `blocked_by_ticket_id` (self-referential FK on Ticket model):
- A ticket cannot execute until its blocker reaches `DONE`
- `ticket.is_blocked_by_dependency` property checks blocker status
- Planner auto-blocks tickets with incomplete dependencies and auto-unblocks when dependencies complete
- `DeliveryPipeline` uses **Kahn's algorithm** for topological sort with cycle detection (falls back to original order on cycles)
- Dependencies enforced at planner level via `BLOCKED` state, not at job creation

### Git Worktree Isolation

Each ticket gets its own isolated git worktree for parallel execution:
- Worktrees: `.draft/worktrees/{ticket_id}/`
- Branches: `goal/{goal_id}/ticket/{ticket_id}`
- Logs: `{worktree_path}/.draft/logs/{job_id}.log`
- Auto-cleaned when tickets reach terminal states

Key services: `WorkspaceService` (creates worktrees), `WorktreeValidator` (validates safety), `CleanupService` (removes stale worktrees)

### Background Job System

Jobs run in-process via `SQLiteWorker` (ThreadPoolExecutor + SQLite job queue):

1. Frontend/planner calls `POST /tickets/{id}/run` or `/verify`
2. Backend creates Job record (`QUEUED`) and enqueues into `job_queue` table
3. SQLiteWorker polls, claims task, runs in isolated worktree, streams logs via in-memory broadcaster
4. Job transitions: `QUEUED → RUNNING → SUCCEEDED/FAILED/CANCELED`
5. Job results trigger ticket state transitions

Key files: `worker.py` (task implementations), `sqlite_worker.py` (job runner + periodic scheduler), `task_dispatch.py` (enqueue), `job_service.py` (CRUD), `job_watchdog_service.py` (auto-cancels stuck jobs)

**Periodic tasks** (run by SQLiteWorker scheduler): job watchdog (15s), planner tick (2s), PR status polling (5min).

### AI Executor System

Multiple AI code executors via `executor_service.py`:
- `CLAUDE`: Claude Code CLI (headless, recommended)
- `CURSOR_AGENT`: Cursor Agent CLI (headless)
- `CURSOR`: Cursor IDE CLI (interactive → `NEEDS_HUMAN` immediately)
- `CODEX`: OpenAI Codex CLI
- `GEMINI`: Google Gemini CLI

State transitions after execution:
- Headless success with diff → `VERIFYING`
- Headless success with NO diff → `BLOCKED` (reason: "no changes")
- Headless failure → `BLOCKED`

**YOLO Mode:** When enabled in `draft.yaml`, Claude CLI runs with `--dangerously-skip-permissions`. Only runs if `yolo_allowlist` has trusted repo paths.

### Multi-Agent Team Execution

When a board has an active agent team, ticket execution uses **tmux-based multi-agent orchestration** instead of a single executor. Inspired by Coral's architecture.

**Agent Roles (14 available):** Team Lead (orchestrator, required), PM, Code Explorer, Developer, Code Reviewer, QA Engineer, Frontend Dev, Backend Dev, LLM Expert, ML Engineer, Prompt Engineer, DevOps Engineer, Security Engineer, Database Expert.

**Presets:** `default` (6 agents), `duo` (2), `full_stack` (7), `ml_pipeline` (7), `security_audit` (5).

**How it works:**
1. Worker detects active team via `_get_active_team()` in `worker.py`
2. `TeamSessionService` launches one tmux session per team member
3. Each agent gets a role-specific behavior prompt + the ticket context
4. Team Lead (orchestrator) receives all messages; others receive only directed messages
5. Agents communicate via `board-cli.sh` → `POST /boards/{id}/messages` (message board)
6. Status tracked via PULSE protocol: `||PULSE:STATUS working||` tags in agent output
7. Worker polls tmux sessions every 30s, checks for completion signals
8. When Team Lead posts `DONE:`, worker collects diff and transitions ticket

**Key files:**
- `agent_catalog.py`: Role definitions, prompts, presets
- `tmux_manager.py`: Session lifecycle (create, kill, capture output)
- `team_session_service.py`: Launch/monitor agent teams
- `message_board_service.py`: Inter-agent messaging (cursor-based reads)
- `board_cli_service.py`: Shell script injected into worktrees
- `agent_hooks_service.py`: Claude Code hooks for board check-ins
- `routers/agent_team.py`: REST API for team CRUD
- `routers/message_board.py`: REST API for messaging

**Per-member executor:** Each team member can use a different executor (Claude, Cursor, Codex, Gemini) configured in the UI.

**Important:** Don't run the backend with `--reload` during team execution — HMR kills the worker's polling loop mid-execution.

### Verification Pipeline

After execution, verification commands from `draft.yaml` run sequentially in the worktree:
- Each command's stdout/stderr captured as `Evidence` records
- All pass → `NEEDS_HUMAN`; any fail → `BLOCKED`
- Stop on first failure

### Revision & Review System

Revisions are PR-like artifacts (NOT git commits) tracking each agent iteration:
- One revision per execute job, incrementally numbered per ticket
- Status: `open` → `changes_requested` → `approved` → `superseded`
- New revision supersedes previous open one
- Diffs stored as immutable Evidence (stat + patch)
- `ReviewComment` for line-level comments, `ReviewSummary` for final decision
- Approval enables transition to DONE; changes_requested returns to EXECUTING

### Board & Multi-Tenancy

Boards are permission boundaries scoping all operations to a single repo:
- `board.repo_root` is the authoritative path for ALL file operations (never use client-provided paths)
- Goals, Tickets, Jobs, Workspaces all scoped by `board_id`
- Cascade deletes: Board → Goals → Tickets → Jobs/Revisions/Events

### Planner (Autopilot)

`PlannerService` runs on periodic ticks:
- Picks highest-priority `PLANNED` ticket when no active execution exists
- Proposes follow-up tickets for `BLOCKED` tickets (LLM-powered)
- Generates reflections for `DONE` tickets

**Safety:** Can only create `PROPOSED` tickets, enqueue jobs, add comments. Cannot transition tickets or delete anything. Uses `planner_locks` table for concurrency control.

**Caps:** `max_followups_per_ticket` (default 2), `max_followups_per_tick` (default 3)

Use `TicketGenerationService` for generating tickets from goals; `PlannerService` for tick-based autopilot.

### Middleware

**Idempotency** (`idempotency.py`): Atomic first-writer-wins via SQLite. Guarantees exactly-once execution for LLM operations. Key includes `(client_id, route, resource_scope, idempotency_key)`. Returns `409 Conflict` for same key + different body.

**Rate Limiting** (`rate_limit.py`): Cost-based budget per client for LLM endpoints using SQLite.

### Data Model Relationships

```
Board
  ├─ Goals (1:N)
  │    ├─ Tickets (1:N)
  │    │    ├─ Jobs (1:N) → Evidence (1:N), Revision (1:1 per execute job)
  │    │    ├─ Revisions (1:N) → ReviewComments (1:N), ReviewSummary (1:1)
  │    │    ├─ TicketEvents (1:N)
  │    │    └─ Workspace (1:1)
  │    ├─ CostBudget (1:1)
  │    └─ AgentSessions (1:N)
  ├─ AgentTeam (1:1)
  │    └─ AgentTeamMembers (1:N)
  │         └─ TeamAgentSessions (1:N)
  ├─ BoardMessages (1:N) — inter-agent message board
  ├─ BoardMessageCursors (1:N) — per-session read cursors
  ├─ Jobs (1:N, denormalized)
  └─ Workspaces (1:N, denormalized)
```

Evidence is NOT cascade deleted (orphaned evidence cleaned by maintenance tasks).

## Important Patterns & Gotchas

### Async vs Sync Database

- **FastAPI routes:** Async SQLAlchemy via `database.get_db()`
- **Background worker:** Sync SQLAlchemy via `database_sync.get_sync_db()`
- Models are shared but sessions differ. Use `db.expunge()` before passing objects between contexts.

### Testing

- Tests use `asyncio_mode = "auto"` (configured in `pyproject.toml`) — no need for `@pytest.mark.asyncio`
- Mock LLM calls in tests to avoid API costs
- Fixtures in `backend/tests/conftest.py`

### Ruff Configuration

Ruff ignores `B008` (function call in default argument) because FastAPI's `Depends()` pattern uses this intentionally. Don't "fix" `Depends()` default arguments.

### Worktree Safety

- Never run operations on main/master/develop branches when worktree expected
- Always use `WorktreeValidator.validate_safe_for_execution()` before running commands in worktrees
- Board's `repo_root` is authoritative — never trust client-provided paths

### LLM Integration

- Use `LLMService` wrapper (via LiteLLM) for all LLM calls
- Supports OpenAI, Anthropic, AWS Bedrock
- Configure model in `draft.yaml` (`planner_config.model`)
- Cost tracking via `CostTrackingService` with per-goal budgets

### Configuration Files

- `backend/.env`: Database URL, CORS, AWS credentials (copy from `.env.example`)
- `draft.yaml` (repo root): Executor config, verification commands, cleanup TTLs, planner settings, merge strategy
- `backend/pyproject.toml`: Ruff + pytest config

### Coding Style

**Python:** Ruff (88-char lines, double quotes, sorted imports, type hints required). Config in `backend/pyproject.toml`.

**TypeScript/React:** ESLint + Prettier. Components in `PascalCase.tsx`, hooks start with `use`, utilities in `camelCase.ts`.

## Common Tasks

### Adding a New State Transition
1. Update `ALLOWED_TRANSITIONS` in `backend/app/state_machine.py`
2. Add transition logic in ticket service or worker
3. Update tests in `backend/tests/test_revision_invariants.py`
4. Update frontend state handling in `frontend/src/components/TicketCard.tsx`

### Adding a New Executor Type
1. Add enum variant to `ExecutorType` in `executor_service.py`
2. Implement `get_apply_command()` logic
3. Update `find_executor()` to detect new CLI
4. Add to `EXECUTOR_OPTIONS` in `frontend/src/components/TeamSettings.tsx`

### Adding a Verification Command
Edit `draft.yaml` under `verify_config.commands`.

### Adding a New Agent Role
1. Add role definition to `AGENT_ROLE_CATALOG` in `backend/app/services/agent_catalog.py`
2. Include: `role` (snake_case id), `display_name`, `description`, `default_prompt`, `receive_mode` ("directed" or "all"), `is_required`, `category`, `icon`
3. Optionally add to presets in `TEAM_PRESETS` in the same file
4. Add icon mapping in `ICON_MAP` in `frontend/src/components/TeamSettings.tsx`

### Adding a New Team Preset
1. Add preset to `TEAM_PRESETS` dict in `backend/app/services/agent_catalog.py`
2. Each preset is a list of role strings (must match `role` field in catalog)
3. Preset appears automatically in the UI

### Running Multi-Agent Execution
1. Open Board Settings → Agent Team tab
2. Apply a preset or add members from catalog
3. Toggle "Multi-Agent Execution" ON
4. Execute a ticket — worker auto-detects the team and launches tmux sessions
5. Monitor via `tmux ls` to see running agents
6. **Important:** Use `make run` (not `--reload`) to prevent HMR from killing the worker loop
