"""arq job enqueue/status helpers for the webhook + jobs endpoints.

Kept separate/small so tests can monkeypatch these without requiring a
running Redis instance, mirroring ``app.modules.document.jobs``.
"""

from __future__ import annotations

from typing import Any

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus

from app.core.config import get_settings

_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    return _pool


async def enqueue_chat_job(
    *,
    agent_id: str,
    session_id: str,
    text: str,
    metadata: dict[str, Any],
    platform: str,
) -> str:
    pool = await get_arq_pool()
    job = await pool.enqueue_job(
        "process_chat_job",
        agent_id=agent_id,
        session_id=session_id,
        text=text,
        metadata=metadata,
        platform=platform,
    )
    assert job is not None  # enqueue_job only returns None on job-id collision
    return job.job_id


_STATUS_MAP = {
    JobStatus.deferred: "queued",
    JobStatus.queued: "queued",
    JobStatus.in_progress: "in_progress",
    JobStatus.complete: "complete",
    JobStatus.not_found: "not_found",
}


async def get_job_status(job_id: str) -> dict[str, Any]:
    pool = await get_arq_pool()
    job = Job(job_id, pool)
    status = await job.status()

    if status == JobStatus.not_found:
        return {"job_id": job_id, "status": "not_found", "result": None}

    mapped = _STATUS_MAP[status]
    result: Any = None

    if mapped == "complete":
        info = await job.result_info()
        if info is not None:
            if info.success:
                result = info.result
            else:
                mapped = "failed"
                result = {"error": str(info.result)}

    return {"job_id": job_id, "status": mapped, "result": result}
