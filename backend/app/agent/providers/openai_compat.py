"""OpenAI-compatible adapter for :class:`LLMProvider`.

Translates the provider-agnostic message/tool/params shapes used by
``app.agent`` into the OpenAI Chat Completions request format, and
normalizes responses back into :class:`LLMResponse`. Works against any
OpenAI-compatible endpoint (OpenAI itself, or self-hosted gateways that
mirror the same schema) by pointing ``base_url`` at it.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from app.agent.core.types import LLMResponse, Message, ModelParams, Role, StreamChunk, ToolCall


def _message_to_openai(message: Message) -> dict[str, Any]:
    if message.role == Role.TOOL:
        result = message.tool_result
        return {
            "role": "tool",
            "tool_call_id": result.tool_call_id if result else "",
            "content": result.content if result else "",
        }

    payload: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                },
            }
            for call in message.tool_calls
        ]
    return payload


def _tool_to_openai(tool_definition: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool_definition["name"],
            "description": tool_definition.get("description", ""),
            "parameters": tool_definition.get("input_schema", {}),
        },
    }


def _params_to_body(params: ModelParams | None) -> dict[str, Any]:
    if params is None:
        return {}
    body: dict[str, Any] = {}
    if params.temperature is not None:
        body["temperature"] = params.temperature
    if params.top_p is not None:
        body["top_p"] = params.top_p
    # top_k has no OpenAI Chat Completions equivalent; intentionally skipped.
    if params.max_tokens is not None:
        body["max_tokens"] = params.max_tokens
    if params.stop:
        body["stop"] = params.stop
    if params.seed is not None:
        body["seed"] = params.seed
    body.update(params.extra)
    return body


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return dict(raw or {})


class OpenAICompatProvider:
    def __init__(self, base_url: str, api_key: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
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
            "messages": [_message_to_openai(m) for m in messages],
        }
        if tools:
            payload["tools"] = [_tool_to_openai(t) for t in tools]
        payload.update(_params_to_body(params))

        response = await self._client.post(
            "/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        message = choice.get("message", {})
        raw_tool_calls = message.get("tool_calls") or []
        tool_calls = [
            ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=_parse_arguments(tc["function"].get("arguments")),
            )
            for tc in raw_tool_calls
        ]

        usage_data = data.get("usage") or {}
        usage: dict[str, int] = {}
        if "prompt_tokens" in usage_data:
            usage["prompt_tokens"] = usage_data["prompt_tokens"]
        if "completion_tokens" in usage_data:
            usage["completion_tokens"] = usage_data["completion_tokens"]

        return LLMResponse(
            content=message.get("content") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason"),
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
        payload: dict[str, Any] = {
            "model": model,
            "messages": [_message_to_openai(m) for m in messages],
            "stream": True,  # Explicitly enable streaming
        }
        if tools:
            payload["tools"] = [_tool_to_openai(t) for t in tools]
        payload.update(_params_to_body(params))

        # Accumulate streamed content and tool calls across deltas
        content = ""
        finish_reason: str | None = None
        tool_accum: dict[int, dict] = {}  # keyed by tool call index

        async with self._client.stream(
            "POST",
            "/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                # Skip blank lines
                if not line:
                    continue

                # Only process lines starting with "data:"
                if not line.startswith("data:"):
                    continue

                # Strip the "data:" prefix and leading/trailing whitespace
                data_str = line[5:].strip()

                # Check for terminal marker
                if data_str == "[DONE]":
                    break

                # Parse the JSON chunk
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                # Extract the first choice
                if "choices" not in chunk or not chunk["choices"]:
                    continue

                choice = chunk["choices"][0]
                delta = choice.get("delta", {})

                # Track whether we yielded anything for this SSE line
                has_content = False

                # Accumulate text content
                if delta.get("content"):
                    content += delta["content"]
                    has_content = True
                    # Yield incremental delta chunk
                    yield StreamChunk(delta=delta["content"], done=False)

                # Accumulate tool calls by index
                if delta.get("tool_calls"):
                    has_content = True
                    for tc_delta in delta["tool_calls"]:
                        idx = tc_delta["index"]
                        entry = tool_accum.setdefault(
                            idx, {"id": "", "name": "", "arguments": ""}
                        )

                        # Set id if present (typically only on first delta for this tool call)
                        if "id" in tc_delta:
                            entry["id"] = tc_delta["id"]

                        # Set name if present (typically only on first delta for this tool call)
                        fn = tc_delta.get("function", {})
                        if fn.get("name"):
                            entry["name"] = fn["name"]

                        # Accumulate arguments (concatenate on each delta)
                        if fn.get("arguments"):
                            entry["arguments"] += fn["arguments"]

                    # Yield a delta chunk for tool calls (with empty delta text)
                    yield StreamChunk(delta="", done=False)

                # Track finish_reason (keep overwriting so the last non-null one wins)
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]

        # Build final tool_calls list, sorted by index for deterministic order
        tool_calls = [
            ToolCall(
                id=entry["id"],
                name=entry["name"],
                arguments=_parse_arguments(entry["arguments"]),
            )
            for _, entry in sorted(tool_accum.items())
        ]

        # Yield final chunk with complete response
        # Note: usage is deliberately left empty (scope cut; not requesting
        # stream_options.include_usage from OpenAI)
        yield StreamChunk(
            done=True,
            response=LLMResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage={},
            ),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
