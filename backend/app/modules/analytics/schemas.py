"""Pydantic schemas for the analytics (usage/cost-free metrics) module."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AnalyticsRange = Literal["24h", "7d", "30d"]
BreakdownBy = Literal["api_key", "agent", "model", "status"]


class UsageSummary(BaseModel):
    total_requests: int
    success_requests: int
    error_requests: int
    error_rate: float
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    avg_latency_ms: float


class TimeseriesPoint(BaseModel):
    bucket: datetime
    requests: int
    total_tokens: int
    error_count: int


class BreakdownRow(BaseModel):
    key: str
    key_id: str | None = None
    requests: int
    total_tokens: int
    error_count: int
