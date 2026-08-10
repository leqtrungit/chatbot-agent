"""Business logic for request-usage logging and aggregation queries."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.models import Agent
from app.modules.analytics.models import RequestLog
from app.modules.analytics.schemas import (
    AnalyticsRange,
    BreakdownBy,
    BreakdownRow,
    TimeseriesPoint,
    UsageSummary,
)
from app.modules.apikey.models import ApiKey

_RANGE_TO_TIMEDELTA: dict[AnalyticsRange, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def range_to_since(range_: AnalyticsRange, *, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now - _RANGE_TO_TIMEDELTA[range_]


def bucket_for_range(range_: AnalyticsRange) -> Literal["hour", "day"]:
    return "hour" if range_ == "24h" else "day"


async def record_request(
    session: AsyncSession,
    *,
    job_id: str,
    api_key_id: uuid.UUID,
    agent_id: uuid.UUID,
    session_id: str,
    platform: str,
    model_name: str,
    provider: str,
    usage: dict[str, int],
    iterations: int,
    stopped_on: str | None,
    status: str,
    error_message: str | None,
    latency_ms: int,
) -> RequestLog:
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    log = RequestLog(
        job_id=job_id,
        api_key_id=api_key_id,
        agent_id=agent_id,
        session_id=session_id,
        platform=platform,
        model_name=model_name,
        provider=provider,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        iterations=iterations,
        stopped_on=stopped_on,
        status=status,
        error_message=error_message[:500] if error_message else None,
        latency_ms=latency_ms,
    )
    session.add(log)
    await session.commit()
    return log


async def get_summary(session: AsyncSession, since: datetime) -> UsageSummary:
    error_count_expr = func.sum(case((RequestLog.status == "error", 1), else_=0))
    stmt = select(
        func.count(RequestLog.id),
        func.coalesce(error_count_expr, 0),
        func.coalesce(func.sum(RequestLog.prompt_tokens), 0),
        func.coalesce(func.sum(RequestLog.completion_tokens), 0),
        func.coalesce(func.avg(RequestLog.latency_ms), 0.0),
    ).where(RequestLog.created_at >= since)

    result = await session.execute(stmt)
    total, error_count, prompt_tokens, completion_tokens, avg_latency = result.one()

    total = int(total)
    error_count = int(error_count)
    success_count = total - error_count

    return UsageSummary(
        total_requests=total,
        success_requests=success_count,
        error_requests=error_count,
        error_rate=(error_count / total) if total else 0.0,
        total_prompt_tokens=int(prompt_tokens),
        total_completion_tokens=int(completion_tokens),
        total_tokens=int(prompt_tokens) + int(completion_tokens),
        avg_latency_ms=float(avg_latency),
    )


async def get_timeseries(
    session: AsyncSession, since: datetime, bucket: Literal["hour", "day"]
) -> list[TimeseriesPoint]:
    bucket_expr = func.date_trunc(bucket, RequestLog.created_at).label("bucket")
    error_count_expr = func.sum(case((RequestLog.status == "error", 1), else_=0))
    stmt = (
        select(
            bucket_expr,
            func.count(RequestLog.id),
            func.coalesce(func.sum(RequestLog.total_tokens), 0),
            func.coalesce(error_count_expr, 0),
        )
        .where(RequestLog.created_at >= since)
        .group_by(bucket_expr)
        .order_by(bucket_expr)
    )
    result = await session.execute(stmt)
    return [
        TimeseriesPoint(bucket=row[0], requests=row[1], total_tokens=int(row[2]), error_count=int(row[3]))
        for row in result.all()
    ]


async def get_breakdown(session: AsyncSession, since: datetime, by: BreakdownBy) -> list[BreakdownRow]:
    error_count_expr = func.sum(case((RequestLog.status == "error", 1), else_=0))
    requests_expr = func.count(RequestLog.id)
    tokens_expr = func.coalesce(func.sum(RequestLog.total_tokens), 0)

    if by == "api_key":
        stmt = (
            select(ApiKey.id, ApiKey.name, requests_expr, tokens_expr, func.coalesce(error_count_expr, 0))
            .join(ApiKey, ApiKey.id == RequestLog.api_key_id)
            .where(RequestLog.created_at >= since)
            .group_by(ApiKey.id, ApiKey.name)
            .order_by(requests_expr.desc())
        )
    elif by == "agent":
        stmt = (
            select(Agent.id, Agent.name, requests_expr, tokens_expr, func.coalesce(error_count_expr, 0))
            .join(Agent, Agent.id == RequestLog.agent_id)
            .where(RequestLog.created_at >= since)
            .group_by(Agent.id, Agent.name)
            .order_by(requests_expr.desc())
        )
    elif by == "model":
        stmt = (
            select(
                RequestLog.model_name, RequestLog.model_name, requests_expr, tokens_expr,
                func.coalesce(error_count_expr, 0),
            )
            .where(RequestLog.created_at >= since)
            .group_by(RequestLog.model_name)
            .order_by(requests_expr.desc())
        )
    else:  # status
        stmt = (
            select(
                RequestLog.status, RequestLog.status, requests_expr, tokens_expr,
                func.coalesce(error_count_expr, 0),
            )
            .where(RequestLog.created_at >= since)
            .group_by(RequestLog.status)
            .order_by(requests_expr.desc())
        )

    result = await session.execute(stmt)
    rows = []
    for key_id, key, requests, tokens, error_count in result.all():
        rows.append(
            BreakdownRow(
                key=str(key),
                key_id=str(key_id) if by in ("api_key", "agent") else None,
                requests=requests,
                total_tokens=int(tokens),
                error_count=int(error_count),
            )
        )
    return rows
