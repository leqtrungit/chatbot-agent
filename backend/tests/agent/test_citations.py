"""Citation accumulation and marker extraction in the agent loop."""

from __future__ import annotations

from typing import Any

from app.agent.core.agent import Agent
from app.agent.core.types import Citation, LLMResponse, ModelParams, StreamChunk, ToolCall
from app.agent.tools.base import Tool, ToolOutput


class CitingTool(Tool):
    """Returns a scripted ToolOutput (or plain str) for each call, in order."""

    def __init__(self, outputs: list[str | ToolOutput]):
        self._outputs = list(outputs)

    @property
    def name(self) -> str:
        return "cite_search"

    @property
    def description(self) -> str:
        return "Searches and returns citations."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"query": {"type": "string"}}}

    async def execute(self, **kwargs: Any) -> str | ToolOutput:
        return self._outputs.pop(0)


CIT_1 = Citation(marker=1, source_id="doc1:0", title="a.pdf", snippet="Fact one.", score=0.9)
CIT_2 = Citation(marker=2, source_id="doc2:0", title="b.pdf", snippet="Fact two.", score=0.8)

TOOL_CALL = ToolCall(id="call-1", name="cite_search", arguments={"query": "x"})


def make_agent(mock_llm, tool: Tool, max_iterations: int = 10):
    return Agent(
        llm=mock_llm,
        model="test-model",
        system_prompt="You are a test agent.",
        tools=[tool],
        params=ModelParams(),
        max_iterations=max_iterations,
    )


async def test_final_answer_cites_only_referenced_marker(mock_llm):
    tool = CitingTool([ToolOutput(content="[1] a.pdf\nFact one.\n\n[2] b.pdf\nFact two.", citations=[CIT_1, CIT_2])])
    mock_llm.queue(LLMResponse(content="", tool_calls=[TOOL_CALL], finish_reason="tool_calls"))
    mock_llm.queue(LLMResponse(content="The answer is [1].", finish_reason="stop"))

    agent = make_agent(mock_llm, tool)
    result = await agent.run("hi")

    assert result.citations == [CIT_1]


async def test_citations_ordered_by_first_appearance_in_text(mock_llm):
    tool = CitingTool([ToolOutput(content="results", citations=[CIT_1, CIT_2])])
    mock_llm.queue(LLMResponse(content="", tool_calls=[TOOL_CALL], finish_reason="tool_calls"))
    mock_llm.queue(LLMResponse(content="See [2] and also [1].", finish_reason="stop"))

    agent = make_agent(mock_llm, tool)
    result = await agent.run("hi")

    assert result.citations == [CIT_2, CIT_1]


async def test_comma_form_parses_both_markers(mock_llm):
    tool = CitingTool([ToolOutput(content="results", citations=[CIT_1, CIT_2])])
    mock_llm.queue(LLMResponse(content="", tool_calls=[TOOL_CALL], finish_reason="tool_calls"))
    mock_llm.queue(LLMResponse(content="See [1, 2] for details.", finish_reason="stop"))

    agent = make_agent(mock_llm, tool)
    result = await agent.run("hi")

    assert result.citations == [CIT_1, CIT_2]


async def test_repeated_marker_deduped(mock_llm):
    tool = CitingTool([ToolOutput(content="results", citations=[CIT_1])])
    mock_llm.queue(LLMResponse(content="", tool_calls=[TOOL_CALL], finish_reason="tool_calls"))
    mock_llm.queue(LLMResponse(content="See [1][1].", finish_reason="stop"))

    agent = make_agent(mock_llm, tool)
    result = await agent.run("hi")

    assert result.citations == [CIT_1]


async def test_hallucinated_marker_dropped_without_crash(mock_llm):
    tool = CitingTool([ToolOutput(content="results", citations=[CIT_1])])
    mock_llm.queue(LLMResponse(content="", tool_calls=[TOOL_CALL], finish_reason="tool_calls"))
    mock_llm.queue(LLMResponse(content="See [9] for details.", finish_reason="stop"))

    agent = make_agent(mock_llm, tool)
    result = await agent.run("hi")

    assert result.citations == []


async def test_str_returning_tool_yields_no_citations(mock_llm):
    tool = CitingTool(["plain text result"])
    mock_llm.queue(LLMResponse(content="", tool_calls=[TOOL_CALL], finish_reason="tool_calls"))
    mock_llm.queue(LLMResponse(content="The answer is [1].", finish_reason="stop"))

    agent = make_agent(mock_llm, tool)
    result = await agent.run("hi")

    assert result.citations == []


async def test_max_iterations_exhaustion_still_populates_citations(mock_llm):
    tool = CitingTool([ToolOutput(content="results", citations=[CIT_1])])
    mock_llm.queue(LLMResponse(content="", tool_calls=[TOOL_CALL], finish_reason="tool_calls"))
    mock_llm.queue(LLMResponse(content="Partial answer [1].", tool_calls=[TOOL_CALL], finish_reason="tool_calls"))
    tool._outputs.append(ToolOutput(content="more results", citations=[CIT_1]))

    agent = make_agent(mock_llm, tool, max_iterations=2)
    result = await agent.run("hi")

    assert result.stopped_on == "max_iterations"
    assert result.content == "Partial answer [1]."
    assert result.citations == [CIT_1]


# --- run_stream ---


async def test_stream_final_cites_only_referenced_marker(mock_llm):
    tool = CitingTool([ToolOutput(content="results", citations=[CIT_1, CIT_2])])
    mock_llm.queue_stream(
        [StreamChunk(done=True, response=LLMResponse(content="", tool_calls=[TOOL_CALL], finish_reason="tool_calls"))]
    )
    mock_llm.queue_stream(
        [StreamChunk(done=True, response=LLMResponse(content="The answer is [1].", finish_reason="stop"))]
    )

    agent = make_agent(mock_llm, tool)
    final = None
    async for event in agent.run_stream("hi"):
        if event.type == "final":
            final = event.response

    assert final is not None
    assert final.citations == [CIT_1]


async def test_stream_str_returning_tool_yields_no_citations(mock_llm):
    tool = CitingTool(["plain text result"])
    mock_llm.queue_stream(
        [StreamChunk(done=True, response=LLMResponse(content="", tool_calls=[TOOL_CALL], finish_reason="tool_calls"))]
    )
    mock_llm.queue_stream(
        [StreamChunk(done=True, response=LLMResponse(content="The answer is [1].", finish_reason="stop"))]
    )

    agent = make_agent(mock_llm, tool)
    final = None
    async for event in agent.run_stream("hi"):
        if event.type == "final":
            final = event.response

    assert final is not None
    assert final.citations == []
