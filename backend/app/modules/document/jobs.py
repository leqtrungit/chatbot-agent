"""arq job enqueue helpers.

Kept separate/small so tests can monkeypatch ``get_arq_pool`` without
requiring a running Redis instance. The worker itself (that consumes the
"ingest_document" job and calls ``app.modules.document.pipeline.ingest``)
is wired up elsewhere.
"""

from __future__ import annotations

import uuid

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings

_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    return _pool


async def enqueue_ingest_job(document_id: uuid.UUID) -> None:
    pool = await get_arq_pool()
    await pool.enqueue_job("ingest_document", str(document_id))
