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


# ============================================================================
# chat_stream tests
# ============================================================================


async def test_chat_stream_sends_stream_true():
    """Verify that streaming requests explicitly set stream=True in payload."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"index":0,"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        )

    provider = make_provider(handler)
    chunks = [
        c async for c in provider.chat_stream(
            [Message(role=Role.USER, content="hi")], model="gpt-4o-mini"
        )
    ]

    assert captured["body"]["stream"] is True


async def test_chat_stream_yields_incremental_deltas_then_final():
    """Verify that deltas arrive incrementally, then final chunk with full response."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"index":0,"delta":{"content":"Hel"},"finish_reason":null}]}\n\ndata: {"choices":[{"index":0,"delta":{"content":"lo!"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        )

    provider = make_provider(handler)
    chunks = [
        c async for c in provider.chat_stream(
            [Message(role=Role.USER, content="hi")], model="gpt-4o-mini"
        )
    ]

    # Should have 3 chunks: 2 deltas + 1 final
    assert len(chunks) == 3

    # First delta chunk
    assert chunks[0].delta == "Hel"
    assert chunks[0].done is False
    assert chunks[0].response is None

    # Second delta chunk
    assert chunks[1].delta == "lo!"
    assert chunks[1].done is False
    assert chunks[1].response is None

    # Final chunk
    assert chunks[2].delta == ""
    assert chunks[2].done is True
    assert chunks[2].response is not None
    assert chunks[2].response.content == "Hello!"
    assert chunks[2].response.finish_reason == "stop"
    assert chunks[2].response.tool_calls == []


async def test_chat_stream_yields_reasoning_content_as_thinking_deltas():
    """Verify vLLM/DeepSeek-style reasoning_content deltas surface as thinking, not content."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=(
                b'data: {"choices":[{"index":0,"delta":{"reasoning_content":"Let me "},"finish_reason":null}]}\n\n'
                b'data: {"choices":[{"index":0,"delta":{"reasoning_content":"think..."},"finish_reason":null}]}\n\n'
                b'data: {"choices":[{"index":0,"delta":{"content":"Answer"},"finish_reason":"stop"}]}\n\n'
                b'data: [DONE]\n\n'
            ),
        )

    provider = make_provider(handler)
    chunks = [
        c async for c in provider.chat_stream(
            [Message(role=Role.USER, content="hi")], model="gpt-4o-mini"
        )
    ]

    assert chunks[0].thinking == "Let me "
    assert chunks[0].delta == ""
    assert chunks[1].thinking == "think..."
    assert chunks[2].delta == "Answer"
    assert chunks[2].thinking == ""
    assert chunks[3].done is True
    assert chunks[3].response.content == "Answer"


async def test_chat_stream_accumulates_single_tool_call_across_deltas():
    """Verify that a single tool call's arguments are accumulated across deltas."""

    def handler(request: httpx.Request) -> httpx.Response:
        # Simulates OpenAI's real streaming pattern:
        # - Chunk 1: id and name only, arguments ""
        # - Chunk 2: additional argument characters (no id/name), arguments {"q":
        # - Chunk 3: more argument characters (no id/name), arguments "x"}
        # Concatenated arguments: "" + {"q": + "x"} = {"q":"x"}
        return httpx.Response(
            200,
            content=b'data: {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_abc", "function": {"name": "search", "arguments": ""}}]}, "finish_reason": null}]}\n\ndata: {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\\"q\\":"}}]}, "finish_reason": null}]}\n\ndata: {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "\\"x\\"}"}}]}, "finish_reason": "tool_calls"}]}\n\ndata: [DONE]\n',
        )

    provider = make_provider(handler)
    chunks = [
        c async for c in provider.chat_stream(
            [Message(role=Role.USER, content="search for x")], model="gpt-4o-mini"
        )
    ]

    # Should have 4 chunks: 3 deltas + 1 final
    assert len(chunks) == 4

    # First 3 should be delta chunks with no response
    for i in range(3):
        assert chunks[i].done is False
        assert chunks[i].response is None

    # Final chunk should have the assembled tool call
    final = chunks[3]
    assert final.done is True
    assert final.response is not None
    assert final.response.finish_reason == "tool_calls"
    assert len(final.response.tool_calls) == 1

    tool_call = final.response.tool_calls[0]
    assert tool_call.id == "call_abc"
    assert tool_call.name == "search"
    assert tool_call.arguments == {"q": "x"}


