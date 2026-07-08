"""Provider interfaces.

Swapping LLM vendors means adding one adapter implementing these
protocols; agent logic never changes.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.agent.core.types import LLMResponse, Message, ModelParams


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


@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        """Embed a batch of texts, preserving order."""
        ...
