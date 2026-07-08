from __future__ import annotations

import pytest

from app.agent.tools.base import FunctionTool, Tool


async def test_function_tool_wraps_async_function():
    async def add(a: int, b: int) -> str:
        return str(a + b)

    tool = FunctionTool(
        add,
        name="add",
        description="Adds two numbers.",
        input_schema={
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
    )

    assert tool.name == "add"
    assert isinstance(tool, Tool)
    result = await tool.execute(a=2, b=3)
    assert result == "5"


def test_to_definition_returns_expected_keys():
    async def noop() -> str:
        return "ok"

    tool = FunctionTool(noop, name="noop", description="Does nothing.", input_schema={"type": "object"})
    definition = tool.to_definition()
    assert set(definition.keys()) == {"name", "description", "input_schema"}
    assert definition["name"] == "noop"
