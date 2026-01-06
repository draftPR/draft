.PHONY: setup setup-backend setup-frontend dev dev-backend dev-frontend dev-worker redis db-migrate lint lint-backend lint-frontend format format-backend format-frontend clean

# Default target
help:
	@echo "Smart Kanban - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup          - Install all dependencies (frontend + backend)"
	@echo "  make setup-backend  - Set up Python virtual environment and install dependencies"
	@echo "  make setup-frontend - Install Node.js dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make dev-backend    - Run FastAPI backend server (http://localhost:8000)"
	@echo "  make dev-frontend   - Run Vite frontend dev server (http://localhost:5173)"
	@echo "  make dev-worker     - Run Celery worker for background jobs"
	@echo "  make redis          - Start Redis server (required for worker)"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate     - Run Alembic database migrations"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint           - Run linters for both frontend and backend"
	@echo "  make lint-backend   - Run ruff linter on Python code"
	@echo "  make lint-frontend  - Run ESLint on TypeScript code"
	@echo "  make format         - Format code in both frontend and backend"
	@echo "  make format-backend - Format Python code with ruff"
	@echo "  make format-frontend- Format TypeScript code with Prettier"
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

# Development targets
dev-backend:
	cd backend && . venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

dev-worker:
	cd backend && . venv/bin/activate && celery -A app.celery_app worker --loglevel=info

redis:
	redis-server

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

# Clean targets
clean:
	@echo "Cleaning build artifacts..."
	rm -rf frontend/dist
	rm -rf frontend/node_modules/.vite
	rm -rf backend/__pycache__
	rm -rf backend/app/__pycache__
	rm -rf backend/.ruff_cache
	rm -rf backend/.pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Clean complete!"

