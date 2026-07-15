"""OpenAI-compatible adapter for :class:`LLMProvider`.

Translates the provider-agnostic message/tool/params shapes used by
``app.agent`` into the OpenAI Chat Completions request format, and
normalizes responses back into :class:`LLMResponse`. Works against any
OpenAI-compatible endpoint (OpenAI itself, or self-hosted gateways that
mirror the same schema) by pointing ``base_url`` at it.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.agent.core.types import LLMResponse, Message, ModelParams, Role, ToolCall


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

    async def aclose(self) -> None:
        await self._client.aclose()
