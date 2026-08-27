"""Pydantic schemas for the API keys module (FR-T4, NFR-SEC2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    """Request to create an API key."""

    name: str = Field(..., min_length=1, max_length=255)
    rate_limit_per_minute: int | None = Field(None, ge=1)


class ApiKeyRead(BaseModel):
    """API key in list/read responses (never exposes raw key or hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    rate_limit_per_minute: int | None = None
    created_at: datetime
    revoked_at: datetime | None = None


class ApiKeyCreateResponse(BaseModel):
    """Response to create: includes raw key (shown once only)."""

    id: uuid.UUID
    name: str
    key: str  # Raw key: cba_ + 32 hex chars
    rate_limit_per_minute: int | None = None
    created_at: datetime
