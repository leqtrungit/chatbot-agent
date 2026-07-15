from __future__ import annotations

import json

import httpx
import pytest

from app.agent.core.types import Message, ModelParams, Role, ToolCall, ToolResult
from app.agent.providers.openai_compat import OpenAICompatProvider


def make_provider(handler) -> OpenAICompatProvider:
    transport = httpx.MockTransport(handler)
    provider = OpenAICompatProvider(base_url="http://openai.local/v1", api_key="sk-test")
    provider._client = httpx.AsyncClient(transport=transport, base_url="http://openai.local/v1")
    return provider


async def test_chat_request_payload_mapping_and_response_parsing():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Hello!"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    provider = make_provider(handler)

    messages = [
        Message(role=Role.SYSTEM, content="Be nice."),
        Message(role=Role.USER, content="Hi"),
    ]
    tools = [{"name": "search", "description": "Searches.", "input_schema": {"type": "object"}}]
    params = ModelParams(temperature=0.5, top_p=0.9, top_k=40, max_tokens=100, stop=["END"], seed=42)

    response = await provider.chat(messages, model="gpt-4o-mini", tools=tools, params=params)

    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["authorization"] == "Bearer sk-test"

    body = captured["body"]
    assert body["model"] == "gpt-4o-mini"
    assert body["messages"] == [
        {"role": "system", "content": "Be nice."},
        {"role": "user", "content": "Hi"},
    ]
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Searches.",
                "parameters": {"type": "object"},
            },
        }
    ]
    # top_k has no OpenAI equivalent and must be skipped
    assert "top_k" not in body
    assert body["temperature"] == 0.5
    assert body["top_p"] == 0.9
    assert body["max_tokens"] == 100
    assert body["stop"] == ["END"]
    assert body["seed"] == 42

    assert response.content == "Hello!"
    assert response.finish_reason == "stop"
    assert response.tool_calls == []
    assert response.usage == {"prompt_tokens": 10, "completion_tokens": 5}


async def test_chat_request_without_tools_omits_tools_key():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    provider = make_provider(handler)
    await provider.chat([Message(role=Role.USER, content="hi")], model="gpt-4o-mini")
    assert "tools" not in captured["body"]


async def test_chat_request_without_params_omits_param_keys():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    provider = make_provider(handler)
    await provider.chat([Message(role=Role.USER, content="hi")], model="gpt-4o-mini")
    body = captured["body"]
    for key in ("temperature", "top_p", "max_tokens", "stop", "seed", "top_k"):
        assert key not in body


async def test_chat_params_extra_is_merged():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    provider = make_provider(handler)
    params = ModelParams(extra={"presence_penalty": 0.2})
    await provider.chat([Message(role=Role.USER, content="hi")], model="gpt-4o-mini", params=params)
    assert captured["body"]["presence_penalty"] == 0.2


async def test_chat_maps_assistant_tool_calls_and_tool_messages():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "done"}}]},
        )

    provider = make_provider(handler)

    messages = [
        Message(role=Role.USER, content="search for x"),
        Message(
            role=Role.ASSISTANT,
            content="",
            tool_calls=[ToolCall(id="call_abc", name="search", arguments={"query": "x"})],
        ),
        Message(
            role=Role.TOOL,
            tool_result=ToolResult(tool_call_id="call_abc", name="search", content="result content"),
        ),
    ]
    await provider.chat(messages, model="gpt-4o-mini")

    body_messages = captured["body"]["messages"]
    assert body_messages[1]["role"] == "assistant"
    assert body_messages[1]["tool_calls"] == [
        {
            "id": "call_abc",
            "type": "function",
            "function": {"name": "search", "arguments": json.dumps({"query": "x"})},
        }
    ]
    assert body_messages[2] == {
        "role": "tool",
        "tool_call_id": "call_abc",
        "content": "result content",
    }


async def test_chat_response_with_tool_calls_echoes_real_ids():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_xyz",
                                    "type": "function",
                                    "function": {
                                        "name": "search",
                                        "arguments": json.dumps({"query": "x"}),
                                    },
                                },
                                {
                                    "id": "call_other",
                                    "type": "function",
                                    "function": {"name": "other", "arguments": json.dumps({"a": 1})},
                                },
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        )

    provider = make_provider(handler)
    response = await provider.chat([Message(role=Role.USER, content="hi")], model="gpt-4o-mini")

    assert response.content == ""
    assert len(response.tool_calls) == 2
    assert response.tool_calls[0].id == "call_xyz"
    assert response.tool_calls[0].name == "search"
    assert response.tool_calls[0].arguments == {"query": "x"}
    assert response.tool_calls[1].id == "call_other"
    assert response.finish_reason == "tool_calls"


async def test_chat_response_tolerates_invalid_arguments_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_bad",
                                    "type": "function",
                                    "function": {"name": "search", "arguments": "{not valid json"},
                                }
                            ],
                        }
                    }
                ]
            },
        )

    provider = make_provider(handler)
    response = await provider.chat([Message(role=Role.USER, content="hi")], model="gpt-4o-mini")
    assert response.tool_calls[0].arguments == {}


async def test_chat_response_null_content_becomes_empty_string():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": None}}]},
        )

    provider = make_provider(handler)
    response = await provider.chat([Message(role=Role.USER, content="hi")], model="gpt-4o-mini")
    assert response.content == ""


async def test_chat_response_missing_usage_defaults_to_empty_dict():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    provider = make_provider(handler)
    response = await provider.chat([Message(role=Role.USER, content="hi")], model="gpt-4o-mini")
    assert response.usage == {}


async def test_chat_http_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    provider = make_provider(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await provider.chat([Message(role=Role.USER, content="hi")], model="gpt-4o-mini")
