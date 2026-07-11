"""Fixtures for module tests: a real Postgres test database + ASGI client."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import Base, get_session
from app.modules.apikey import models as apikey_models  # noqa: F401
from app.modules.document import models as document_models  # noqa: F401
from app.modules.domain import models as domain_models  # noqa: F401

TEST_DB_NAME = "chatbot_test"


@pytest_asyncio.fixture(autouse=True)
async def _reset_arq_pool() -> AsyncIterator[None]:
    """``app.modules.webhook.jobs`` caches the arq/redis pool in a module
    global; pytest-asyncio gives each test its own event loop, so a pool
    created in a previous test's loop breaks ("Event loop is closed") if
    reused here. Reset the singleton around every test."""
    import app.modules.webhook.jobs as job_helpers

    job_helpers._pool = None
    yield
    if job_helpers._pool is not None:
        await job_helpers._pool.aclose()
    job_helpers._pool = None


def _server_dsn() -> str:
    settings = get_settings()
    # DATABASE_URL points at the "chatbot" maintenance db; reuse host/creds.
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://").rsplit(
        "/", 1
    )[0] + "/chatbot"


def _test_db_url() -> str:
    settings = get_settings()
    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    return f"{base}/{TEST_DB_NAME}"


async def _ensure_test_database() -> None:
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
    # Function-scoped (not session-scoped) because pytest-asyncio gives each
    # test function its own event loop by default; asyncpg connections/pools
    # cannot be reused across event loops.
    await _ensure_test_database()
    engine = create_async_engine(_test_db_url(), future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_maker(test_engine):
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(test_engine, session_maker) -> AsyncIterator[AsyncSession]:
    async with session_maker() as session:
        yield session

    # truncate all tables so each test starts clean
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def client(test_engine, session_maker) -> AsyncIterator[AsyncClient]:
    from app.main import app

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_session, None)

    # truncate all tables so each test starts clean
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture
def admin_auth_header() -> dict[str, str]:
    settings = get_settings()
    token = base64.b64encode(
        f"{settings.ADMIN_USERNAME}:{settings.ADMIN_PASSWORD}".encode()
    ).decode()
    return {"Authorization": f"Basic {token}"}


@pytest_asyncio.fixture
async def api_key_header(client: AsyncClient, admin_auth_header: dict[str, str]) -> dict[str, str]:
    """Creates a fresh active API key through the admin API and returns the
    ``X-API-Key`` header ready to attach to a webhook/job request."""
    resp = await client.post(
        "/api/api-keys",
        json={"name": "Test App"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 201, resp.text
    return {"X-API-Key": resp.json()["key"]}
