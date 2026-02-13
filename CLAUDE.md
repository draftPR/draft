# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Smart Kanban (aka Orion Kanban) is an AI-powered local-first kanban board that uses AI agents to automatically implement tickets. It creates isolated git worktrees for each ticket, runs AI code tools (Claude CLI or Cursor Agent) to implement changes, verifies the changes, and manages the workflow through a state machine.

**Tech Stack:**
- Backend: FastAPI + SQLAlchemy (async) + Celery + Redis
- Frontend: React + Vite + TypeScript + Tailwind CSS + shadcn/ui
- Database: SQLite with Alembic migrations
- Background Jobs: Celery workers with Redis broker
- AI Executors: Claude Code CLI or Cursor Agent CLI

## Quick Reference

**Start everything:**
```bash
make run           # Starts Redis, Backend, Worker, Frontend
```

**Run tests:**
```bash
cd backend && source venv/bin/activate && pytest tests -v
```

**Lint/format code:**
```bash
make lint          # Lint backend + frontend
make format        # Format backend + frontend
```

**Database migrations:**
```bash
make db-migrate    # Apply migrations
```

**Check services:**
```bash
curl http://localhost:8000/health          # Backend health
redis-cli ping                              # Redis status
ps aux | grep celery                        # Worker running?
```

## Development Commands

### Setup
```bash
make setup              # Install all dependencies (backend venv + frontend npm)
```

### Running the Application
```bash
make run                # Start ALL services (Redis, Backend, Worker, Frontend)
# OR
./run.py                # Alternative launcher script
```

### Running Services Manually (4 terminals)
```bash
make redis              # Terminal 1: Start Redis
make dev-backend        # Terminal 2: FastAPI at http://localhost:8000
make dev-worker         # Terminal 3: Celery worker (--pool=solo to avoid SIGSEGV)
make dev-frontend       # Terminal 4: Vite at http://localhost:5173
```

### Database
```bash
make db-migrate         # Run Alembic migrations (alembic upgrade head)
```

### Code Quality
```bash
make lint               # Run ruff (backend) + ESLint (frontend)
make format             # Format with ruff + Prettier
make lint-backend       # Ruff only: cd backend && ruff check .
make format-backend     # Ruff format + fix
```

### Testing
```bash
cd backend
source venv/bin/activate
pytest tests -v         # Run all backend tests
pytest tests/test_middleware.py -v  # Run specific test file
pytest -k "test_name" -v            # Run specific test
```

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

**Key states:**
- `PROPOSED`: New ticket, awaiting human review
- `PLANNED`: Approved, ready to execute
- `EXECUTING`: AI agent actively implementing changes
- `VERIFYING`: Running verification commands (tests, lints)
- `NEEDS_HUMAN`: Awaiting human review/approval or stuck (interactive executor)
- `BLOCKED`: Execution or verification failed
- `DONE`: Completed and approved
- `ABANDONED`: Cancelled/discarded

**Terminal states:** `DONE` and `ABANDONED` (worktrees are cleaned up)

### Git Worktree Isolation

Each ticket gets its own **isolated git worktree** to enable parallel execution without conflicts:

- Worktrees live at `.smartkanban/worktrees/{ticket_id}/`
- Each worktree has a branch: `goal/{goal_id}/ticket/{ticket_id}`
- Logs stored in: `{worktree_path}/.smartkanban/logs/{job_id}.log`
- Evidence files (stdout/stderr) stored per-job in worktree
- Worktrees are auto-cleaned when tickets reach terminal states (via `cleanup_service.py`)

**Services involved:**
- `WorkspaceService` (`workspace_service.py`): Creates/manages worktrees
- `WorktreeValidator` (`worktree_validator.py`): Validates worktree integrity
- `CleanupService` (`cleanup_service.py`): Removes stale worktrees and evidence files

### Background Job System

Jobs are Celery tasks that execute or verify tickets:

**Job Types:**
- `EXECUTE`: Run AI executor (Claude/Cursor) to implement ticket changes
- `VERIFY`: Run verification commands (tests, linters) defined in `smartkanban.yaml`

**Job Flow:**
1. Frontend or planner calls `POST /tickets/{id}/run` or `/verify`
2. Backend creates Job record with status `QUEUED`, returns immediately
3. Celery worker picks up task from Redis queue
4. Worker runs in isolated worktree, streams logs via Redis SSE
5. Job status transitions: `QUEUED → RUNNING → SUCCEEDED/FAILED/CANCELED`
6. Job results trigger ticket state transitions

**Key files:**
- `backend/app/worker.py`: Celery task definitions (`execute_ticket_job`, `verify_ticket_job`)
- `backend/app/celery_app.py`: Celery configuration
- `backend/app/services/job_service.py`: Job CRUD operations
- `backend/app/services/job_watchdog_service.py`: Monitors stuck jobs, auto-cancels timeouts

