from __future__ import annotations

from app.agent.core.agent import Agent
from app.agent.core.types import LLMResponse, ModelParams, StreamChunk, ToolCall


def make_agent(mock_llm, tools=None, max_iterations=10):
    return Agent(
        llm=mock_llm,
        model="test-model",
        system_prompt="You are a test agent.",
        tools=tools or [],
        params=ModelParams(),
        max_iterations=max_iterations,
    )


async def test_run_single_iteration_usage_passthrough(mock_llm):
    mock_llm.queue(
        LLMResponse(content="Hi", finish_reason="stop", usage={"prompt_tokens": 10, "completion_tokens": 4})
    )
    agent = make_agent(mock_llm)

    result = await agent.run("Hello")

    assert result.usage == {"prompt_tokens": 10, "completion_tokens": 4}


async def test_run_multi_iteration_usage_sums_across_tool_calls(mock_llm, recording_tool):
    mock_llm.queue(
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="call_1", name="recorder", arguments={"x": "y"})],
            finish_reason="tool_calls",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )
    )
    mock_llm.queue(
        LLMResponse(content="Final answer", finish_reason="stop", usage={"prompt_tokens": 20, "completion_tokens": 8})
    )
    agent = make_agent(mock_llm, tools=[recording_tool])

    result = await agent.run("Do the thing")

    assert result.usage == {"prompt_tokens": 30, "completion_tokens": 13}


async def test_run_max_iterations_exhausted_still_aggregates_usage(mock_llm, recording_tool):
    for _ in range(3):
        mock_llm.queue(
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name="recorder", arguments={"x": "y"})],
                finish_reason="tool_calls",
                usage={"prompt_tokens": 5, "completion_tokens": 2},
            )
        )
    agent = make_agent(mock_llm, tools=[recording_tool], max_iterations=3)

    result = await agent.run("Do the thing")

    assert result.stopped_on == "max_iterations"
    assert result.usage == {"prompt_tokens": 15, "completion_tokens": 6}


async def test_run_partial_usage_keys_do_not_crash(mock_llm, recording_tool):
    mock_llm.queue(
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="call_1", name="recorder", arguments={"x": "y"})],
            finish_reason="tool_calls",
            usage={},
        )
    )
    mock_llm.queue(
        LLMResponse(content="Final answer", finish_reason="stop", usage={"prompt_tokens": 7, "completion_tokens": 3})
    )
    agent = make_agent(mock_llm, tools=[recording_tool])

    result = await agent.run("Do the thing")

    assert result.usage == {"prompt_tokens": 7, "completion_tokens": 3}


async def test_run_stream_single_iteration_usage_passthrough(mock_llm):
    mock_llm.queue_stream(
        [StreamChunk(delta="Hi", done=False),
         StreamChunk(done=True, response=LLMResponse(content="Hi", finish_reason="stop", usage={"prompt_tokens": 10, "completion_tokens": 4}))]
    )
    agent = make_agent(mock_llm)

    final = None
    async for event in agent.run_stream("Hello"):
        if event.type == "final":
            final = event.response

    assert final is not None
    assert final.usage == {"prompt_tokens": 10, "completion_tokens": 4}


async def test_run_stream_multi_iteration_usage_sums_across_tool_calls(mock_llm, recording_tool):
    mock_llm.queue_stream(
        [StreamChunk(
            done=True,
            response=LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name="recorder", arguments={"x": "y"})],
                finish_reason="tool_calls",
                usage={"prompt_tokens": 10, "completion_tokens": 5},
            ),
        )]
    )
    mock_llm.queue_stream(
        [StreamChunk(
            done=True,
            response=LLMResponse(content="Final answer", finish_reason="stop", usage={"prompt_tokens": 20, "completion_tokens": 8}),
        )]
    )
    agent = make_agent(mock_llm, tools=[recording_tool])

    final = None
    async for event in agent.run_stream("Do the thing"):
        if event.type == "final":
            final = event.response

    assert final is not None
    assert final.usage == {"prompt_tokens": 30, "completion_tokens": 13}


async def test_run_stream_max_iterations_exhausted_still_aggregates_usage(mock_llm, recording_tool):
    for _ in range(3):
        mock_llm.queue_stream(
            [StreamChunk(
                done=True,
                response=LLMResponse(
                    content="",
                    tool_calls=[ToolCall(id="call_1", name="recorder", arguments={"x": "y"})],
                    finish_reason="tool_calls",
                    usage={"prompt_tokens": 5, "completion_tokens": 2},
                ),
            )]
        )
    agent = make_agent(mock_llm, tools=[recording_tool], max_iterations=3)

    final = None
    async for event in agent.run_stream("Do the thing"):
        if event.type == "final":
            final = event.response

    assert final is not None
    assert final.stopped_on == "max_iterations"
    assert final.usage == {"prompt_tokens": 15, "completion_tokens": 6}
