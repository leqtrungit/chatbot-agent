"""Inbound webhook + job status polling endpoints.

Public surface of the app for external platforms — but not anonymous:
callers must present a valid ``X-API-Key`` identifying the integration app
(see ``app.modules.apikey``). The webhook route additionally enforces
fixed-window rate limits per API key and per session.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import ChannelParseError
from app.channels.registry import ChannelNotRegisteredError, get_channel_registry
from app.core.config import get_settings
from app.core.db import get_session
from app.core.ratelimit import check_rate_limit
from app.modules.apikey.deps import require_api_key
from app.modules.apikey.models import ApiKey
from app.modules.webhook import jobs as job_helpers
from app.modules.webhook import service
from app.modules.webhook.schemas import JobStatusRead, WebhookAck

webhook_router = APIRouter(tags=["webhooks"])
jobs_router = APIRouter(tags=["jobs"])


@webhook_router.post(
    "/api/webhooks/{platform}",
    response_model=WebhookAck,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_webhook(
    platform: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    api_key: ApiKey = Depends(require_api_key),
) -> WebhookAck:
    registry = get_channel_registry()
    try:
        adapter = registry.get(platform)
    except ChannelNotRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown platform") from exc

    payload = await request.json()
    headers = dict(request.headers)

    try:
        message = await adapter.parse_incoming(payload, headers)
    except ChannelParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    settings = get_settings()
    redis = await job_helpers.get_arq_pool()

    key_limit = api_key.rate_limit_per_minute or settings.RATE_LIMIT_PER_MINUTE
    key_result = await check_rate_limit(redis, f"rl:key:{api_key.id}", key_limit)
    if not key_result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for this API key",
            headers={"Retry-After": str(key_result.retry_after)},
        )

    session_result = await check_rate_limit(
        redis,
        f"rl:sess:{api_key.id}:{message.session_id}",
        settings.RATE_LIMIT_SESSION_PER_MINUTE,
    )
    if not session_result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for this session",
            headers={"Retry-After": str(session_result.retry_after)},
        )

    try:
        domain = await service.resolve_domain(session, message.domain_id)
    except service.DomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found") from exc

    metadata = {**message.metadata, "app_id": str(api_key.id), "app_name": api_key.name}

    job_id = await job_helpers.enqueue_chat_job(
        domain_id=str(domain.id),
        session_id=message.session_id,
        text=message.text,
        metadata=metadata,
        platform=platform,
    )
    return WebhookAck(job_id=job_id)


@jobs_router.get("/api/jobs/{job_id}", response_model=JobStatusRead)
async def get_job(job_id: str, api_key: ApiKey = Depends(require_api_key)) -> JobStatusRead:
    status_info = await job_helpers.get_job_status(job_id)
    if status_info["status"] == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobStatusRead(**status_info)
