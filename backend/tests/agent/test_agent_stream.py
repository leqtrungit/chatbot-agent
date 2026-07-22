from __future__ import annotations

import asyncio

import pytest

from app.agent.core.agent import Agent
from app.agent.core.types import (
    AgentStreamEvent,
    LLMResponse,
    Message,
    ModelParams,
    Role,
    StreamChunk,
    ToolCall,
)
from tests.agent.conftest import RecordingTool


def make_agent(mock_llm, tools=None, max_iterations=10):
    return Agent(
        llm=mock_llm,
        model="test-model",
        system_prompt="You are a test agent.",
        tools=tools or [],
        params=ModelParams(),
        max_iterations=max_iterations,
    )


async def test_single_shot_streamed_answer(mock_llm):
    mock_llm.queue_stream([
        StreamChunk(delta="Hel"),
        StreamChunk(delta="lo!"),
        StreamChunk(done=True, response=LLMResponse(content="Hello!", finish_reason="stop")),
    ])
    agent = make_agent(mock_llm)

    events = [e async for e in agent.run_stream("hi")]

    assert len(events) == 3
    assert events[0] == AgentStreamEvent(type="delta", delta="Hel")
    assert events[1] == AgentStreamEvent(type="delta", delta="lo!")
    assert events[2].type == "final"
    assert events[2].response is not None
    assert events[2].response.content == "Hello!"
    assert events[2].response.iterations == 1
    assert events[2].response.stopped_on == "final_answer"


async def test_stream_tool_call_then_final_answer(mock_llm, recording_tool):
    # First iteration: tool call response (no deltas during tool calls)
    mock_llm.queue_stream([
        StreamChunk(
            done=True,
            response=LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name="recorder", arguments={"x": "y"})],
                finish_reason="tool_calls",
            ),
        ),
    ])
    # Second iteration: final answer with deltas
    mock_llm.queue_stream([
        StreamChunk(delta="Final "),
        StreamChunk(delta="answer"),
        StreamChunk(done=True, response=LLMResponse(content="Final answer", finish_reason="stop")),
    ])

    agent = make_agent(mock_llm, tools=[recording_tool])
    events = [e async for e in agent.run_stream("Do the thing")]

    # Filter to see what was actually emitted
    delta_events = [e for e in events if e.type == "delta"]
    final_events = [e for e in events if e.type == "final"]

    # No delta events should be emitted during tool-call iteration
    assert len(delta_events) == 2
    assert delta_events[0].delta == "Final "
    assert delta_events[1].delta == "answer"

    # Exactly one final event
    assert len(final_events) == 1
    final = final_events[0]
    assert final.response is not None
    assert final.response.content == "Final answer"
    assert final.response.iterations == 2
    assert final.response.stopped_on == "final_answer"

    # Tool executed
    assert recording_tool.calls == [{"x": "y"}]

    # Message roles match the non-streaming equivalent
    roles = [m.role for m in final.response.messages]
    assert roles == [
        Role.SYSTEM,
        Role.USER,
        Role.ASSISTANT,
        Role.TOOL,
        Role.ASSISTANT,
    ]


async def test_stream_max_iterations_exhaustion(mock_llm, recording_tool):
    # Queue max_iterations tool-call responses (no final answer)
    for _ in range(3):
        mock_llm.queue_stream([
            StreamChunk(
                done=True,
                response=LLMResponse(
                    content="thinking...",
                    tool_calls=[ToolCall(id="call_x", name="recorder", arguments={})],
                    finish_reason="tool_calls",
                ),
            ),
        ])

    agent = make_agent(mock_llm, tools=[recording_tool], max_iterations=3)
    events = [e async for e in agent.run_stream("loop forever")]

    # Only final event should appear
    final_events = [e for e in events if e.type == "final"]
    assert len(final_events) == 1

    final = final_events[0]
    assert final.response is not None
    assert final.response.stopped_on == "max_iterations"
    assert final.response.iterations == 3
    assert isinstance(final.response.content, str) and final.response.content


async def test_stream_history_is_prepended(mock_llm):
    mock_llm.queue_stream([
        StreamChunk(done=True, response=LLMResponse(content="ok", finish_reason="stop")),
    ])
    agent = make_agent(mock_llm)
    history = [
        Message(role=Role.USER, content="earlier question"),
        Message(role=Role.ASSISTANT, content="earlier answer"),
    ]
    events = [e async for e in agent.run_stream("new question", history=history)]

    # Verify history was passed through to chat_stream
    assert len(mock_llm.stream_calls) == 1
    call_messages = mock_llm.stream_calls[0]["messages"]
    assert call_messages[0].role == Role.SYSTEM
    assert call_messages[1].content == "earlier question"
    assert call_messages[2].content == "earlier answer"
    assert call_messages[3].content == "new question"


async def test_mock_llm_chat_stream_records_calls_independently_of_chat(mock_llm):
    # Call chat once
    mock_llm.queue(LLMResponse(content="sync response", finish_reason="stop"))
    await mock_llm.chat(
        [Message(role=Role.USER, content="sync message")],
        model="test-model",
    )

    # Call chat_stream once
    mock_llm.queue_stream([
        StreamChunk(done=True, response=LLMResponse(content="async response", finish_reason="stop")),
    ])
    async for _ in mock_llm.chat_stream(
        [Message(role=Role.USER, content="async message")],
        model="test-model",
    ):
        pass

    # Verify they are tracked separately
    assert len(mock_llm.calls) == 1
    assert len(mock_llm.stream_calls) == 1
    assert mock_llm.calls[0]["messages"][0].content == "sync message"
    assert mock_llm.stream_calls[0]["messages"][0].content == "async message"
