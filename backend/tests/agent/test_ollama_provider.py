from __future__ import annotations

import json

import httpx
import pytest

from app.agent.core.types import Message, ModelParams, Role, StreamChunk, ToolCall, ToolResult
from app.agent.providers.ollama import OllamaEmbeddingProvider, OllamaProvider


def make_provider(handler) -> OllamaProvider:
    transport = httpx.MockTransport(handler)
    provider = OllamaProvider(base_url="http://ollama.local")
    provider._client = httpx.AsyncClient(transport=transport, base_url="http://ollama.local")
    return provider


async def test_chat_request_payload_mapping_and_response_parsing():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "Hello!"},
                "done_reason": "stop",
                "prompt_eval_count": 10,
                "eval_count": 5,
            },
        )

    provider = make_provider(handler)

    messages = [
        Message(role=Role.SYSTEM, content="Be nice."),
        Message(role=Role.USER, content="Hi"),
    ]
    tools = [{"name": "search", "description": "Searches.", "input_schema": {"type": "object"}}]
    params = ModelParams(temperature=0.5, top_p=0.9, top_k=40, max_tokens=100, stop=["END"], seed=42)

    response = await provider.chat(messages, model="llama3", tools=tools, params=params)

    assert captured["url"].endswith("/api/chat")
    body = captured["body"]
    assert body["model"] == "llama3"
    assert body["stream"] is False
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
    assert body["options"]["temperature"] == 0.5
    assert body["options"]["top_p"] == 0.9
    assert body["options"]["top_k"] == 40
    assert body["options"]["num_predict"] == 100
    assert body["options"]["stop"] == ["END"]
    assert body["options"]["seed"] == 42

    assert response.content == "Hello!"
    assert response.finish_reason == "stop"
    assert response.tool_calls == []
    assert response.usage == {"prompt_tokens": 10, "completion_tokens": 5}


async def test_chat_request_without_tools_omits_tools_key():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}})

    provider = make_provider(handler)
    await provider.chat([Message(role=Role.USER, content="hi")], model="llama3")
    assert "tools" not in captured["body"]


async def test_chat_maps_assistant_tool_calls_and_tool_messages():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "done"}})

    provider = make_provider(handler)

    messages = [
        Message(role=Role.USER, content="search for x"),
        Message(
            role=Role.ASSISTANT,
            content="",
            tool_calls=[ToolCall(id="call_0", name="search", arguments={"query": "x"})],
        ),
        Message(
            role=Role.TOOL,
            tool_result=ToolResult(tool_call_id="call_0", name="search", content="result content"),
        ),
    ]
    await provider.chat(messages, model="llama3")

    body_messages = captured["body"]["messages"]
    assert body_messages[1]["role"] == "assistant"
    assert body_messages[1]["tool_calls"] == [
        {"function": {"name": "search", "arguments": {"query": "x"}}}
    ]
    assert body_messages[2]["role"] == "tool"
    assert body_messages[2]["content"] == "result content"
    assert body_messages[2]["tool_name"] == "search"


async def test_chat_response_with_tool_calls_gets_generated_ids():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "search", "arguments": {"query": "x"}}},
                        {"function": {"name": "other", "arguments": {"a": 1}}},
                    ],
                },
                "done_reason": "tool_calls",
            },
        )

    provider = make_provider(handler)
    response = await provider.chat([Message(role=Role.USER, content="hi")], model="llama3")

    assert len(response.tool_calls) == 2
    assert response.tool_calls[0].id == "call_0"
    assert response.tool_calls[0].name == "search"
    assert response.tool_calls[0].arguments == {"query": "x"}
    assert response.tool_calls[1].id == "call_1"
    assert response.finish_reason == "tool_calls"


async def test_chat_response_tool_call_arguments_as_json_string():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "search", "arguments": '{"query": "x"}'}},
                    ],
                }
            },
        )

    provider = make_provider(handler)
    response = await provider.chat([Message(role=Role.USER, content="hi")], model="llama3")
    assert response.tool_calls[0].arguments == {"query": "x"}


