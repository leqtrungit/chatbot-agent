"""Pydantic schemas for the MCP server module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

VALID_TRANSPORTS = ("http", "sse")


class McpServerCreate(BaseModel):
    name: str
    url: str
    transport: str = "http"
    headers: dict[str, str] | None = None
    is_active: bool = True


class McpServerUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    transport: str | None = None
    headers: dict[str, str] | None = None
    is_active: bool | None = None


class McpServerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    transport: str
    headers: dict[str, str] | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
