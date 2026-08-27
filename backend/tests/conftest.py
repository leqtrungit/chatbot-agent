"""Root fixtures shared by every test package.

The database fixtures live here (not in a package-local conftest) so that
test packages never import another package's conftest — doing so makes
pytest register the same file twice and aborts collection for the whole
suite. Helpers they build on are in ``tests/db_utils.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.main import create_app
from tests.db_utils import ensure_test_database, test_db_url

# Import every model module so Base.metadata is complete before create_all.
from app.agents import models as _agents_models  # noqa: F401
from app.apikeys import models as _apikeys_models  # noqa: F401
from app.knowledge import models as _knowledge_models  # noqa: F401
from app.orgs import models as _orgs_models  # noqa: F401


@pytest.fixture
def app() -> FastAPI:
    """A FastAPI app instance with all production routers mounted."""
    return create_app()


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async HTTP client bound to the app under test."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest_asyncio.fixture
async def test_engine():
    """Engine on a freshly-created schema in the test database."""
    await ensure_test_database()
    engine = create_async_engine(test_db_url(), future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_maker(test_engine):
    """Session factory bound to the test engine."""
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(test_engine, session_maker) -> AsyncIterator[AsyncSession]:
    """A session per test; every table is emptied afterwards."""
    async with session_maker() as session:
        yield session

    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
