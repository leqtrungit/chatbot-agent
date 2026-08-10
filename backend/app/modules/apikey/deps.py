"""FastAPI dependencies + shared request-handling helpers for the public,
API-key-authenticated surface (webhook, chat/stream, conversations). Kept
separate from ``router.py`` so those modules can import just this without
pulling in the admin router."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import get_session
from app.core.ratelimit import RedisLike, check_rate_limit
from app.modules.agent import service as agent_service
from app.modules.agent.models import Agent
from app.modules.apikey import service
from app.modules.apikey.models import ApiKey


async def require_api_key(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ApiKey:
    raw_key = request.headers.get("X-API-Key")
    if not raw_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    api_key = await service.get_active_key_by_raw(session, raw_key)
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key")

    return api_key


async def resolve_agent_or_404(session: AsyncSession, agent_id: str) -> Agent:
    """Parse ``agent_id`` and load the agent, raising a 404 for either an
    invalid UUID or an unknown agent (same response either way — callers
    shouldn't be able to distinguish "malformed id" from "doesn't exist")."""
    try:
        agent_uuid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    try:
        return await agent_service.get_agent(session, agent_uuid)
    except agent_service.AgentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


async def enforce_rate_limits(
    redis: RedisLike, api_key: ApiKey, session_id: str, settings: Settings
) -> None:
    """Apply the per-key and per-session fixed-window rate limits shared by
    every job-producing endpoint (webhook, chat/stream). Raises 429 with a
    ``Retry-After`` header when either limit is exceeded."""
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
        f"rl:sess:{api_key.id}:{session_id}",
        settings.RATE_LIMIT_SESSION_PER_MINUTE,
    )
    if not session_result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for this session",
            headers={"Retry-After": str(session_result.retry_after)},
        )


def build_job_metadata(metadata: dict[str, Any], api_key: ApiKey) -> dict[str, Any]:
    """Stamp caller identity onto job metadata, shared by every endpoint
    that enqueues a chat job on behalf of an API key."""
    return {**metadata, "app_id": str(api_key.id), "app_name": api_key.name}
