"""Shared fixtures: mock providers so no test ever calls Ollama."""

from __future__ import annotations

from typing import Any

import pytest

from app.agent.core.types import LLMResponse, Message, ModelParams


class MockLLMProvider:
    """Scriptable LLM: returns queued responses in order, records calls."""

    def __init__(self, responses: list[LLMResponse] | None = None):
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

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
