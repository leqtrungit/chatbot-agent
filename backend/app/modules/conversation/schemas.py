"""Pydantic schemas for the conversation history read endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ChatMessageRead(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ConversationMessagesRead(BaseModel):
    messages: list[ChatMessageRead]


class HistoryItemIn(BaseModel):
    """A single client-supplied history turn.

    Restricted to user/assistant (same set the ``chat_messages`` CHECK
    constraint allows) so a client can never inject a spoofed system/tool
    message ahead of the agent's real system prompt.
    """

    role: Literal["user", "assistant"]
    content: str
