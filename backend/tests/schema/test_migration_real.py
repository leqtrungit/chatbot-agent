"""Run the real alembic migration against a scratch database.

The other schema tests build the schema via ``Base.metadata.create_all`` for
speed, which never exercises the hand-written migration (pgvector extension,
HNSW index). This module upgrades a dedicated scratch DB with the actual
alembic migration and asserts the artifacts autogenerate cannot produce.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import asyncpg
import pytest

from app.core.config import get_settings

SCRATCH_DB = "chatbot_migration_test"
BACKEND_DIR = Path(__file__).resolve().parents[2]


def _url(db: str, driver: str = "postgresql+asyncpg") -> str:
    base = get_settings().database_url.rsplit("/", 1)[0]
    return f"{base.replace('postgresql+asyncpg', driver)}/{db}"


async def _recreate_scratch_db() -> None:
    conn = await asyncpg.connect(dsn=_url("chatbot", driver="postgresql"))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{SCRATCH_DB}"')
    finally:
        await conn.close()


def _alembic(*args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DATABASE_URL"] = _url(SCRATCH_DB)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.mark.asyncio
async def test_alembic_upgrade_head_produces_full_schema() -> None:
    await _recreate_scratch_db()

    result = _alembic("upgrade", "head")
    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

    conn = await asyncpg.connect(dsn=_url(SCRATCH_DB, driver="postgresql"))
    try:
        tables = {
            r["tablename"]
            for r in await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        }
        expected = {
            "organizations",
            "api_keys",
            "agents",
            "knowledge_bases",
            "documents",
            "document_chunks",
            "kb_agents",
        }
        assert expected <= tables, f"missing tables: {expected - tables}"

        ext = await conn.fetchval("SELECT 1 FROM pg_extension WHERE extname='vector'")
        assert ext == 1, "pgvector extension not created by migration"

        hnsw = await conn.fetchval(
            "SELECT 1 FROM pg_indexes WHERE indexname='ix_document_chunks_embedding_hnsw'"
        )
        assert hnsw == 1, "HNSW index not created by migration"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_alembic_downgrade_base_is_clean() -> None:
    await _recreate_scratch_db()
    assert _alembic("upgrade", "head").returncode == 0

    result = _alembic("downgrade", "base")
    assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

    conn = await asyncpg.connect(dsn=_url(SCRATCH_DB, driver="postgresql"))
    try:
        tables = {
            r["tablename"]
            for r in await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        }
        leftover = tables - {"alembic_version"}
        assert not leftover, f"downgrade left tables behind: {leftover}"
    finally:
        await conn.close()
