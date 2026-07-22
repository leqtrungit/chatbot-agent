"""Provider interfaces.

Swapping LLM vendors means adding one adapter implementing these
protocols; agent logic never changes.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable

from app.agent.core.types import LLMResponse, Message, ModelParams, StreamChunk


@runtime_checkable
class LLMProvider(Protocol):
    async def chat(
        self,
        messages: list[Message],
        *,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        params: ModelParams | None = None,
    ) -> LLMResponse:
        """Send a normalized conversation, return a normalized response.

        ``tools`` is a list of JSON-schema tool definitions:
        {"name": ..., "description": ..., "input_schema": {...}}
        """
        ...

    async def chat_stream(
        self,
        messages: list[Message],
        *,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        params: ModelParams | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Like ``chat`` but yields incremental ``StreamChunk``s.

        Yields zero or more ``StreamChunk(delta=..., done=False)`` chunks,
        then exactly one ``StreamChunk(delta="", done=True, response=<full LLMResponse>)``
        and stops. ``response`` is never ``None`` on the ``done=True`` chunk.
        """
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        """Embed a batch of texts, preserving order."""
        ...
