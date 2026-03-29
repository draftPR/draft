<p align="center">
  <img src="https://raw.githubusercontent.com/doramirdor/draft/main/docs/screenshots/banner.png" alt="Draft - Describe a feature. Get a PR." width="900" />
</p>

<p align="center">
  <a href="https://github.com/doramirdor/draft"><img src="https://img.shields.io/github/stars/doramirdor/draft?style=social" alt="GitHub Stars" /></a>
  <a href="https://github.com/doramirdor/draft/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-BSL--1.1-blue" alt="License: BSL 1.1" /></a>
  <a href="https://www.npmjs.com/package/draft-board"><img src="https://img.shields.io/npm/v/draft-board" alt="npm version" /></a>
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/node-18+-339933?logo=node.js&logoColor=white" alt="Node 18+" />
</p>

---

# Draft

An AI-powered local-first kanban board that uses AI agents to automatically implement tickets. Describe a feature, and Draft creates isolated git worktrees, runs AI code tools (Claude Code CLI, Cursor Agent, or others) to implement changes, verifies them, and manages the full workflow — from idea to pull request.

## Quick Start

```bash
npx draft-board
```

That's it. This single command:

1. Checks prerequisites (Python 3.11+, Git)
2. Sets up a Python virtual environment
3. Installs backend dependencies
4. Runs database migrations
5. Starts the server

Once running, open **http://localhost:8000** in your browser.

Press `Ctrl+C` to stop.

## Prerequisites

- **Node.js** 18+
- **Python** 3.11+
- **Git**

No external services (Redis, Postgres, etc.) required — everything runs locally with SQLite.

## How It Works

1. **Create a board** pointing to any git repository
2. **Add a goal** describing what you want to build
3. **Generate tickets** — Draft uses AI to break goals into implementable tickets with dependencies
4. **Run autopilot** — tickets are executed by AI agents in isolated git worktrees
5. **Review & merge** — built-in code review with diffs, then merge back to your branch

### Ticket Lifecycle

```
PROPOSED → PLANNED → EXECUTING → VERIFYING → NEEDS_HUMAN → DONE
```

Each ticket gets its own git worktree and branch, so multiple tickets can execute in parallel without interference.

## Supported AI Executors

| Executor | Mode | Description |
|----------|------|-------------|
| **Claude Code** | Headless | Claude Code CLI (`--print` mode) |
| **Cursor Agent** | Headless | Cursor Agent CLI |
| **Cursor** | Interactive | Opens Cursor IDE for manual editing |

Configure your executor in `draft.yaml` at your repository root:

```yaml
executor_config:
  executor_type: claude  # claude, cursor_agent, or cursor
  yolo_mode: false
```

## Verification

Add verification commands to automatically test implementations:

```yaml
verify_config:
  commands:
    - "pytest tests/"
    - "npm run lint"
    - "npm run build"
```

All commands pass → auto-approved. Any failure → ticket blocked with details.

## Configuration

Create `draft.yaml` at your repository root:

```yaml
executor_config:
  executor_type: claude
  yolo_mode: false

verify_config:
  commands:
    - "pytest tests/ -v"
    - "ruff check ."

planner_config:
  model: "claude-sonnet-4-20250514"
  auto_execute: true
  auto_verify: true
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React + Vite + TypeScript + shadcn/ui |
| Backend | FastAPI (Python) |
| Database | SQLite + Alembic migrations |
| Background Jobs | In-process SQLiteWorker |
| AI Executors | Claude Code CLI, Cursor Agent CLI |

## Development

For contributors, clone the repo and use:

```bash
git clone https://github.com/doramirdor/draft.git
cd draft
make setup        # Install all dependencies
make run          # Start backend + frontend (hot reload)
```

See the [full documentation](https://github.com/doramirdor/draft) for development commands, API reference, and architecture details.

## License

Business Source License 1.1 (BSL 1.1). Free for non-commercial use including personal projects, education, and evaluation. Converts to Apache 2.0 on 2030-02-26.
