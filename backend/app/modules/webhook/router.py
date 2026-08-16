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
from app.modules.apikey.deps import build_job_metadata, enforce_rate_limits, require_api_key, resolve_agent_or_404
from app.modules.apikey.models import ApiKey
from app.modules.webhook import jobs as job_helpers
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

    await enforce_rate_limits(redis, api_key, message.session_id, settings)

    agent = await resolve_agent_or_404(session, message.agent_id)

    metadata = build_job_metadata(message.metadata, api_key)

    job_id = await job_helpers.enqueue_chat_job(
        agent_id=str(agent.id),
        session_id=message.session_id,
        text=message.text,
        metadata=metadata,
        platform=platform,
        history=[item.model_dump() for item in message.history] if message.history is not None else None,
    )
    return WebhookAck(job_id=job_id)


@jobs_router.get("/api/jobs/{job_id}", response_model=JobStatusRead)
async def get_job(job_id: str, api_key: ApiKey = Depends(require_api_key)) -> JobStatusRead:
    status_info = await job_helpers.get_job_status(job_id)
    if status_info["status"] == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobStatusRead(**status_info)
