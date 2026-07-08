"""Inbound webhook + job status polling endpoints.

No auth: external platforms call these directly. Unlike the admin
document/domain routers, these are the public surface of the app.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import ChannelParseError
from app.channels.registry import ChannelNotRegisteredError, get_channel_registry
from app.core.db import get_session
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

    try:
        domain = await service.resolve_domain(session, message.domain_id)
    except service.DomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found") from exc

    job_id = await job_helpers.enqueue_chat_job(
        domain_id=str(domain.id),
        session_id=message.session_id,
        text=message.text,
        metadata=message.metadata,
        platform=platform,
    )
    return WebhookAck(job_id=job_id)


@jobs_router.get("/api/jobs/{job_id}", response_model=JobStatusRead)
async def get_job(job_id: str) -> JobStatusRead:
    status_info = await job_helpers.get_job_status(job_id)
    if status_info["status"] == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobStatusRead(**status_info)
