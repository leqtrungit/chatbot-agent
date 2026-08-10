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
