from __future__ import annotations

from typing import Any

import pytest
from mcp import types

from app.agent.tools.mcp import McpTool, connect_mcp_server, list_mcp_tools


class FakeSession:
    """Stand-in for ``mcp.ClientSession``: records calls, returns canned results."""

    def __init__(self, tools: list[types.Tool], call_result: types.CallToolResult | None = None):
        self._tools = tools
        self._call_result = call_result
        self.calls: list[dict[str, Any]] = []

    async def list_tools(self) -> types.ListToolsResult:
        return types.ListToolsResult(tools=self._tools)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> types.CallToolResult:
        self.calls.append({"name": name, "arguments": arguments})
        return self._call_result


def _tool_def(name: str = "search_docs") -> types.Tool:
    return types.Tool(
        name=name,
        description="Search external docs",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
    )


async def test_list_mcp_tools_wraps_each_remote_tool():
    session = FakeSession(tools=[_tool_def("search_docs"), _tool_def("fetch_page")])

    tools = await list_mcp_tools(session)

    assert [t.name for t in tools] == ["search_docs", "fetch_page"]
    assert all(isinstance(t, McpTool) for t in tools)
    assert tools[0].description == "Search external docs"
    assert tools[0].input_schema["properties"]["query"]["type"] == "string"


async def test_mcp_tool_execute_calls_session_and_joins_text_content():
    result = types.CallToolResult(
        content=[types.TextContent(type="text", text="first"), types.TextContent(type="text", text="second")],
        is_error=False,
    )
    session = FakeSession(tools=[_tool_def()], call_result=result)
    tool = McpTool(session, "search_docs", "Search external docs", {"type": "object"})

    output = await tool.execute(query="pricing")

    assert output == "first\nsecond"
    assert session.calls == [{"name": "search_docs", "arguments": {"query": "pricing"}}]


async def test_mcp_tool_execute_prefixes_error_results():
    result = types.CallToolResult(
        content=[types.TextContent(type="text", text="boom")],
        is_error=True,
    )
    session = FakeSession(tools=[], call_result=result)
    tool = McpTool(session, "flaky", "A flaky tool", {"type": "object"})

    output = await tool.execute()

    assert output == "Error: boom"


async def test_to_definition_shape():
    tool = McpTool(FakeSession([]), "search_docs", "desc", {"type": "object", "properties": {}})
    definition = tool.to_definition()
    assert definition == {"name": "search_docs", "description": "desc", "input_schema": {"type": "object", "properties": {}}}


async def test_connect_mcp_server_rejects_unknown_transport():
    from contextlib import AsyncExitStack

    with pytest.raises(ValueError, match="Unsupported MCP transport"):
        async with AsyncExitStack() as stack:
            await connect_mcp_server("http://example.invalid", "carrier-pigeon", None, stack=stack)  # type: ignore[arg-type]
