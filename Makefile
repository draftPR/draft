.PHONY: setup setup-backend setup-frontend run dev-backend dev-frontend db-migrate lint lint-backend lint-frontend format format-backend format-frontend clean generate-types test test-backend test-frontend

# Default target
help:
	@echo "Draft - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup          - Install all dependencies (frontend + backend)"
	@echo "  make setup-backend  - Set up Python virtual environment and install dependencies"
	@echo "  make setup-frontend - Install Node.js dependencies"
	@echo ""
	@echo "Quick Start:"
	@echo "  make run            - Start backend + frontend (2 processes)"
	@echo "  ./run.py            - Alternative: run the launcher script directly"
	@echo ""
	@echo "Development (Manual):"
	@echo "  make dev-backend    - Run FastAPI backend server (http://localhost:8000)"
	@echo "  make dev-frontend   - Run Vite frontend dev server (http://localhost:5173)"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate     - Run Alembic database migrations"
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run all tests (backend + frontend)"
	@echo "  make test-backend   - Run backend pytest tests"
	@echo "  make test-frontend  - Run frontend vitest tests"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint           - Run linters for both frontend and backend"
	@echo "  make lint-backend   - Run ruff linter on Python code"
	@echo "  make lint-frontend  - Run ESLint on TypeScript code"
	@echo "  make format         - Format code in both frontend and backend"
	@echo "  make format-backend - Format Python code with ruff"
	@echo "  make format-frontend- Format TypeScript code with Prettier"
	@echo ""
	@echo "Type Generation:"
	@echo "  make generate-types - Generate TypeScript types from backend OpenAPI spec"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean          - Remove build artifacts and caches"

# Setup targets
setup: setup-backend setup-frontend
	@echo "✓ Setup complete!"

setup-backend:
	@echo "Setting up backend..."
	cd backend && python3 -m venv venv
	cd backend && . venv/bin/activate && pip install -r requirements-dev.txt
	@echo "✓ Backend setup complete!"

setup-frontend:
	@echo "Setting up frontend..."
	cd frontend && npm install
	@echo "✓ Frontend setup complete!"

# Quick start - backend + frontend (2 processes, no Redis needed)
run:
	@echo "Starting Draft..."
	@python3 run.py

# Development targets (manual)
dev-backend:
	cd backend && . venv/bin/activate && uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

# Database targets
db-migrate:
	cd backend && . venv/bin/activate && alembic upgrade head

# Lint targets
lint: lint-backend lint-frontend

lint-backend:
	cd backend && . venv/bin/activate && ruff check .

lint-frontend:
	cd frontend && npm run lint

# Format targets
format: format-backend format-frontend

format-backend:
	cd backend && . venv/bin/activate && ruff format .
	cd backend && . venv/bin/activate && ruff check --fix .

format-frontend:
	cd frontend && npm run format

# Test targets
test: test-backend test-frontend

test-backend:
	cd backend && . venv/bin/activate && pytest tests -v

test-frontend:
	cd frontend && npx vitest run

# Type generation
generate-types:
	@echo "Generating TypeScript types from OpenAPI spec..."
	cd backend && (test -f venv/bin/activate && . venv/bin/activate; python scripts/extract_openapi.py /tmp/draft-openapi.json)
	cd frontend && npx openapi-typescript /tmp/draft-openapi.json -o src/types/generated.ts
	@rm -f /tmp/draft-openapi.json
	@echo "Generated frontend/src/types/generated.ts"

# Clean targets
clean:
	@echo "Cleaning build artifacts..."
	rm -rf frontend/dist
	rm -rf frontend/node_modules/.vite
	rm -rf backend/__pycache__
	rm -rf backend/app/__pycache__
	rm -rf backend/.ruff_cache
	rm -rf backend/.pytest_cache
	rm -f backend/celerybeat-schedule*
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Clean complete!"