async def test_chat_stream_accumulates_multiple_interleaved_tool_calls():
    """Verify that multiple tool calls at different indices are accumulated correctly even if interleaved."""

    def handler(request: httpx.Request) -> httpx.Response:
        # Two tool calls with interleaved deltas:
        # - index 1's id/name arrives in chunk 1
        # - index 0's id/name arrives in chunk 2
        # - arguments for both interleaved in chunks 3-4
        # Tool 0 arguments: {"a": + "x"} = {"a":"x"}
        # Tool 1 arguments: {"b": + "y"} = {"b":"y"}
        # Use json.dumps to properly escape the test data
        chunk1 = {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 1, "id": "call_y", "function": {"name": "tool2", "arguments": ""}}]}, "finish_reason": None}]}
        chunk2 = {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_x", "function": {"name": "tool1", "arguments": ""}}]}, "finish_reason": None}]}
        chunk3 = {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 1, "function": {"arguments": '{"b":'}}, {"index": 0, "function": {"arguments": '{"a":'}}]}, "finish_reason": None}]}
        chunk4 = {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 1, "function": {"arguments": '"y"}'}}, {"index": 0, "function": {"arguments": '"x"}'}}]}, "finish_reason": "tool_calls"}]}

        lines = [
            f'data: {json.dumps(chunk1)}',
            '',
            f'data: {json.dumps(chunk2)}',
            '',
            f'data: {json.dumps(chunk3)}',
            '',
            f'data: {json.dumps(chunk4)}',
            '',
            'data: [DONE]',
            ''
        ]
        sse_bytes = '\n'.join(lines).encode()
        return httpx.Response(200, content=sse_bytes)

    provider = make_provider(handler)
    chunks = [
        c async for c in provider.chat_stream(
            [Message(role=Role.USER, content="call two tools")], model="gpt-4o-mini"
        )
    ]

    # Final chunk should have both tool calls in order by index
    final = chunks[-1]
    assert final.done is True
    assert final.response is not None
    assert len(final.response.tool_calls) == 2

    # Should be ordered by index: [index 0, index 1]
    assert final.response.tool_calls[0].id == "call_x"
    assert final.response.tool_calls[0].name == "tool1"
    assert final.response.tool_calls[0].arguments == {"a": "x"}

    assert final.response.tool_calls[1].id == "call_y"
    assert final.response.tool_calls[1].name == "tool2"
    assert final.response.tool_calls[1].arguments == {"b": "y"}


async def test_chat_stream_requests_usage_via_stream_options():
    """Verify streaming requests set stream_options.include_usage so the
    server sends a trailing usage-only chunk."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"index":0,"delta":{"content":"result"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        )

    provider = make_provider(handler)
    _ = [
        c async for c in provider.chat_stream(
            [Message(role=Role.USER, content="hi")], model="gpt-4o-mini"
        )
    ]

    assert captured["body"]["stream_options"] == {"include_usage": True}


async def test_chat_stream_usage_defaults_to_empty_dict_when_server_omits_it():
    """If the server never sends a usage chunk, usage stays empty rather than crashing."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"index":0,"delta":{"content":"result"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        )

    provider = make_provider(handler)
    chunks = [
        c async for c in provider.chat_stream(
            [Message(role=Role.USER, content="hi")], model="gpt-4o-mini"
        )
    ]

    final = chunks[-1]
    assert final.response is not None
    assert final.response.usage == {}


async def test_chat_stream_parses_trailing_usage_only_chunk():
    """OpenAI sends a final chunk with empty choices and a top-level usage
    object when stream_options.include_usage is set — must not be dropped
    by the empty-choices skip."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=(
                b'data: {"choices":[{"index":0,"delta":{"content":"Hello!"},"finish_reason":"stop"}]}\n\n'
                b'data: {"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":6,"total_tokens":18}}\n\n'
                b'data: [DONE]\n\n'
            ),
        )

    provider = make_provider(handler)
    chunks = [
        c async for c in provider.chat_stream(
            [Message(role=Role.USER, content="hi")], model="gpt-4o-mini"
        )
    ]

    final = chunks[-1]
    assert final.done is True
    assert final.response is not None
    assert final.response.content == "Hello!"
    assert final.response.usage == {"prompt_tokens": 12, "completion_tokens": 6}


async def test_chat_omits_auth_header_when_api_key_blank():
    """Agents may point at a gateway that authenticates by network, not Bearer."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}]},
        )

    transport = httpx.MockTransport(handler)
    provider = OpenAICompatProvider(base_url="http://gateway.local/v1", api_key="")
    provider._client = httpx.AsyncClient(transport=transport, base_url="http://gateway.local/v1")

    await provider.chat([Message(role=Role.USER, content="Hi")], model="m")
    assert "authorization" not in captured["headers"]
