"""The dynamic agent loop.

The model decides which tools to call and when to stop; there is no
hard-coded sequence of steps here. This module has no knowledge of any
specific LLM vendor or tool implementation — those arrive via
constructor injection (see :class:`app.agent.core.builder.AgentBuilder`).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, AsyncIterator

from app.agent.core.types import (
    AgentResponse,
    AgentStreamEvent,
    Citation,
    LLMResponse,
    Message,
    ModelParams,
    Role,
    StreamChunk,
    ToolCall,
    ToolResult,
)
from app.agent.providers.base import LLMProvider
from app.agent.tools.base import Tool, ToolOutput

_MAX_ITERATIONS_FALLBACK = (
    "I wasn't able to reach a final answer within the allotted number of steps."
)

_MARKER_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def _cited_from(text: str, pool: dict[int, Citation]) -> list[Citation]:
    """Extract, in order of first appearance, the citations referenced by ``text``.

    Handles ``[1]``, ``[1, 2]``, and ``[1][2]`` marker forms. Markers not
    present in ``pool`` are silently dropped (never invented, never a
    crash).
    """
    ordered: list[Citation] = []
    seen: set[int] = set()
    for match in _MARKER_RE.finditer(text):
        for raw in match.group(1).split(","):
            marker = int(raw.strip())
            if marker in seen:
                continue
            citation = pool.get(marker)
            if citation is None:
                continue
            seen.add(marker)
            ordered.append(citation)
    return ordered


class Agent:
    def __init__(
        self,
        llm: LLMProvider,
        model: str,
        system_prompt: str,
        tools: list[Tool],
        params: ModelParams | None = None,
        max_iterations: int = 10,
    ):
        self.llm = llm
        self.model = model
        self.system_prompt = system_prompt
        self.tools = list(tools)
        self.params = params or ModelParams()
        self.max_iterations = max_iterations
        self._tools_by_name: dict[str, Tool] = {t.name: t for t in self.tools}

    async def run(
        self, user_message: str, history: list[Message] | None = None
    ) -> AgentResponse:
        messages: list[Message] = [Message(role=Role.SYSTEM, content=self.system_prompt)]
        messages.extend(history or [])
        messages.append(Message(role=Role.USER, content=user_message))

        tool_definitions = (
            [t.to_definition() for t in self.tools] if self.tools else None
        )

        last_text = ""
        iterations = 0
        usage_totals: dict[str, int] = {}
        citation_pool: dict[int, Citation] = {}
        for iterations in range(1, self.max_iterations + 1):
            response: LLMResponse = await self.llm.chat(
                messages,
                model=self.model,
                tools=tool_definitions,
                params=self.params,
            )
            self._accumulate_usage(usage_totals, response.usage)

            if response.content:
                last_text = response.content

            if not response.has_tool_calls:
                messages.append(Message(role=Role.ASSISTANT, content=response.content))
                return AgentResponse(
                    content=response.content,
                    messages=messages,
                    iterations=iterations,
                    stopped_on="final_answer",
                    usage=usage_totals,
                    citations=_cited_from(response.content, citation_pool),
                )

            messages.append(
                Message(
                    role=Role.ASSISTANT,
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            results = await asyncio.gather(
                *(self._execute_tool_call(call) for call in response.tool_calls)
            )
            for result in results:
                messages.append(Message(role=Role.TOOL, tool_result=result))
                self._accumulate_citations(citation_pool, result.citations)

        final_text = last_text or _MAX_ITERATIONS_FALLBACK
        return AgentResponse(
            content=final_text,
            messages=messages,
            iterations=iterations,
            stopped_on="max_iterations",
            usage=usage_totals,
            citations=_cited_from(final_text, citation_pool),
        )

    async def run_stream(
        self, user_message: str, history: list[Message] | None = None
    ) -> AsyncIterator[AgentStreamEvent]:
        messages: list[Message] = [Message(role=Role.SYSTEM, content=self.system_prompt)]
        messages.extend(history or [])
        messages.append(Message(role=Role.USER, content=user_message))

        tool_definitions = (
            [t.to_definition() for t in self.tools] if self.tools else None
        )

        last_text = ""
        iterations = 0
        usage_totals: dict[str, int] = {}
        citation_pool: dict[int, Citation] = {}
        for iterations in range(1, self.max_iterations + 1):
            response: LLMResponse | None = None
            async for chunk in self.llm.chat_stream(
                messages, model=self.model, tools=tool_definitions, params=self.params,
            ):
                if not chunk.done:
                    if chunk.thinking:
                        yield AgentStreamEvent(type="thinking", thinking=chunk.thinking)
                    if chunk.delta:
                        yield AgentStreamEvent(type="delta", delta=chunk.delta)
                    continue
                response = chunk.response
            assert response is not None, "LLMProvider.chat_stream contract violated: no done=True chunk with a response"
            self._accumulate_usage(usage_totals, response.usage)

            if response.content:
                last_text = response.content

            if not response.has_tool_calls:
                messages.append(Message(role=Role.ASSISTANT, content=response.content))
                yield AgentStreamEvent(
                    type="final",
                    response=AgentResponse(
                        content=response.content,
                        messages=messages,
                        iterations=iterations,
                        stopped_on="final_answer",
                        usage=usage_totals,
                        citations=_cited_from(response.content, citation_pool),
                    ),
                )
                return

            messages.append(
                Message(
                    role=Role.ASSISTANT,
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            results = await asyncio.gather(
                *(self._execute_tool_call(call) for call in response.tool_calls)
            )
            for result in results:
                messages.append(Message(role=Role.TOOL, tool_result=result))
                self._accumulate_citations(citation_pool, result.citations)

        final_text = last_text or _MAX_ITERATIONS_FALLBACK
        yield AgentStreamEvent(
            type="final",
            response=AgentResponse(
                content=final_text,
                messages=messages,
                iterations=iterations,
                stopped_on="max_iterations",
                usage=usage_totals,
                citations=_cited_from(final_text, citation_pool),
            ),
        )

    @staticmethod
    def _accumulate_usage(totals: dict[str, int], usage: dict[str, int]) -> None:
        for key, value in usage.items():
            totals[key] = totals.get(key, 0) + value

    @staticmethod
    def _accumulate_citations(pool: dict[int, Citation], citations: list[Citation]) -> None:
        for citation in citations:
            pool.setdefault(citation.marker, citation)

    async def _execute_tool_call(self, call: ToolCall) -> ToolResult:
        tool = self._tools_by_name.get(call.name)
        if tool is None:
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                content=f"Error: unknown tool {call.name!r}",
                is_error=True,
            )
        try:
            out = await tool.execute(**call.arguments)
        except Exception as exc:  # noqa: BLE001 - tool failures must never crash the loop
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                content=f"Error: {exc}",
                is_error=True,
            )
        if isinstance(out, ToolOutput):
            return ToolResult(
                tool_call_id=call.id, name=call.name, content=out.content, citations=out.citations
            )
        return ToolResult(tool_call_id=call.id, name=call.name, content=out)
