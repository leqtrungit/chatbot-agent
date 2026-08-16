"""Admin REST endpoints for usage/analytics dashboards."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import require_admin
from app.modules.analytics import service
from app.modules.analytics.schemas import (
    AnalyticsRange,
    BreakdownBy,
    BreakdownRow,
    TimeseriesPoint,
    UsageSummary,
)

router = APIRouter(
    prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(require_admin)]
)


@router.get("/summary", response_model=UsageSummary)
async def summary(
    range: AnalyticsRange = "7d", session: AsyncSession = Depends(get_session)
) -> UsageSummary:
    since = service.range_to_since(range)
    return await service.get_summary(session, since)


@router.get("/timeseries", response_model=list[TimeseriesPoint])
async def timeseries(
    range: AnalyticsRange = "7d", session: AsyncSession = Depends(get_session)
) -> list[TimeseriesPoint]:
    since = service.range_to_since(range)
    bucket = service.bucket_for_range(range)
    return await service.get_timeseries(session, since, bucket)


@router.get("/breakdown", response_model=list[BreakdownRow])
async def breakdown(
    by: BreakdownBy, range: AnalyticsRange = "7d", session: AsyncSession = Depends(get_session)
) -> list[BreakdownRow]:
    since = service.range_to_since(range)
    return await service.get_breakdown(session, since, by)