**Real-time Logs:**
- Jobs stream logs via Redis using `log_stream_service.py`
- Frontend subscribes to SSE endpoint `GET /jobs/{id}/logs/stream`
- Logs written to both file (for persistence) and Redis (for streaming)

**Celery Beat (Periodic Tasks):**
- Celery Beat scheduler runs periodic tasks (configured in `celery_app.py`)
- Tasks include:
  - PR status polling (every 5 minutes)
  - Job watchdog (checks for stuck jobs)
  - Stale worktree cleanup (configurable)
- Run Beat with worker: `celery -A app.celery_app worker --beat --loglevel=info`
- Or separately: `celery -A app.celery_app beat --loglevel=info`

### AI Executor System

The system supports multiple AI code executors via `executor_service.py`:

**Executor Types:**
- `CLAUDE`: Claude Code CLI (headless, recommended for automation)
- `CURSOR_AGENT`: Cursor Agent CLI (headless)
- `CURSOR`: Cursor IDE CLI (interactive, requires human)

**Execution Modes:**
- `HEADLESS`: Fully automated, AI runs without prompts
- `INTERACTIVE`: Opens editor, requires human to complete work

**YOLO Mode (DANGEROUS):**
- When enabled in `smartkanban.yaml`, Claude CLI runs with `--dangerously-skip-permissions`
- Allows AI to run any command without user approval
- Safety: Only runs if `yolo_allowlist` has trusted repo paths
- Worker refuses to run YOLO if allowlist is empty

**Prompt Bundle:**
- Executors receive a prompt bundle with ticket context
- Built by `PromptBundleBuilder` in `executor_service.py`
- Includes: ticket title, description, goal context, codebase info

**State Transitions:**
- Headless success with diff → `VERIFYING`
- Headless success with NO diff → `BLOCKED` (reason: "no changes")
- Headless failure → `BLOCKED`
- Interactive (Cursor) → `NEEDS_HUMAN` immediately

### Verification Pipeline

After execution, tickets move to `VERIFYING` state where verification commands run:

**Configuration:** `smartkanban.yaml` at repo root
```yaml
verify_config:
  commands:
    - "python -m compileall -q backend/app"
    - "cd backend && ruff check app --select=E,F"
  on_failure: "blocked"
```

**Verification Process:**
1. Commands run sequentially in ticket's worktree
2. Each command's stdout/stderr captured as `Evidence` records
3. Evidence linked to job and ticket for debugging
4. Stop on first failure

**State Transitions:**
- All pass → `NEEDS_HUMAN` (awaiting human approval)
- Any fail → `BLOCKED` (with TicketEvent describing failure)

**Evidence API:**
- `GET /tickets/{id}/evidence`: List all evidence for ticket
- `GET /evidence/{id}/stdout`: Get stdout content
- `GET /evidence/{id}/stderr`: Get stderr content

### Revision & Review System (PR-like Workflow)

Revisions track each agent iteration like GitHub PR snapshots:

**Revision Model** (`revision.py`):
- **One revision per execute job** - captures code changes as diffs
- **Incremental numbering** - Revision #1, #2, #3 per ticket
- **Status lifecycle:** `open` → `changes_requested` → `approved` → `superseded`
- **Only one open revision** - New revision supersedes previous open one
- **Immutable evidence:** Diffs stored as Evidence (stat + patch)
- **Unique constraint:** One revision per (ticket_id, job_id) and (ticket_id, number)

**Review Components:**
- `ReviewComment` - Line-level or general comments on revisions (can be resolved)
- `ReviewSummary` - Final review decision (approve/request changes)
- Comments and summaries cascade delete with revision

**Workflow:**
1. Execute job completes → Create Revision with git diff
2. Human/LLM adds ReviewComments
3. Human creates ReviewSummary (approve/changes_requested)
4. If approved → Ticket can transition to DONE
5. If changes requested → Ticket returns to EXECUTING
6. New execution creates new revision, old becomes `superseded`

**Key Fields:**
- `diff_stat_evidence_id` - Link to Evidence with `git diff --stat`
- `diff_patch_evidence_id` - Link to Evidence with `git diff`
- `unresolved_comment_count` - Property counting unresolved comments

**API:**
- `GET /tickets/{id}/revisions` - List all revisions for ticket
- `GET /revisions/{id}` - Get revision details with comments
- `POST /revisions/{id}/comments` - Add review comment
- `POST /revisions/{id}/review` - Submit final review decision

**Important:** Revisions are NOT the same as git commits. They're pre-merge review artifacts.

### Board & Multi-Tenancy

Boards provide **permission boundaries** and **repository scoping**:

