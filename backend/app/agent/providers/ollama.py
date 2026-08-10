"""Ollama adapter for :class:`LLMProvider` / :class:`EmbeddingProvider`.

Translates the provider-agnostic message/tool/params shapes used by
``app.agent`` into Ollama's ``/api/chat`` and ``/api/embed`` request
formats, and normalizes responses back into :class:`LLMResponse`.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from app.agent.core.types import LLMResponse, Message, ModelParams, Role, StreamChunk, ToolCall


def _message_to_ollama(message: Message) -> dict[str, Any]:
    if message.role == Role.TOOL:
        result = message.tool_result
        payload: dict[str, Any] = {
            "role": "tool",
            "content": result.content if result else "",
        }
        if result is not None:
            payload["tool_name"] = result.name
        return payload

    payload = {"role": message.role.value, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {"function": {"name": call.name, "arguments": call.arguments}}
            for call in message.tool_calls
        ]
    return payload


def _tool_to_ollama(tool_definition: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool_definition["name"],
            "description": tool_definition.get("description", ""),
            "parameters": tool_definition.get("input_schema", {}),
        },
    }


def _params_to_options(params: ModelParams | None) -> dict[str, Any]:
    if params is None:
        return {}
    options: dict[str, Any] = {}
    if params.temperature is not None:
        options["temperature"] = params.temperature
    if params.top_p is not None:
        options["top_p"] = params.top_p
    if params.top_k is not None:
        options["top_k"] = params.top_k
    if params.max_tokens is not None:
        options["num_predict"] = params.max_tokens
    if params.stop:
        options["stop"] = params.stop
    if params.seed is not None:
        options["seed"] = params.seed
    options.update(params.extra)
    return options


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return dict(raw or {})


class OllamaProvider:
    def __init__(self, base_url: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        params: ModelParams | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [_message_to_ollama(m) for m in messages],
            "stream": False,
        }
        if tools:
            payload["tools"] = [_tool_to_ollama(t) for t in tools]
        options = _params_to_options(params)
        if options:
            payload["options"] = options

        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

        message = data.get("message", {})
        raw_tool_calls = message.get("tool_calls") or []
        tool_calls = [
            ToolCall(
                id=f"call_{i}",
                name=tc["function"]["name"],
                arguments=_parse_arguments(tc["function"].get("arguments")),
            )
            for i, tc in enumerate(raw_tool_calls)
        ]

        usage: dict[str, int] = {}
        if "prompt_eval_count" in data:
            usage["prompt_tokens"] = data["prompt_eval_count"]
        if "eval_count" in data:
            usage["completion_tokens"] = data["eval_count"]

        return LLMResponse(
            content=message.get("content", ""),
            tool_calls=tool_calls,
            finish_reason=data.get("done_reason"),
            usage=usage,
        )

    async def chat_stream(
        self,
        messages: list[Message],
        *,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        params: ModelParams | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a chat response, yielding incremental deltas then a final LLMResponse."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": [_message_to_ollama(m) for m in messages],
            "stream": True,
        }
        if tools:
            payload["tools"] = [_tool_to_ollama(t) for t in tools]
        options = _params_to_options(params)
        if options:
            payload["options"] = options

        content = ""
        raw_tool_calls = []
        done_reason = None
        usage: dict[str, int] = {}

        async with self._client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue

                data = json.loads(line)
                message = data.get("message", {})

                # Accumulate thinking and yield deltas (reasoning models only)
                chunk_thinking = message.get("thinking") or ""
                if chunk_thinking:
                    yield StreamChunk(thinking=chunk_thinking)

                # Accumulate content and yield deltas
                chunk_content = message.get("content") or ""
                if chunk_content:
                    content += chunk_content
                    yield StreamChunk(delta=chunk_content)

                # Capture tool_calls (last non-empty one wins)
                if message.get("tool_calls"):
                    raw_tool_calls = message.get("tool_calls", [])

                # Handle done
                if data.get("done"):
                    done_reason = data.get("done_reason")
                    if "prompt_eval_count" in data:
                        usage["prompt_tokens"] = data["prompt_eval_count"]
                    if "eval_count" in data:
                        usage["completion_tokens"] = data["eval_count"]
                    break

        # Build tool_calls from captured raw data
        tool_calls = [
            ToolCall(
                id=f"call_{i}",
                name=tc["function"]["name"],
                arguments=_parse_arguments(tc["function"].get("arguments")),
            )
            for i, tc in enumerate(raw_tool_calls)
        ]

        # Yield final chunk with complete response
        yield StreamChunk(
            done=True,
            response=LLMResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason=done_reason,
                usage=usage,
            ),
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class OllamaEmbeddingProvider:
    def __init__(self, base_url: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        response = await self._client.post(
            "/api/embed", json={"model": model, "input": texts}
        )
        response.raise_for_status()
        data = response.json()
        return data["embeddings"]

    async def aclose(self) -> None:
        await self._client.aclose()
