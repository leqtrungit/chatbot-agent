"""Request/response schemas for the chat streaming endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.modules.conversation.schemas import HistoryItemIn


class ChatStreamRequest(BaseModel):
    """Request body for POST /api/chat/stream."""

    agent_id: str
    session_id: str | None = None
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    history: list[HistoryItemIn] | None = None
    """Client-managed history for this turn — see ``IncomingMessage.history``
    (``app.channels.base``) for the semantics; same opt-in contract applies
    on this SSE entry point."""

    @field_validator("history")
    @classmethod
    def _validate_history_length(cls, value: list[HistoryItemIn] | None) -> list[HistoryItemIn] | None:
        if value is None:
            return value
        max_len = get_settings().MAX_CLIENT_HISTORY_MESSAGES
        if len(value) > max_len:
            raise ValueError(f"'history' exceeds the maximum of {max_len} messages")
        return value
