"""Pydantic schemas for the API key module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApiKeyCreate(BaseModel):
    name: str
    rate_limit_per_minute: int | None = None


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    rate_limit_per_minute: int | None = None
    created_at: datetime
    revoked_at: datetime | None = None


class ApiKeyCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    key: str
