# Repository Guidelines

## Project Structure & Module Organization
- `backend/`: FastAPI app (`backend/app`), Alembic migrations, and `backend/tests` (pytest). Config lives in `backend/.env` and `smartkanban.yaml` at repo root.
- `frontend/`: React + Vite + TypeScript app in `frontend/src` with Tailwind/shadcn UI.
- `scripts/`: helper scripts; `run.py` boots all services.
- `.smartkanban/`: worktrees, logs, and evidence (generated).

## Build, Test, and Development Commands
- `make setup`: create `backend/venv` and install backend + frontend deps.
- `make run` or `./run.py`: start Redis, FastAPI, Celery worker, and Vite dev server.
- `make dev-backend` / `make dev-worker` / `make dev-frontend` / `make redis`: run services manually.
- `make db-migrate`: apply Alembic migrations.
- `make lint` / `make format`: run ruff + ESLint/Prettier.
- Frontend build/preview: `cd frontend && npm run build` / `npm run preview`.

## Coding Style & Naming Conventions
- Python: ruff for lint + format, 88-char lines, double quotes, sorted imports. Prefer type hints and clear docstrings.
- TypeScript/React: ESLint + Prettier. Components in `PascalCase`, hooks in `useX`, files in `PascalCase.tsx` or `camelCase.ts` as appropriate.
- Paths: keep backend modules under `backend/app`, tests under `backend/tests`.

## Testing Guidelines
- Backend uses pytest. Run all tests: `cd backend && pytest tests -v`.
- Integration tests require Redis and are marked `-m integration`.
- Tests live in `backend/tests` and follow `test_*.py` naming.

## Commit & Pull Request Guidelines
- Git history shows no strict convention. Use short, imperative summaries (e.g., “Fix planner transition guard”), optionally prefixed with area (`backend:`, `frontend:`).
- PRs should include: a clear description, linked issues/tickets, and screenshots for UI changes. Note any migrations or config updates.

## Security & Configuration Tips
- Set backend environment variables in `backend/.env` (see `backend/ENV_SETUP.md`).
- Verification commands run from `smartkanban.yaml`; keep them repo-root safe (e.g., `cd backend && pytest tests -v`).
