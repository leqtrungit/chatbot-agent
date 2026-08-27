"""Test-database helpers.

A plain module — NOT a conftest — so any test package can import it without
pytest registering the same file twice as a plugin (which aborts collection
for the whole suite).

The shared fixtures built on top of these helpers live in the root
``tests/conftest.py``; test packages just request ``db_session``.
"""

from __future__ import annotations

import asyncpg

from app.core.config import get_settings

TEST_DB_NAME = "chatbot_test"


def server_dsn() -> str:
    """DSN for the maintenance connection (the default ``chatbot`` database)."""
    settings = get_settings()
    base = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    return base.rsplit("/", 1)[0] + "/chatbot"


def test_db_url(driver: str = "postgresql+asyncpg") -> str:
    """SQLAlchemy URL of the test database."""
    settings = get_settings()
    base = settings.database_url.rsplit("/", 1)[0]
    return f"{base.replace('postgresql+asyncpg', driver)}/{TEST_DB_NAME}"


async def ensure_test_database() -> None:
    """Create the test database and its pgvector extension if missing."""
    conn = await asyncpg.connect(dsn=server_dsn())
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await conn.close()

    test_conn = await asyncpg.connect(dsn=test_db_url(driver="postgresql"))
    try:
        await test_conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        await test_conn.close()
