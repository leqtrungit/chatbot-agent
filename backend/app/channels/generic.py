"""Generic adapter: the reference/default platform, and what tests target.

Payload shape: {"domain_id": ..., "session_id": ... (optional), "message":
..., "metadata": {...} (optional)}
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
        domain_id = payload.get("domain_id")
        message = payload.get("message")

        if not domain_id or not isinstance(domain_id, str):
            raise ChannelParseError("Missing or invalid 'domain_id'")
        if not message or not isinstance(message, str):
            raise ChannelParseError("Missing or invalid 'message'")

        session_id = payload.get("session_id") or str(uuid.uuid4())
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ChannelParseError("'metadata' must be an object")

        return IncomingMessage(
            domain_id=domain_id,
            session_id=str(session_id),
            text=message,
            metadata=metadata,
        )
