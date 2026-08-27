"""Fixtures for schema tests: a real Postgres test database with schema migrations applied."""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base, get_session
from app.core.config import get_settings

# Import all models to register them with Base.metadata
from app.orgs import models as orgs_models  # noqa: F401
from app.apikeys import models as apikeys_models  # noqa: F401
from app.agents import models as agents_models  # noqa: F401
from app.knowledge import models as knowledge_models  # noqa: F401

TEST_DB_NAME = "chatbot_test"


def _server_dsn() -> str:
    """Get DSN for connection to postgres server (not a specific DB)."""
    settings = get_settings()
    # DATABASE_URL points at the "chatbot" database; reuse host/creds.
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://").rsplit(
        "/", 1
    )[0] + "/chatbot"


def _test_db_url() -> str:
    """Get URL for test database."""
    settings = get_settings()
    base = settings.database_url.rsplit("/", 1)[0]
    return f"{base}/{TEST_DB_NAME}"


async def _ensure_test_database() -> None:
    """Create test database and pgvector extension if they don't exist."""
    conn = await asyncpg.connect(dsn=_server_dsn())
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await conn.close()

    test_conn = await asyncpg.connect(dsn=_test_db_url().replace("+asyncpg", ""))
    try:
        await test_conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        await test_conn.close()


@pytest_asyncio.fixture
async def test_engine():
    """Create a test database engine and run migrations."""
    await _ensure_test_database()
    engine = create_async_engine(_test_db_url(), future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_maker(test_engine):
    """Create an async session maker."""
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(test_engine, session_maker) -> AsyncIterator[AsyncSession]:
    """Provide a database session for each test, then truncate all tables."""
    async with session_maker() as session:
        yield session

    # truncate all tables so each test starts clean
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
