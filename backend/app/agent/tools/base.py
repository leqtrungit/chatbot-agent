"""Tool abstraction: how the agent exposes callable capabilities to an LLM."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from app.agent.core.types import Citation


class ToolOutput(BaseModel):
    content: str                     # the text the LLM reads
    citations: list[Citation] = Field(default_factory=list)


class Tool(ABC):
    """A single callable capability the agent can invoke.

    Implementations must expose ``name``, ``description``, ``input_schema``
    (a JSON schema dict describing keyword arguments) and an async
    ``execute`` that returns a plain string, or a :class:`ToolOutput`
    (string plus citations) for the LLM to read.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]: ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str | ToolOutput: ...

    @property
    def prompt_fragment(self) -> str:
        """Instruction fragment appended to the system prompt, if any.

        A tool may contribute a fragment of prompt text (e.g. instructions
        for how to use its output) that gets appended to the agent's system
        prompt, mirroring :class:`app.agent.skills.base.Skill`. Empty by
        default.
        """
        return ""

    def to_definition(self) -> dict[str, Any]:
        """Return the tool definition shape expected by ``LLMProvider.chat``."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class FunctionTool(Tool):
    """Wraps a plain async function as a :class:`Tool`."""

    def __init__(
        self,
        fn: Callable[..., Awaitable[str]],
        *,
        name: str,
        description: str,
        input_schema: dict[str, Any],
    ):
        self._fn = fn
        self._name = name
        self._description = description
        self._input_schema = input_schema

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def input_schema(self) -> dict[str, Any]:
        return self._input_schema

    async def execute(self, **kwargs: Any) -> str:
        return await self._fn(**kwargs)
