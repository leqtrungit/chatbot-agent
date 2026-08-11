"""Message shapes and the abstract adapter every platform must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from app.modules.conversation.schemas import HistoryItemIn


class ChannelParseError(ValueError):
    """Raised by ``parse_incoming`` when a webhook payload is invalid."""


class IncomingMessage(BaseModel):
    agent_id: str
    session_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    history: list[HistoryItemIn] | None = None
    """Client-managed history for this turn, if supplied.

    ``None`` (the field absent from the payload) means server-managed
    history: the worker loads/persists via ``chat_messages`` as before.
    A list (even empty) means the client owns history for this session:
    the worker uses it directly and skips loading/persisting.
    """


class OutgoingMessage(BaseModel):
    session_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelAdapter(ABC):
    """Translates a platform's webhook payloads to/from normalized messages."""

    @property
    @abstractmethod
    def platform(self) -> str:
        """Slug identifying this platform, e.g. ``"generic"``."""

    @abstractmethod
    async def parse_incoming(
        self, payload: dict[str, Any], headers: dict[str, str]
    ) -> IncomingMessage:
        """Parse a raw webhook payload into a normalized message.

        Raises ``ChannelParseError`` if the payload is invalid.
        """

    async def send_response(self, message: OutgoingMessage) -> None:
        """Push a reply back to the platform.

        Default no-op: today clients poll job status instead of receiving a
        push. Future platforms (e.g. one that requires an outbound API call
        to deliver a reply) override this.
        """
        return None
