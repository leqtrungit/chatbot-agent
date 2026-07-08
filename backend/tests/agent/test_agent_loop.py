from __future__ import annotations

import asyncio

import pytest

from app.agent.core.agent import Agent
from app.agent.core.types import LLMResponse, Message, ModelParams, Role, ToolCall
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


async def test_single_shot_text_answer(mock_llm):
    mock_llm.queue(LLMResponse(content="Hello there!", finish_reason="stop"))
    agent = make_agent(mock_llm)

    result = await agent.run("Hi")

    assert result.content == "Hello there!"
    assert result.iterations == 1
    assert result.stopped_on == "final_answer"
    # system + user + assistant
    assert result.messages[0].role == Role.SYSTEM
    assert result.messages[1].role == Role.USER
    assert result.messages[1].content == "Hi"
    assert result.messages[2].role == Role.ASSISTANT
    assert result.messages[2].content == "Hello there!"


async def test_tool_call_then_final_answer(mock_llm, recording_tool):
    mock_llm.queue(
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="call_1", name="recorder", arguments={"x": "y"})],
            finish_reason="tool_calls",
        )
    )
    mock_llm.queue(LLMResponse(content="Final answer", finish_reason="stop"))

    agent = make_agent(mock_llm, tools=[recording_tool])
    result = await agent.run("Do the thing")

    assert result.content == "Final answer"
    assert result.iterations == 2
    assert result.stopped_on == "final_answer"
    assert recording_tool.calls == [{"x": "y"}]

    roles = [m.role for m in result.messages]
    assert roles == [
        Role.SYSTEM,
        Role.USER,
        Role.ASSISTANT,
        Role.TOOL,
        Role.ASSISTANT,
    ]
    tool_msg = result.messages[3]
    assert tool_msg.tool_result is not None
    assert tool_msg.tool_result.content == "ok"
    assert tool_msg.tool_result.tool_call_id == "call_1"
    assert tool_msg.tool_result.is_error is False

    # verify tool definitions were passed to llm.chat on first call
    first_call = mock_llm.calls[0]
    assert first_call["tools"] == [recording_tool.to_definition()]


async def test_no_tools_passes_none(mock_llm):
    mock_llm.queue(LLMResponse(content="ok", finish_reason="stop"))
    agent = make_agent(mock_llm, tools=[])
    await agent.run("hi")
    assert mock_llm.calls[0]["tools"] is None


async def test_multiple_tool_calls_executed_concurrently(mock_llm):
    order: list[str] = []

    class DelayTool(RecordingTool):
        def __init__(self, name, delay):
            super().__init__(name=name)
            self.delay = delay

        async def execute(self, **kwargs):
            order.append(f"start-{self.name}")
            await asyncio.sleep(self.delay)
            order.append(f"end-{self.name}")
            return f"result-{self.name}"

    tool_a = DelayTool("tool_a", 0.05)
    tool_b = DelayTool("tool_b", 0.01)

    mock_llm.queue(
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(id="call_a", name="tool_a", arguments={}),
                ToolCall(id="call_b", name="tool_b", arguments={}),
            ],
            finish_reason="tool_calls",
        )
    )
    mock_llm.queue(LLMResponse(content="done", finish_reason="stop"))

    agent = make_agent(mock_llm, tools=[tool_a, tool_b])
    result = await agent.run("go")

    assert result.content == "done"
    # both should start before either ends (concurrent), since b is faster
    assert order.index("start-tool_b") < order.index("end-tool_a")

    tool_results = [m.tool_result for m in result.messages if m.role == Role.TOOL]
    assert len(tool_results) == 2
    contents = {tr.tool_call_id: tr.content for tr in tool_results}
    assert contents == {"call_a": "result-tool_a", "call_b": "result-tool_b"}


async def test_tool_raises_exception_becomes_error_result(mock_llm):
    failing_tool = RecordingTool(name="failer", error=ValueError("boom"))
    mock_llm.queue(
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="call_1", name="failer", arguments={})],
            finish_reason="tool_calls",
        )
    )
    mock_llm.queue(LLMResponse(content="recovered", finish_reason="stop"))

    agent = make_agent(mock_llm, tools=[failing_tool])
    result = await agent.run("go")

    assert result.content == "recovered"
    tool_msg = next(m for m in result.messages if m.role == Role.TOOL)
    assert tool_msg.tool_result.is_error is True
    assert "boom" in tool_msg.tool_result.content


async def test_unknown_tool_name_becomes_error_result(mock_llm, recording_tool):
    mock_llm.queue(
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="call_1", name="does_not_exist", arguments={})],
            finish_reason="tool_calls",
        )
    )
    mock_llm.queue(LLMResponse(content="ok anyway", finish_reason="stop"))

    agent = make_agent(mock_llm, tools=[recording_tool])
    result = await agent.run("go")

    assert result.content == "ok anyway"
    tool_msg = next(m for m in result.messages if m.role == Role.TOOL)
    assert tool_msg.tool_result.is_error is True
    assert "does_not_exist" in tool_msg.tool_result.content
    assert recording_tool.calls == []


async def test_max_iterations_exhaustion(mock_llm, recording_tool):
    for _ in range(3):
        mock_llm.queue(
            LLMResponse(
                content="thinking...",
                tool_calls=[ToolCall(id="call_x", name="recorder", arguments={})],
                finish_reason="tool_calls",
            )
        )

    agent = make_agent(mock_llm, tools=[recording_tool], max_iterations=3)
    result = await agent.run("loop forever")

    assert result.stopped_on == "max_iterations"
    assert result.iterations == 3
    assert isinstance(result.content, str) and result.content


async def test_history_is_prepended(mock_llm):
    mock_llm.queue(LLMResponse(content="ok", finish_reason="stop"))
    agent = make_agent(mock_llm)
    history = [
        Message(role=Role.USER, content="earlier question"),
        Message(role=Role.ASSISTANT, content="earlier answer"),
    ]
    result = await agent.run("new question", history=history)

    assert result.messages[1].content == "earlier question"
    assert result.messages[2].content == "earlier answer"
    assert result.messages[3].content == "new question"
