"""Test harness: a throwaway Postgres database, migrated with Alembic, one app per test."""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from zolo.api.main import create_app
from zolo.core.config import Settings
from zolo.core.db import make_engine, make_sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://zolo:zolo@localhost:5432/zolo_test"
)


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": TEST_DB_URL,
        "session_secret": "test-session-secret-0123456789abcdef-test",
        "env": "test",
        "rp_id": "localhost",
        "origin": "http://localhost:3000",
        "cors_origins": "http://localhost:3000",
        "cookie_secure": False,
        "demo_mode": True,
        "demo_token": "test-demo-token",
    }
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


async def _ensure_database() -> None:
    url = make_url(TEST_DB_URL)
    conn = await asyncpg.connect(
        user=url.username, password=url.password, host=url.host, port=url.port, database="postgres"
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()


def _migrate() -> None:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    os.environ["ALEMBIC_DATABASE_URL"] = TEST_DB_URL
    try:
        if any((BACKEND / "migrations" / "versions").glob("*.py")):
            command.upgrade(cfg, "head")
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    await _ensure_database()
    # alembic's env runs its own event loop, so migrate off-loop
    import asyncio

    await asyncio.to_thread(_migrate)
    eng = make_engine(TEST_DB_URL)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A clean database for each test: every table emptied (ledger and audit included)."""
    async with engine.begin() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename <> 'alembic_version'"
                )
            )
        ).scalars().all()  # fmt: skip
        if tables:
            names = ", ".join(f'"{t}"' for t in tables)
            await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    yield make_sessionmaker(engine)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest_asyncio.fixture
async def app(
    settings: Settings, sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[object]:
    application = create_app(settings)
    application.state.sessionmaker = sessionmaker
    yield application


@pytest_asyncio.fixture
async def client(app: object) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def _quiet_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-0123456789abcdef-test")
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
    yield
