"""Request/response schemas for the chat streaming endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatStreamRequest(BaseModel):
    """Request body for POST /api/chat/stream."""

    agent_id: str
    session_id: str | None = None
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
