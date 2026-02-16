"""Database connection and session management for Alma Kanban."""

import os
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

# Get the backend directory (where this file lives is app/, so go up one level)
_BACKEND_DIR = Path(__file__).parent.parent.resolve()

# Database URL - defaults to SQLite file in the backend directory
# Use absolute path to ensure consistency across different working directories
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{_BACKEND_DIR}/kanban.db")

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    future=True,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Initialize the database by creating all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to inject database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