**Board Model** (`board.py`):
- **Single repo per board** - `repo_root` is authoritative path
- **Permission boundary** - All operations scoped by `board_id`
- **Prevents cross-tenant access** - Goals/Tickets/Jobs/Workspaces belong to one board
- **Default branch** - Optional per-board configuration

**Scoping:**
- Goals have `board_id` (nullable for migration compatibility)
- Tickets have `board_id` (must match goal's board)
- Jobs have `board_id` (inherited from ticket)
- Workspaces have `board_id`

**Security:**
- All file operations use `board.repo_root` - NOT client-provided paths
- Validates all operations stay within board's repo
- Prevents path traversal attacks

**Multi-board Setup:**
Create boards for different projects:
```bash
POST /boards
{
  "id": "project-a",
  "name": "Project A",
  "repo_root": "/path/to/project-a",
  "default_branch": "main"
}
```

### Cost Tracking & Budget Management

Tracks LLM API costs to prevent runaway spending:

**Cost Budget** (`cost_budget.py`):
- **Per-goal budgets** - Set spending limits per goal
- **Time-based limits:** `daily_budget`, `weekly_budget`, `monthly_budget`, `total_budget`
- **Alert thresholds:** `warning_threshold` (default 80%)
- **Auto-pause:** `pause_on_exceed` flag stops execution when budget exceeded

**Cost Tracking Service** (`cost_tracking_service.py`):
- Tracks costs across tickets, goals, time periods
- Aggregates by agent type (Claude, GPT-4, etc.)
- Provides `CostSummary` with breakdowns
- Calculates `BudgetStatus` with remaining funds

**Agent Sessions** (`agent_session.py`):
- Each LLM API call creates an AgentSession record
- Tracks: `input_tokens`, `output_tokens`, `cost_usd`
- Links to ticket and goal for aggregation
- Uses `AGENT_REGISTRY` for per-model pricing

**API:**
- `GET /goals/{id}/cost-summary` - Get spending summary
- `GET /goals/{id}/budget-status` - Check budget remaining
- `POST /goals/{id}/budget` - Set/update budget limits

**Budget Enforcement:**
- Planner checks budget before queueing jobs
- Executor can abort if budget exceeded mid-execution
- Warning alerts at threshold (e.g., 80%)

### Context Gatherer (Secure Codebase Analysis)

Gathers repository context for LLM prompts **safely**:

**Context Gatherer** (`context_gatherer.py`):
- **Metadata-first approach** - Returns file paths, line counts, small excerpts only
- **NEVER full file contents** - Prevents prompt size explosions
- **Security-first:**
  - Excludes sensitive paths (`.env`, `*.key`, `credentials`, `secrets`)
  - Skips symlinks to prevent secret leakage
  - Validates all paths within repo boundary
- **Strict caps:**
  - Max files scanned (configurable)
  - Max bytes read per file
  - Max excerpt size (200 chars for TODOs, 500 for README)

**RepoContext Output:**
- `file_tree` - List of FileMetadata (path, line_count, language, size)
- `project_type` - Detected type (python, node, mixed, unknown)
- `todo_count` / `todo_excerpts` - Found TODO comments (max 50)
- `readme_excerpt` - First 500 chars of README if exists
- `stats` - Scan statistics (files scanned, bytes read, exclusions)

**Usage:**
```python
from app.services.context_gatherer import ContextGatherer

gatherer = ContextGatherer(repo_path)
context = gatherer.gather(
    include_readme=True,
    include_todos=True,
    max_files=1000
)
prompt = context.to_prompt_string()  # LLM-ready format
```

**Used by:**
- Ticket generation (provides codebase overview)
- Planner (validates tickets against codebase)
- Executor prompts (gives agent context)

### Log Normalization & Agent Sessions

Raw agent logs are parsed into structured, displayable formats:

**Log Normalization:**
- `CursorLogNormalizer` (`cursor_log_normalizer.py`) parses Claude Code CLI / Cursor Agent logs
- Extracts thinking blocks, file changes, commands, errors
- Stored in `normalized_logs` table linked to jobs
- UI displays logs as collapsible sections with syntax highlighting

**Agent Session Management:**
- `AgentSessionManager` (`agent_session_manager.py`) tracks active agent CLI sessions
- Supports interactive agents (Cursor IDE) that open editors
- Session lifecycle: create → track PID → poll status → cleanup
- Used for "needs_human" workflow where human completes ticket in Cursor

**API:**
- `GET /jobs/{id}/normalized-logs`: Get structured logs
- `POST /jobs/{id}/normalize-logs?agent_type=claude`: Trigger normalization

### Planner (Autopilot)

The planner (`planner_service.py`) is an AI-powered autopilot that runs on periodic ticks:

**Tick Actions:**
1. **Pick next ticket:** If no `EXECUTING`/`VERIFYING` ticket exists, pick highest priority `PLANNED` ticket
2. **Propose follow-ups:** For `BLOCKED` tickets, generate follow-up ticket proposals (LLM-powered)
3. **Generate reflections:** For `DONE` tickets, create summary comments (LLM-powered)

**Permissions (what planner CAN and CANNOT do):**
- ✅ CAN: Create tickets in `PROPOSED` state, enqueue EXECUTE jobs, add COMMENT events
- ❌ CANNOT: Transition tickets, delete anything, modify ticket text, create tickets in non-PROPOSED states

**Safety Caps:**
- `max_followups_per_ticket`: Max follow-ups for any single blocked ticket (default: 2)
- `max_followups_per_tick`: Max follow-ups created per tick (default: 3)
- `skip_followup_reasons`: Blocker reasons that shouldn't trigger follow-ups (e.g., "no changes")

**Concurrency:**
- Uses `planner_locks` table to ensure only one tick runs at a time
- Celery jobs enqueued AFTER DB commit

**Ticket Generation:**
- For generating tickets from goals, use `TicketGenerationService` (`ticket_generation_service.py`)
- For tick-based autopilot, use `PlannerService`

**Ticket Validation:**
- When `validate_tickets: true`, LLM checks if generated tickets are:
  - Appropriate for the goal
  - Not already implemented
  - Relevant to the codebase
- Invalid tickets filtered out and logged

### Middleware

**Rate Limiting** (`rate_limit.py`):
- 10 req/min for LLM endpoints (e.g., `/planner/tick`, `/tickets/generate`)
- Uses Redis for distributed rate limiting

**Idempotency** (`idempotency.py`) - CRITICAL SYSTEM:
- **Atomic first-writer-wins** pattern using Redis SETNX
- **Guarantees exactly-once execution** for expensive LLM operations
- **Deterministic behavior contract:**
  1. First request: acquires lock, executes, stores result with execution_id
  2. Concurrent requests: blocking wait up to 10 seconds for result
  3. If result appears: return with `X-Idempotency-Replayed: true` header
  4. If timeout: return `202 Accepted` with execution_id for polling
  5. If same key + different body: return `409 Conflict`
- **Resource scoping:** Keys include `(client_id, route, resource_scope, idempotency_key)` to prevent cross-goal collisions
- **Scope precedence:** Path params (e.g., `/goals/{goal_id}`) take precedence over body params
- **Redis REQUIRED:** Returns `503 Service Unavailable` if Redis unavailable
- **Lock TTL:** Dynamically calculated based on executor timeout + buffer
- **Endpoints:** `/goals/{goal_id}/generate-tickets`, `/goals/{goal_id}/reflect-on-tickets`, `/boards/{board_id}/analyze-codebase`, `/tickets/bulk-update-priority`

**How to use:**
```bash
# Client sends Idempotency-Key header (max 64 chars)
curl -X POST http://localhost:8000/goals/{goal_id}/generate-tickets \
  -H "Idempotency-Key: my-unique-key-123" \
  -H "Content-Type: application/json" \
  -d '{"goal_id": "abc"}'

# Retry with same key returns cached result
# Response headers include:
#   X-Idempotency-Replayed: true
#   X-Execution-ID: <uuid>
```

## Project Structure

```
backend/app/
├── main.py                  # FastAPI app, CORS, exception handlers
├── database.py              # Async SQLAlchemy setup
├── database_sync.py         # Sync SQLAlchemy for Celery
├── celery_app.py            # Celery configuration
├── worker.py                # Celery tasks (execute, verify)
├── state_machine.py         # Ticket state machine, transition rules
├── exceptions.py            # Custom exception classes
├── redis_client.py          # Redis connection
├── models/                  # SQLAlchemy models
│   ├── board.py             # Board (permission scope, repo boundary)
│   ├── goal.py              # Goal (parent of tickets, has board_id)
│   ├── ticket.py            # Ticket (has blocked_by_ticket_id, board_id)
│   ├── job.py               # Job (execute/verify background task, has board_id)
│   ├── revision.py          # Revision (PR-like diff snapshot per execute job)
│   ├── review_comment.py    # ReviewComment (line comments on revisions)
│   ├── review_summary.py    # ReviewSummary (final review decision)
│   ├── evidence.py          # Evidence (verification stdout/stderr, diffs)
│   ├── ticket_event.py      # TicketEvent (audit log)
│   ├── workspace.py         # Workspace (git worktree metadata, has board_id)
│   ├── agent_session.py     # AgentSession (LLM API call tracking)
│   ├── cost_budget.py       # CostBudget (spending limits per goal)
│   ├── normalized_log.py    # NormalizedLog (structured agent logs)
│   ├── analysis_cache.py    # AnalysisCache (codebase analysis cache)
│   ├── planner_lock.py      # PlannerLock (concurrency control)
│   └── enums.py             # EventType, ActorType enums
├── schemas/                 # Pydantic schemas for API
├── routers/                 # FastAPI route handlers
│   ├── tickets.py           # Ticket CRUD, transition, run, verify
│   ├── goals.py             # Goal CRUD
│   ├── jobs.py              # Job status, logs, cancel
│   ├── board.py             # Board view (kanban columns)
│   ├── planner.py           # Planner tick, config
│   ├── merge.py             # Merge worktree branch to main
│   ├── evidence.py          # Evidence stdout/stderr
│   └── ...
├── services/                # Business logic
│   ├── executor_service.py  # AI executor (Claude/Cursor)
│   ├── workspace_service.py # Git worktree management
│   ├── job_service.py       # Job CRUD
│   ├── job_watchdog_service.py  # Monitor stuck jobs
│   ├── planner_service.py   # Autopilot planner
│   ├── planner_tick_sync.py # Planner tick (sync version for Celery)
│   ├── ticket_generation_service.py  # Generate tickets from goals
│   ├── ticket_service.py    # Ticket CRUD
│   ├── revision_service.py  # Revision CRUD and management
│   ├── review_service.py    # Review comment and summary management
│   ├── config_service.py    # Load smartkanban.yaml
│   ├── cleanup_service.py   # Worktree cleanup
│   ├── merge_service.py     # Merge worktree branches
│   ├── board_service.py     # Board CRUD
│   ├── goal_service.py      # Goal CRUD
│   ├── log_stream_service.py  # Real-time log streaming
│   ├── log_normalizer.py    # Parse agent logs to structured format
│   ├── cursor_log_normalizer.py  # Claude CLI log parser
│   ├── llm_service.py       # LLM API wrapper (LiteLLM)
│   ├── llm_provider_clients.py  # Provider-specific LLM clients
│   ├── context_gatherer.py  # Gather codebase context for prompts
│   ├── cost_tracking_service.py  # Track LLM API costs
│   ├── agent_registry.py    # Agent type registry with pricing
│   ├── agent_session_manager.py  # Track interactive agent sessions
│   ├── agent_session_service.py  # Agent session CRUD
│   ├── github_service.py    # GitHub PR integration
│   ├── worktree_validator.py  # Validate worktree safety
│   └── queued_message_service.py  # Message queue management
├── middleware/              # FastAPI middleware
│   ├── idempotency.py       # Idempotency key support
│   └── rate_limit.py        # Rate limiting
└── utils/                   # Utility functions

backend/tests/               # pytest tests
├── conftest.py              # Test fixtures
├── test_middleware.py       # Idempotency, rate limit tests
├── test_planner_providers.py  # Planner provider tests
├── test_revision_invariants.py  # Revision invariant tests
└── test_ticket_validation.py  # Ticket validation tests

frontend/src/
├── App.tsx                  # Main app
├── main.tsx                 # Entry point
├── components/              # React components
│   ├── KanbanBoard.tsx      # Main board view
│   ├── TicketCard.tsx       # Ticket card
│   ├── JobLogsViewer.tsx    # Job logs display
│   ├── EvidenceList.tsx     # Verification evidence
│   ├── LiveAgentLogs.tsx    # Real-time SSE logs
│   └── ui/                  # shadcn/ui components
└── types/                   # TypeScript types
```

## Configuration

### Backend Environment (`backend/.env`)

Copy `backend/.env.example` to `backend/.env` and configure:

```bash
# Application environment
APP_ENV=development  # or production

# Database (async SQLAlchemy for FastAPI)
DATABASE_URL=sqlite+aiosqlite:///./backend/kanban.db

# CORS - Frontend URL for cross-origin requests
FRONTEND_URL=http://localhost:5173

# Git repository settings for worktree isolation
GIT_REPO_PATH=/path/to/repo  # Optional, defaults to project root
BASE_BRANCH=main              # Optional, defaults to main, fallback to master

# AWS credentials (if using Bedrock for LLM)
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_REGION_NAME=us-east-2

# Redis (optional, defaults to localhost:6379)
REDIS_URL=redis://localhost:6379/0

# GitHub token (optional, gh CLI preferred)
GITHUB_TOKEN=ghp_xxxxx
```

### Smart Kanban Config (`smartkanban.yaml`)
Key sections:
- `execute_config`: Executor timeout, preferred executor (claude/cursor), YOLO mode settings
- `verify_config`: Verification commands, failure behavior
- `cleanup_config`: Auto-cleanup settings, TTLs for worktrees/evidence
- `merge_config`: Merge strategy (merge/rebase), auto-delete branches
- `planner_config`: LLM model, agent path, follow-up caps, feature toggles

## Exception Hierarchy

All custom exceptions inherit from `SmartKanbanError` and map to HTTP status codes:

**Base Exception:**
- `SmartKanbanError` - Base class for all domain exceptions

**Validation & State (HTTP 400):**
- `InvalidStateTransitionError(from_state, to_state)` - Invalid ticket state transition
- `ValidationError(message)` - General validation failure

**Not Found (HTTP 404):**
- `ResourceNotFoundError(resource_type, resource_id)` - Resource doesn't exist

**Conflict (HTTP 409):**
- `ConflictError(message)` - Operation conflicts with current state (e.g., comment on superseded revision)

**Workspace Errors:**
- `WorkspaceError(message)` - Base for workspace issues
- `NotAGitRepositoryError(path)` - Path is not a git repo
- `WorktreeCreationError(message, git_error)` - Failed to create worktree
- `BranchNotFoundError(branch)` - Base branch doesn't exist

**Executor Errors:**
- `ExecutorError(message)` - Base for executor issues
- `ExecutorNotFoundError()` - No Claude/Cursor CLI found
- `ExecutorInvocationError(message, exit_code, stderr)` - CLI invocation failed

**Configuration (HTTP 400):**
- `ConfigurationError(message)` - Missing/invalid config (smartkanban.yaml, .env)

**Planner/LLM Errors:**
- `PlannerError(message)` - Base for planner issues
- `LLMAPIError(message, provider, status_code)` - LLM API call failed

**Usage in Code:**
```python
from app.exceptions import ResourceNotFoundError, InvalidStateTransitionError

# Raise with context
ticket = db.query(Ticket).filter_by(id=ticket_id).first()
if not ticket:
    raise ResourceNotFoundError("Ticket", ticket_id)

# Validate state transition
if not validate_transition(ticket.state, new_state):
    raise InvalidStateTransitionError(ticket.state, new_state)
```

**Exception Handlers:**
All custom exceptions have handlers in `main.py` that return proper JSON responses with `error_type` field.

## Important Patterns & Gotchas

### Async vs Sync Database

- **FastAPI routes:** Use async SQLAlchemy via `app.database.get_db()`
- **Celery workers:** Use sync SQLAlchemy via `app.database_sync.get_sync_db()`
- Models are shared, but sessions are different contexts
- Use `db.expunge()` before passing objects between async/sync contexts

### Revision vs Git Commit

- **Revisions** are pre-merge review artifacts (like PR diffs)
- **Git commits** happen after approval when merging worktree branch
- One ticket can have multiple revisions (iterations)
- Each revision has immutable diffs stored as Evidence
- Revisions track review status: open → changes_requested → approved → superseded

### Board Scoping

- **ALWAYS use board.repo_root** for file operations, never client-provided paths
- Check `board_id` matches across Goal → Ticket → Job relationships
- Validate operations stay within board's repository boundary
- Use `board_id` for permission checks in multi-tenant scenarios

### State Transition Validation

Always validate transitions before applying:
```python
from app.state_machine import validate_transition, TicketState

if not validate_transition(ticket.state, new_state):
    raise InvalidStateTransitionError(ticket.state, new_state)
```

### Worktree Safety

- Never run operations on main/master/develop branches when worktree expected
- Always validate worktree path before executing commands
- Use `WorktreeValidator.validate_safe_for_execution()` before running commands

### Job Lifecycle

- Jobs created with status `QUEUED`, Celery task enqueued separately
- Always check job status before assuming completion
- Use `job_watchdog_service.py` to auto-cancel stuck jobs
- Stream logs via Redis, persist to file for durability

### Ticket Dependencies

Tickets can block each other via `blocked_by_ticket_id`:
- A ticket cannot execute until its blocker is `DONE`
- Check blocker status in `ticket_service.py` before queueing execute jobs
- Agent can specify dependencies when generating tickets
- Frontend displays blocked/blocking relationships

### Data Model Relationships

Understanding the entity relationships is critical:

```
Board
  ├─ Goals (1:N)
  │    └─ Tickets (1:N)
  │         ├─ Jobs (1:N)
  │         │    ├─ Evidence (1:N) - stdout/stderr files
  │         │    └─ Revision (1:1) - diff for execute jobs
  │         ├─ Revisions (1:N)
  │         │    ├─ ReviewComments (1:N)
  │         │    └─ ReviewSummary (1:1)
  │         ├─ TicketEvents (1:N) - audit log
  │         └─ Workspace (1:1) - worktree metadata
  ├─ Jobs (1:N) - denormalized for board-level queries
  └─ Workspaces (1:N) - denormalized for cleanup

Goal
  ├─ CostBudget (1:1) - spending limits
  └─ AgentSessions (1:N) - LLM API calls
```

**Key Relationships:**
- **Board → Everything** - Permission boundary (cascade delete)
- **Ticket → Revision** - One revision per execute job (job completes → create revision)
- **Revision → Evidence** - Immutable diffs (stat + patch)
- **Ticket → Jobs** - Multiple jobs (execute, verify) per ticket
- **Job → Evidence** - Multiple evidence files per job (verification stdout/stderr)
- **Goal → CostBudget** - One budget per goal
- **Ticket → Workspace** - One worktree per ticket (auto-created, auto-cleaned)

**Cascade Deletes:**
- Delete Board → Deletes all Goals, Tickets, Jobs, Workspaces
- Delete Goal → Deletes all Tickets (and their Jobs, Revisions, etc.)
- Delete Ticket → Deletes all Jobs, Revisions, Events, Workspace
- Delete Revision → Deletes ReviewComments and ReviewSummary
- Evidence is NOT cascade deleted (orphaned evidence cleaned by maintenance tasks)

### LLM Calls

- Use `LLMService` wrapper (via LiteLLM) for all LLM calls
- Supports OpenAI, Anthropic, AWS Bedrock (including inference profiles)
- Rate-limited by middleware (10 req/min)
- Configure model in `smartkanban.yaml` (`planner_config.model`)

### Testing

- Tests require Redis for integration tests (marked with `-m integration`)
- Use `conftest.py` fixtures for database and async session setup
- Mock LLM calls in tests to avoid API costs
- Run specific tests: `pytest tests/test_file.py::test_name -v`

### Cleanup & Maintenance

The system auto-cleans stale resources to prevent disk bloat:

**Cleanup Service** (`cleanup_service.py`):
- **Worktree cleanup:**
  - Auto-deletes worktrees for tickets in terminal states (DONE, ABANDONED)
  - Removes worktrees older than `worktree_ttl_days` (default: 14)
  - Triggered on ticket state transitions and periodic maintenance
- **Evidence cleanup:**
  - Deletes evidence files older than `evidence_ttl_days` (default: 30)
  - Orphaned evidence (no linked job) cleaned first
- **Safety checks:**
  - Never deletes worktrees for active tickets (EXECUTING, VERIFYING)
  - Validates worktree paths before deletion
  - Logs all cleanup operations

**Configuration** (in `smartkanban.yaml`):
```yaml
cleanup_config:
  auto_cleanup_on_merge: true    # Delete worktree after successful merge
  worktree_ttl_days: 14           # Max age for worktrees
  evidence_ttl_days: 30           # Max age for evidence files
  max_worktrees: 50               # Soft limit (future use)
```

**Manual Cleanup:**
```bash
# Trigger cleanup via API
POST /maintenance/cleanup
{
  "cleanup_worktrees": true,
  "cleanup_evidence": true,
  "dry_run": false  # Set true to preview without deleting
}

# Or git worktree commands
git worktree list
git worktree remove .smartkanban/worktrees/{ticket_id}
git worktree prune
```

**Periodic Tasks:**
- Celery Beat can schedule cleanup tasks (configure in `celery_app.py`)
- Recommended: Run cleanup daily during off-hours

### Coding Style

**Python (Backend):**
- Ruff for linting and formatting (config in `backend/pyproject.toml`)
- 88-character line length
- Double quotes for strings
- Sorted imports (isort via ruff)
- Type hints required for function signatures
- Clear docstrings for public functions/classes

**TypeScript/React (Frontend):**
- ESLint + Prettier (config in `eslint.config.js` and `.prettierrc`)
- Components in `PascalCase.tsx`
- Hooks start with `use` (e.g., `useTickets`)
- Files: `PascalCase.tsx` for components, `camelCase.ts` for utilities

## Common Tasks

### Running a Single Test
```bash
cd backend
source venv/bin/activate
pytest tests/test_middleware.py::test_idempotency_key -v
```

### Adding a New State Transition
1. Update `ALLOWED_TRANSITIONS` in `backend/app/state_machine.py`
2. Add transition logic in ticket service or worker
3. Update tests in `backend/tests/test_revision_invariants.py`
4. Update frontend state handling in `frontend/src/components/TicketCard.tsx`

### Adding a New Verification Command
Edit `smartkanban.yaml`:
```yaml
verify_config:
  commands:
    - "python -m compileall -q backend/app"
    - "cd backend && ruff check app"
    - "cd backend && pytest tests -v"  # Add this
```

### Adding a New Executor Type
1. Add enum variant to `ExecutorType` in `backend/app/services/executor_service.py`
2. Implement `get_apply_command()` logic for new executor
3. Update `find_executor()` to detect new CLI
4. Test in isolated worktree

### Creating a Database Migration
```bash
cd backend
source venv/bin/activate
alembic revision --autogenerate -m "Add new column to tickets"
# Edit generated migration in backend/alembic/versions/
alembic upgrade head  # Apply migration
alembic current       # Verify current revision
```

### Merging a Ticket's Branch
After ticket is DONE and approved:
```bash
# Via API
POST /tickets/{id}/merge
{
  "strategy": "merge",  # or "rebase"
  "delete_branch": true
}

# This:
# 1. Pulls latest from base branch
# 2. Merges worktree branch to main
# 3. Pushes to remote (if configured)
# 4. Optionally deletes feature branch
# 5. Cleans up worktree
```

### GitHub PR Integration
After ticket execution creates a revision:
```bash
# Create PR (requires gh CLI)
POST /pull-requests
{
  "ticket_id": "abc-123",
  "title": "Optional title",
  "body": "Optional description",
  "base_branch": "main"
}

# Get PR status
GET /pull-requests/{ticket_id}

# Manually refresh PR status
POST /pull-requests/{ticket_id}/refresh
```

**Auto-transition:** When PR merges on GitHub, background polling task (Celery Beat) auto-transitions ticket to DONE.

## Troubleshooting

### Redis Connection Issues
```bash
# Check if Redis is running
redis-cli ping  # Should return PONG

# Start Redis
redis-server

# Or via Docker
docker run -d -p 6379:6379 redis:alpine

# Check Redis logs
redis-cli info
```

### Worker Not Processing Jobs
```bash
# Check worker is running
ps aux | grep celery

# Check Redis queue
redis-cli LLEN celery  # Should show queued jobs

# Restart worker (kills stale processes)
pkill -f "celery worker"
cd backend && source venv/bin/activate
celery -A app.celery_app worker --loglevel=info --pool=solo

# Check worker logs for errors
tail -f backend/logs/celery.log  # If logging to file
```

### Worktree Issues
```bash
# List all worktrees
git worktree list

# Remove stale worktree
git worktree remove .smartkanban/worktrees/{ticket_id}

# Prune deleted worktrees
git worktree prune

# If worktree is locked, force remove
git worktree remove --force .smartkanban/worktrees/{ticket_id}
```

### Database Locked Errors
```bash
# SQLite can lock if multiple processes access it
# Use the sync session for Celery workers, async for FastAPI

# If corrupted, check integrity
sqlite3 backend/kanban.db "PRAGMA integrity_check;"

# Backup before fixing
cp backend/kanban.db backend/kanban.db.backup
```

### Stuck Jobs (Won't Cancel)
Jobs that don't respond to cancel requests:
1. Check `job_watchdog_service.py` is running (monitors timeouts)
2. Kill Celery worker process (job will fail)
3. Manually update job status in DB:
```sql
UPDATE jobs SET status = 'canceled' WHERE id = 'job-id';
```

### Migration Conflicts
```bash
# Check current migration
alembic current

# If "multiple heads" error
alembic heads  # Show all heads
alembic merge -m "merge heads" <revision1> <revision2>
alembic upgrade head
```

### Frontend Can't Connect to Backend
1. Check CORS settings in `backend/app/main.py` (FRONTEND_URL)
2. Verify backend is running: `curl http://localhost:8000/health`
3. Check browser console for CORS errors
4. Ensure `frontend/.env` has correct `VITE_BACKEND_URL`

### LLM API Errors
```bash
# For AWS Bedrock
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION_NAME=us-east-2

# Check credentials
aws sts get-caller-identity

# Test LiteLLM directly
python -c "from litellm import completion; print(completion(model='bedrock/...', messages=[{'role':'user','content':'test'}]))"
```

### Permission Denied on Worktree Operations
Worktree validator checks prevent operations on main branches:
- Only run operations in worktrees (`.smartkanban/worktrees/{ticket_id}/`)
- Never run destructive operations on `main`, `master`, or `develop`
- Use `WorktreeValidator.validate_safe_for_execution()` before commands

## API Endpoints Reference

All endpoints documented at http://localhost:8000/docs (FastAPI auto-generated)

Key endpoints:
- `POST /goals` - Create goal
- `POST /tickets` - Create ticket
- `POST /tickets/{id}/transition` - Change ticket state
- `POST /tickets/{id}/run` - Enqueue execute job
- `POST /tickets/{id}/verify` - Enqueue verify job
- `GET /jobs/{id}` - Get job details with logs
- `GET /jobs/{id}/logs/stream` - SSE stream of live logs
- `POST /planner/tick` - Run planner tick
- `GET /board` - Get kanban board view
- `POST /tickets/{id}/merge` - Merge worktree branch to main
- `GET /tickets/{id}/evidence` - Get verification evidence
