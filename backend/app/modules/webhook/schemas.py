"""Pydantic schemas for the webhook + job status endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class WebhookAck(BaseModel):
    job_id: str


class JobStatusRead(BaseModel):
    job_id: str
    status: Literal["queued", "in_progress", "complete", "failed", "not_found"]
    result: dict[str, Any] | None = None
