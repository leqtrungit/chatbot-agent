"""Generic adapter: the reference/default platform, and what tests target.

Payload shape: {"agent_id": ..., "session_id": ...
(optional), "message": ..., "metadata": {...} (optional)}
"""

from __future__ import annotations

import uuid
from typing import Any

from app.channels.base import ChannelAdapter, ChannelParseError, IncomingMessage


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

        return IncomingMessage(
            agent_id=agent_id,
            session_id=str(session_id),
            text=message,
            metadata=metadata,
        )
