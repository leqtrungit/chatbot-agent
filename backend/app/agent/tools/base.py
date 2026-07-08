"""Tool abstraction: how the agent exposes callable capabilities to an LLM."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable


class Tool(ABC):
    """A single callable capability the agent can invoke.

    Implementations must expose ``name``, ``description``, ``input_schema``
    (a JSON schema dict describing keyword arguments) and an async
    ``execute`` that returns a plain string result for the LLM to read.
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
    async def execute(self, **kwargs: Any) -> str: ...

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
