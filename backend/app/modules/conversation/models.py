"""ORM models for the conversation module (chat history persistence)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ChatMessage(Base):
    """A single persisted turn (user or assistant) for an (agent, session).

    Only the user's message and the agent's final answer are stored — no
    intermediate tool-call traffic — which is enough to reconstruct history
    for the next turn while keeping the table small.
    """

    __tablename__ = "chat_messages"
    __table_args__ = (
        Index(
            "ix_chat_messages_agent_session_created",
            "agent_id",
            "session_id",
            "created_at",
        ),
        CheckConstraint("role IN ('user', 'assistant')", name="ck_chat_messages_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
