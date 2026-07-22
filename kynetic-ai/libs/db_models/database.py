"""
SQLAlchemy 2.0 async engine, session factory, and declarative base.

All services import `async_session_factory` and `Base` from here.
The engine is configured from the DATABASE_URL environment variable.

Usage:
    from libs.db_models.database import async_session_factory, Base

    async with async_session_factory() as session:
        result = await session.execute(select(User))
"""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


# ---------------------------------------------------------------------------
# Base class for all models
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Shared declarative base. All SQLAlchemy models inherit from this."""
    pass


# ---------------------------------------------------------------------------
# Engine and session factory
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://kynetic:kynetic@localhost:5432/kynetic",
)

engine = create_async_engine(
    DATABASE_URL,
    echo=os.environ.get("SQLALCHEMY_ECHO", "false").lower() == "true",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,          # Detect stale connections before use
    pool_recycle=3600,           # Recycle connections after 1 hour
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,      # Avoid lazy-load errors after commit
    autoflush=False,
)


async def get_db_session() -> AsyncSession:
    """
    FastAPI dependency that yields a database session per request.

    Usage in a route:
        from libs.db_models.database import get_db_session
        from sqlalchemy.ext.asyncio import AsyncSession

        @router.get("/example")
        async def example(session: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
