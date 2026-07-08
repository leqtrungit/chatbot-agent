"""Fixtures specific to the app.agent test suite."""

from __future__ import annotations

from typing import Any

import pytest

from app.agent.tools.base import Tool


class RecordingTool(Tool):
    """A tool that records calls and returns a scripted result (or raises)."""

    def __init__(
        self,
        name: str = "recorder",
        description: str = "Records calls.",
        input_schema: dict[str, Any] | None = None,
        result: str = "ok",
        error: Exception | None = None,
    ):
        self._name = name
        self._description = description
        self._input_schema = input_schema or {
            "type": "object",
            "properties": {"x": {"type": "string"}},
        }
        self.result = result
        self.error = error
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def recording_tool() -> RecordingTool:
    return RecordingTool()
