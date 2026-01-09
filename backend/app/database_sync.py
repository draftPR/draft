"""Synchronous database connection for Celery workers."""

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Get the backend directory (where this file lives is app/, so go up one level)
_BACKEND_DIR = Path(__file__).parent.parent.resolve()

# Synchronous database URL - defaults to SQLite file in the backend directory
# Use absolute path to ensure worker finds the same database as the server
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_BACKEND_DIR}/kanban.db")
if DATABASE_URL.startswith("sqlite+aiosqlite"):
    DATABASE_URL = DATABASE_URL.replace("sqlite+aiosqlite", "sqlite")

# Create synchronous engine
sync_engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    future=True,
)

# Synchronous session factory
SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@contextmanager
def get_sync_db() -> Generator[Session, None, None]:
    """Context manager for synchronous database sessions (used by Celery workers)."""
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
