"""Generic adapter: the reference/default platform, and what tests target.

Payload shape: {"agent_id": ..., "session_id": ...
(optional), "message": ..., "metadata": {...} (optional)}
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError

from app.channels.base import ChannelAdapter, ChannelParseError, IncomingMessage
from app.core.config import get_settings
from app.modules.conversation.schemas import HistoryItemIn


class GenericAdapter(ChannelAdapter):
    @property
    def platform(self) -> str:
        return "generic"

    async def parse_incoming(
        self, payload: dict[str, Any], headers: dict[str, str]
    ) -> IncomingMessage:
        agent_id = payload.get("agent_id")
        message = payload.get("message")

        if not agent_id or not isinstance(agent_id, str):
            raise ChannelParseError("Missing or invalid 'agent_id'")
        if not message or not isinstance(message, str):
            raise ChannelParseError("Missing or invalid 'message'")

        session_id = payload.get("session_id") or str(uuid.uuid4())
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ChannelParseError("'metadata' must be an object")

        history = self._parse_history(payload.get("history"))

        return IncomingMessage(
            agent_id=agent_id,
            session_id=str(session_id),
            text=message,
            metadata=metadata,
            history=history,
        )

    @staticmethod
    def _parse_history(raw_history: Any) -> list[HistoryItemIn] | None:
        """Client-managed history opt-in: absent key -> ``None`` (server-managed,
        unchanged behavior). Present -> validated list of user/assistant turns.
        """
        if raw_history is None:
            return None
        if not isinstance(raw_history, list):
            raise ChannelParseError("'history' must be an array")

        settings = get_settings()
        if len(raw_history) > settings.MAX_CLIENT_HISTORY_MESSAGES:
            raise ChannelParseError(
                f"'history' exceeds the maximum of {settings.MAX_CLIENT_HISTORY_MESSAGES} messages"
            )

        try:
            return [HistoryItemIn(**item) for item in raw_history]
        except (TypeError, ValidationError) as exc:
            raise ChannelParseError(f"Invalid 'history' item: {exc}") from exc
