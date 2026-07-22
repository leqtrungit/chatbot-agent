"""Pure business logic for SSE chat streaming.

Deliberately free of FastAPI/Redis imports — only uses typing for
protocols — so it can be unit-tested with hand-built fakes.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Protocol


def sse_frame(payload: dict[str, Any]) -> bytes:
    """Build an SSE frame (Server-Sent Events) from a payload dict.

    Returns a byte string in the format:
        data: <json>\n\n
    """
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n".encode()


class PubSubLike(Protocol):
    """Protocol for pubsub-like objects that can be used with relay_job_events."""

    def listen(self) -> AsyncIterator[dict[str, Any]]:
        """Async iterator yielding messages from the pubsub channel."""
        ...


async def relay_job_events(pubsub: PubSubLike) -> AsyncIterator[bytes]:
    """Relay worker messages from pubsub as SSE frames.

    Listens on the pubsub channel and yields each message as an SSE frame.
    Stops when a "done" or "error" message is received (terminal messages).
    Skips non-message events (subscribe/unsubscribe confirmations).

    Args:
        pubsub: A redis.asyncio.PubSub instance or compatible protocol.

    Yields:
        SSE frames as bytes.
    """
    async for message in pubsub.listen():
        # Skip non-message events (subscribe/unsubscribe confirmations)
        if message.get("type") != "message":
            continue

        # Extract and decode the data field
        data = message["data"]
        if isinstance(data, bytes):
            data = data.decode()

        # Parse the JSON payload
        payload = json.loads(data)

        # Yield the SSE frame
        yield sse_frame(payload)

        # Stop after terminal messages
        if payload.get("type") in ("done", "error"):
            return
