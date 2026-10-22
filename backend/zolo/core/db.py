"""Async SQLAlchemy engine and session helpers."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(database_url: str, pool_size: int = 10, max_overflow: int = 10) -> AsyncEngine:
    return create_async_engine(
        database_url, pool_pre_ping=True, pool_size=pool_size, max_overflow=max_overflow
    )


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
