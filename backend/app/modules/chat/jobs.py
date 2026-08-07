"""arq job enqueueing for the chat streaming endpoint.

Kept separate/small so tests can monkeypatch these without requiring a
running Redis instance, mirroring ``app.modules.document.jobs``.
"""

from __future__ import annotations

from typing import Any

from app.modules.webhook.jobs import get_arq_pool


async def enqueue_chat_stream_job(
    *,
    job_id: str,
    agent_id: str,
    session_id: str,
    text: str,
    metadata: dict[str, Any],
    platform: str,
) -> None:
    """Enqueue a streaming chat job to be processed by the worker.

    Args:
        job_id: Pre-generated job ID (caller's responsibility to generate
            and subscribe to the pubsub channel before calling this).
        agent_id: The agent (provider/model/tools config) to run.
        session_id: Session identifier for grouping related messages.
        text: The user's message.
        metadata: Additional metadata (will include app_id and app_name).
        platform: The platform identifier (e.g. "generic").
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job(
        "process_chat_job_stream",
        _job_id=job_id,
        agent_id=agent_id,
        session_id=session_id,
        text=text,
        metadata=metadata,
        platform=platform,
    )
    assert job is not None  # enqueue_job only returns None on job-id collision
