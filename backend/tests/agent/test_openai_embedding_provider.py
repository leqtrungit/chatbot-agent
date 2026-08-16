from __future__ import annotations

import json

import httpx
import pytest

from app.agent.providers.openai_compat import OpenAICompatEmbeddingProvider


def make_provider(handler) -> OpenAICompatEmbeddingProvider:
    transport = httpx.MockTransport(handler)
    provider = OpenAICompatEmbeddingProvider(base_url="http://openai.local/v1", api_key="sk-test")
    provider._client = httpx.AsyncClient(transport=transport, base_url="http://openai.local/v1")
    return provider


async def test_embed_request_payload_and_auth_header():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.1, 0.2]}, {"index": 1, "embedding": [0.3, 0.4]}]},
        )

    provider = make_provider(handler)
    vectors = await provider.embed(["a", "b"], model="text-embedding-3-small")

    assert captured["url"] == "http://openai.local/v1/embeddings"
    assert captured["headers"]["authorization"] == "Bearer sk-test"
    assert captured["body"] == {"model": "text-embedding-3-small", "input": ["a", "b"]}
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


async def test_embed_reorders_by_index():
    """The API does not guarantee ordering; `index` is authoritative."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"index": 1, "embedding": [9.0]}, {"index": 0, "embedding": [1.0]}]},
        )

    provider = make_provider(handler)
    vectors = await provider.embed(["first", "second"], model="text-embedding-3-small")
    assert vectors == [[1.0], [9.0]]


async def test_embed_empty_input_skips_request():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("no HTTP call expected for an empty batch")

    provider = make_provider(handler)
    assert await provider.embed([], model="text-embedding-3-small") == []


async def test_embed_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    provider = make_provider(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await provider.embed(["a"], model="text-embedding-3-small")


async def test_embed_omits_auth_header_when_api_key_blank():
    """OpenAI-compatible gateways often sit behind network auth instead."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

    transport = httpx.MockTransport(handler)
    provider = OpenAICompatEmbeddingProvider(base_url="http://gateway.local/v1", api_key="")
    provider._client = httpx.AsyncClient(transport=transport, base_url="http://gateway.local/v1")

    await provider.embed(["a"], model="bge-m3")
    assert "authorization" not in captured["headers"]


async def test_embed_falls_back_to_positional_order_when_index_absent():
    """Some OpenAI-compatible gateways omit `index` and rely on input order."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"embedding": [1.0]}, {"embedding": [2.0]}]})

    provider = make_provider(handler)
    assert await provider.embed(["a", "b"], model="bge-m3") == [[1.0], [2.0]]


async def test_embed_raises_when_vector_count_does_not_match_inputs():
    """A short response would otherwise be silently truncated by zip() in ingest."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

    provider = make_provider(handler)
    with pytest.raises(ValueError, match="1 vectors for 3 inputs"):
        await provider.embed(["a", "b", "c"], model="text-embedding-3-small")
