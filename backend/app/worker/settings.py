"""arq worker entrypoint: ``arq app.worker.settings.WorkerSettings``."""

from __future__ import annotations

from typing import Any

from arq import func
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.worker.tasks import (
    build_embedding_provider,
    ingest_document_task,
    process_chat_job,
    process_chat_job_stream,
)

_settings = get_settings()


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, future=True)
    ctx["engine"] = engine
    ctx["session_maker"] = async_sessionmaker(engine, expire_on_commit=False)
    ctx["embedding_provider"] = build_embedding_provider(settings)
    ctx["settings"] = settings


async def shutdown(ctx: dict[str, Any]) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


class WorkerSettings:
    functions = [
        func(ingest_document_task, name="ingest_document"),
        func(process_chat_job, name="process_chat_job"),
        func(process_chat_job_stream, name="process_chat_job_stream"),
    ]
    redis_settings = RedisSettings.from_dsn(_settings.REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
