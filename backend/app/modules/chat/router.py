"""SSE chat streaming endpoint.

Reuses webhook module's auth, rate-limiting, and arq pool.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.modules.apikey.deps import build_job_metadata, enforce_rate_limits, require_api_key, resolve_agent_or_404
from app.modules.apikey.models import ApiKey
from app.modules.chat import jobs as job_helpers
from app.modules.chat.schemas import ChatStreamRequest
from app.modules.chat.service import relay_job_events, sse_frame
from app.modules.webhook import jobs as webhook_jobs

chat_router = APIRouter(tags=["chat"])


@chat_router.post("/api/chat/stream")
async def stream_chat(
    body: ChatStreamRequest,
    session: AsyncSession = Depends(get_session),
    api_key: ApiKey = Depends(require_api_key),
) -> StreamingResponse:
    """Stream chat responses via Server-Sent Events.

    Accepts a chat message and streams back the agent's response token-by-token
    via SSE, plus metadata about completion (iterations, stopped_on reason).

    Rate-limited per API key and per session (same limits as webhook).
    """
    settings = get_settings()

    # Get the shared Redis pool (reuse webhook's singleton)
    redis = await webhook_jobs.get_arq_pool()

    # Use provided session_id or generate one
    session_id = body.session_id or str(uuid.uuid4())

    await enforce_rate_limits(redis, api_key, session_id, settings)

    agent = await resolve_agent_or_404(session, body.agent_id)

    # Generate job_id and subscribe BEFORE enqueueing
    # (critical ordering to avoid missing messages published by the worker)
    job_id = uuid.uuid4().hex
    channel = f"chat:job:{job_id}"
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    metadata = build_job_metadata(body.metadata, api_key)

    # Enqueue the job (now that we're subscribed, no messages will be missed)
    await job_helpers.enqueue_chat_stream_job(
        job_id=job_id,
        agent_id=str(agent.id),
        session_id=session_id,
        text=body.message,
        metadata=metadata,
        platform="generic",
        history=[item.model_dump() for item in body.history] if body.history is not None else None,
    )

    async def event_generator():
        """Generate SSE frames from job events."""
        try:
            # Emit synthetic queued frame immediately (before subscribing to relay)
            yield sse_frame({"type": "queued", "job_id": job_id})
            # Relay all worker events from pubsub
            async for frame in relay_job_events(pubsub):
                yield frame
        finally:
            # Clean up pubsub
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
