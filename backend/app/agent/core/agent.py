"""The dynamic agent loop.

The model decides which tools to call and when to stop; there is no
hard-coded sequence of steps here. This module has no knowledge of any
specific LLM vendor or tool implementation — those arrive via
constructor injection (see :class:`app.agent.core.builder.AgentBuilder`).
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from app.agent.core.types import (
    AgentResponse,
    AgentStreamEvent,
    LLMResponse,
    Message,
    ModelParams,
    Role,
    StreamChunk,
    ToolCall,
    ToolResult,
)
from app.agent.providers.base import LLMProvider
from app.agent.tools.base import Tool

_MAX_ITERATIONS_FALLBACK = (
    "I wasn't able to reach a final answer within the allotted number of steps."
)


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
        for iterations in range(1, self.max_iterations + 1):
            response: LLMResponse = await self.llm.chat(
                messages,
                model=self.model,
                tools=tool_definitions,
                params=self.params,
            )

            if response.content:
                last_text = response.content

            if not response.has_tool_calls:
                messages.append(Message(role=Role.ASSISTANT, content=response.content))
                return AgentResponse(
                    content=response.content,
                    messages=messages,
                    iterations=iterations,
                    stopped_on="final_answer",
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

        return AgentResponse(
            content=last_text or _MAX_ITERATIONS_FALLBACK,
            messages=messages,
            iterations=iterations,
            stopped_on="max_iterations",
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

        yield AgentStreamEvent(
            type="final",
            response=AgentResponse(
                content=last_text or _MAX_ITERATIONS_FALLBACK,
                messages=messages,
                iterations=iterations,
                stopped_on="max_iterations",
            ),
        )

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
            content = await tool.execute(**call.arguments)
        except Exception as exc:  # noqa: BLE001 - tool failures must never crash the loop
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                content=f"Error: {exc}",
                is_error=True,
            )
        return ToolResult(tool_call_id=call.id, name=call.name, content=content)
