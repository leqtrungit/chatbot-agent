"""Core types for the agent framework.

This package is provider-agnostic and framework-agnostic: nothing in
``app.agent`` may import from FastAPI, SQLAlchemy, or ``app.modules``.
All external capabilities (LLM, vector search, ...) enter via the
interfaces in ``app.agent.providers`` and ``app.agent.tools``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_call_id: str
    name: str
    content: str
    is_error: bool = False


class Message(BaseModel):
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_result: ToolResult | None = None


class ModelParams(BaseModel):
    """Common sampling/technical parameters, provider-agnostic."""

    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_tokens: int | None = None
    stop: list[str] = Field(default_factory=list)
    seed: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """Normalized response from any LLM provider."""

    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class StreamChunk(BaseModel):
    delta: str = ""               # NEW text since the last chunk, never cumulative
    thinking: str = ""            # NEW reasoning/thinking text since the last chunk, never cumulative
    done: bool = False
    response: LLMResponse | None = None   # set iff done=True; full accumulated response


class AgentResponse(BaseModel):
    """Final result of one agent run."""

    content: str
    messages: list[Message] = Field(default_factory=list)
    iterations: int = 0
    stopped_on: str = "final_answer"  # final_answer | max_iterations | error
    usage: dict[str, int] = Field(default_factory=dict)  # summed across every LLM call in the run


class AgentStreamEvent(BaseModel):
    type: Literal["delta", "thinking", "final"]
    delta: str = ""                # set iff type=="delta"
    thinking: str = ""             # set iff type=="thinking"
    response: AgentResponse | None = None   # set iff type=="final"
