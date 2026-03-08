# Contributing to Draft

Thanks for your interest in contributing to Draft! This guide will help you get started.

## Getting Started

1. Fork the repository
2. Clone your fork
3. Install dependencies: `make setup`
4. Run migrations: `make db-migrate`
5. Start the dev servers: `make run`
6. Verify everything works: open http://localhost:5173

## Development Setup

```bash
make setup          # Install Python + Node dependencies
make db-migrate     # Run database migrations
make run            # Start backend (8000) + frontend (5173)
```

See [README.md](README.md) for full setup details.

## Code Style

### Python (Backend)

- **Linter/Formatter:** [Ruff](https://docs.astral.sh/ruff/) (configured in `backend/pyproject.toml`)
- 88-character line limit, double quotes, sorted imports, type hints required
- Run: `make lint` / `make format`
- FastAPI's `Depends()` in default arguments is intentional (Ruff B008 is ignored)

### TypeScript (Frontend)

- **Linter:** ESLint
- **Formatter:** Prettier
- Components in `PascalCase.tsx`, hooks start with `use`, utilities in `camelCase.ts`
- Run: `make lint` / `make format`

## Testing

### Backend

```bash
cd backend && source venv/bin/activate
pytest tests -v                # All tests
pytest tests/test_file.py -v   # Specific file
```

### Frontend (E2E)

```bash
cd frontend
npx playwright test            # All e2e tests
npx playwright test --ui       # Interactive mode
```

## Pull Request Process

1. Create a feature branch from `master`
2. Make your changes with clear, descriptive commits
3. Ensure all tests pass (`pytest` + `playwright test`)
4. Ensure linting passes (`make lint`)
5. Open a PR with a clear description of what changed and why

## Architecture Overview

See [CLAUDE.md](CLAUDE.md) for a detailed architecture guide covering:

- State machine and ticket lifecycle
- Git worktree isolation
- Background job system
- AI executor system
- Planner (autopilot) logic

## Key Patterns

- **Async vs Sync DB:** FastAPI routes use async SQLAlchemy; background worker uses sync SQLAlchemy
- **State machine:** Always validate transitions via `validate_transition()` before applying
- **Worktree safety:** Never run operations on main/master branches; use `WorktreeValidator`
- **Board scoping:** `board.repo_root` is authoritative for all file paths; never trust client-provided paths

## Reporting Issues

- Use GitHub Issues
- Include steps to reproduce, expected vs actual behavior
- Attach logs if relevant (`backend/logs/` or browser console)

## License

By contributing, you agree that your contributions will be licensed under the same [BSL 1.1 license](LICENSE) that covers the project.