async def test_chat_stream_sends_stream_true():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        # Return valid streaming NDJSON response
        return httpx.Response(
            200,
            content=b'{"message":{"content":"hello"},"done":true,"done_reason":"stop"}\n',
        )

    provider = make_provider(handler)
    messages = [Message(role=Role.USER, content="hi")]
    chunks = [c async for c in provider.chat_stream(messages, model="llama3")]

    assert captured["body"]["stream"] is True


async def test_chat_stream_yields_incremental_deltas_then_final():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'{"message":{"content":"Hel"},"done":false}\n{"message":{"content":"lo!"},"done":false}\n{"message":{"content":""},"done":true,"done_reason":"stop","prompt_eval_count":5,"eval_count":3}\n',
        )

    provider = make_provider(handler)
    chunks = [c async for c in provider.chat_stream([Message(role=Role.USER, content="hi")], model="llama3")]

    assert len(chunks) == 3
    assert chunks[0] == StreamChunk(delta="Hel")
    assert chunks[1] == StreamChunk(delta="lo!")
    assert chunks[2].done is True
    assert chunks[2].response.content == "Hello!"
    assert chunks[2].response.finish_reason == "stop"
    assert chunks[2].response.usage == {"prompt_tokens": 5, "completion_tokens": 3}


async def test_chat_stream_yields_thinking_deltas_separately_from_content():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=(
                b'{"message":{"thinking":"Let me "},"done":false}\n'
                b'{"message":{"thinking":"think..."},"done":false}\n'
                b'{"message":{"content":"Answer"},"done":false}\n'
                b'{"message":{"content":""},"done":true,"done_reason":"stop"}\n'
            ),
        )

    provider = make_provider(handler)
    chunks = [c async for c in provider.chat_stream([Message(role=Role.USER, content="hi")], model="llama3")]

    assert chunks[0] == StreamChunk(thinking="Let me ")
    assert chunks[1] == StreamChunk(thinking="think...")
    assert chunks[2] == StreamChunk(delta="Answer")
    assert chunks[3].done is True
    assert chunks[3].response.content == "Answer"


async def test_chat_stream_captures_tool_calls_on_final_line():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'{"message":{"content":""},"done":false}\n{"message":{"content":"","tool_calls":[{"function":{"name":"search","arguments":{"q":"x"}}}]},"done":true,"done_reason":"tool_calls"}\n',
        )

    provider = make_provider(handler)
    chunks = [c async for c in provider.chat_stream([Message(role=Role.USER, content="hi")], model="llama3")]

    assert chunks[-1].done is True
    assert len(chunks[-1].response.tool_calls) == 1
    assert chunks[-1].response.tool_calls[0].id == "call_0"
    assert chunks[-1].response.tool_calls[0].name == "search"
    assert chunks[-1].response.tool_calls[0].arguments == {"q": "x"}


async def test_chat_stream_parses_string_json_tool_arguments():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'{"message":{"content":"","tool_calls":[{"function":{"name":"search","arguments":"{\\"q\\":\\"x\\"}"}}]},"done":true,"done_reason":"tool_calls"}\n',
        )

    provider = make_provider(handler)
    chunks = [c async for c in provider.chat_stream([Message(role=Role.USER, content="hi")], model="llama3")]

    assert len(chunks[-1].response.tool_calls) == 1
    assert chunks[-1].response.tool_calls[0].arguments == {"q": "x"}


async def test_chat_stream_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    provider = make_provider(handler)

    with pytest.raises(httpx.HTTPStatusError):
        async for _ in provider.chat_stream([Message(role=Role.USER, content="hi")], model="llama3"):
            pass


async def test_embedding_provider_parses_embeddings():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    transport = httpx.MockTransport(handler)
    provider = OllamaEmbeddingProvider(base_url="http://ollama.local")
    provider._client = httpx.AsyncClient(transport=transport, base_url="http://ollama.local")

    result = await provider.embed(["a", "b"], model="nomic-embed-text")

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["body"] == {"model": "nomic-embed-text", "input": ["a", "b"]}
