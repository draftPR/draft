# =============================================================================
# Draft - Multi-stage Docker build
# =============================================================================
# Stage 1: Python dependencies
# Stage 2: Frontend build
# Stage 3: Slim runtime
# =============================================================================

# --------------- Stage 1: Python builder ---------------
FROM python:3.11-slim AS python-builder

WORKDIR /build

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --------------- Stage 2: Frontend builder ---------------
FROM node:20-slim AS frontend-builder

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps

COPY frontend/ .
RUN npm run build

# --------------- Stage 3: Runtime ---------------
FROM python:3.11-slim AS runtime

# Install git (needed for worktree operations)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash draft

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=python-builder /install /usr/local

# Copy backend source
COPY backend/ ./backend/

# Copy built frontend
COPY --from=frontend-builder /build/dist ./frontend/dist/

# Copy configuration files
COPY Makefile run.py draft.yaml* ./

# Create data directories
RUN mkdir -p /app/data /app/logs && chown -R draft:draft /app

# Set environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TASK_BACKEND=sqlite \
    DATABASE_URL=sqlite+aiosqlite:///./data/draft.db \
    STATIC_FILES_DIR=/app/frontend/dist

USER draft

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

# Default: run the launcher (starts backend + worker)
CMD ["python", "run.py"]
