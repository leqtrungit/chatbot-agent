"""SSE chat streaming endpoint.

Reuses webhook module's auth, rate-limiting, domain resolution, and arq pool.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.ratelimit import check_rate_limit
from app.modules.apikey.deps import require_api_key
from app.modules.apikey.models import ApiKey
from app.modules.chat import jobs as job_helpers
from app.modules.chat.schemas import ChatStreamRequest
from app.modules.chat.service import relay_job_events, sse_frame
from app.modules.webhook import jobs as webhook_jobs
from app.modules.webhook import service as webhook_service

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

    # Rate limit per API key
    key_limit = api_key.rate_limit_per_minute or settings.RATE_LIMIT_PER_MINUTE
    key_result = await check_rate_limit(redis, f"rl:key:{api_key.id}", key_limit)
    if not key_result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for this API key",
            headers={"Retry-After": str(key_result.retry_after)},
        )

    # Use provided session_id or generate one
    session_id = body.session_id or str(uuid.uuid4())

    # Rate limit per session
    session_result = await check_rate_limit(
        redis,
        f"rl:sess:{api_key.id}:{session_id}",
        settings.RATE_LIMIT_SESSION_PER_MINUTE,
    )
    if not session_result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for this session",
            headers={"Retry-After": str(session_result.retry_after)},
        )

    # Resolve domain by UUID or slug
    try:
        domain = await webhook_service.resolve_domain(session, body.domain_id)
    except webhook_service.DomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found") from exc

    # Generate job_id and subscribe BEFORE enqueueing
    # (critical ordering to avoid missing messages published by the worker)
    job_id = uuid.uuid4().hex
    channel = f"chat:job:{job_id}"
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    # Build metadata (mirror webhook pattern)
    metadata = {**body.metadata, "app_id": str(api_key.id), "app_name": api_key.name}

    # Enqueue the job (now that we're subscribed, no messages will be missed)
    await job_helpers.enqueue_chat_stream_job(
        job_id=job_id,
        domain_id=str(domain.id),
        session_id=session_id,
        text=body.message,
        metadata=metadata,
        platform="generic",
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
