"""Shared fixtures: mock providers so no test ever calls Ollama."""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from app.agent.core.types import LLMResponse, Message, ModelParams, StreamChunk


class MockLLMProvider:
    """Scriptable LLM: returns queued responses in order, records calls."""

    def __init__(self, responses: list[LLMResponse] | None = None):
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []
        self.stream_responses: list[list[StreamChunk]] = []
        self.stream_calls: list[dict[str, Any]] = []

    def queue(self, response: LLMResponse) -> None:
        self.responses.append(response)

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        params: ModelParams | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {"messages": list(messages), "model": model, "tools": tools, "params": params}
        )
        if not self.responses:
            return LLMResponse(content="(mock) no response queued", finish_reason="stop")
        return self.responses.pop(0)

    def queue_stream(self, chunks: list[StreamChunk]) -> None:
        self.stream_responses.append(chunks)

    async def chat_stream(
        self,
        messages: list[Message],
        *,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        params: ModelParams | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.stream_calls.append(
            {"messages": list(messages), "model": model, "tools": tools, "params": params}
        )
        if not self.stream_responses:
            yield StreamChunk(done=True, response=LLMResponse(content="(mock) no response queued", finish_reason="stop"))
            return
        chunks = self.stream_responses.pop(0)
        for chunk in chunks:
            yield chunk


class MockEmbeddingProvider:
    """Deterministic fake embeddings, records embedded texts."""

    def __init__(self, dim: int = 768):
        self.dim = dim
        self.embedded: list[str] = []

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        self.embedded.extend(texts)
        return [[float((hash(t) % 1000) / 1000.0)] * self.dim for t in texts]


@pytest.fixture
def mock_llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
def mock_embedding() -> MockEmbeddingProvider:
    return MockEmbeddingProvider()
