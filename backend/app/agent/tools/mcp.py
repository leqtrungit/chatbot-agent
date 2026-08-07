"""MCP (Model Context Protocol) client integration.

Connects to a remote HTTP/SSE MCP server and wraps its tools as
:class:`Tool` instances the agent loop can call like any other tool. Only
the ``mcp`` SDK is used here — no SQLAlchemy/FastAPI/app.core/app.modules
imports, consistent with the rest of ``app.agent``.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any, Literal

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from app.agent.tools.base import Tool

Transport = Literal["http", "sse"]


async def connect_mcp_server(
    url: str,
    transport: Transport,
    headers: dict[str, str] | None,
    *,
    stack: AsyncExitStack,
) -> ClientSession:
    """Open an initialized MCP client session against a remote server.

    ``stack`` owns the transport + session lifetime; the caller closes it
    (e.g. via ``async with AsyncExitStack() as stack``) once done.
    """
    if transport == "sse":
        read_stream, write_stream = await stack.enter_async_context(sse_client(url, headers=headers))
    elif transport == "http":
        http_client = create_mcp_http_client(headers=headers)
        read_stream, write_stream = await stack.enter_async_context(
            streamable_http_client(url, http_client=http_client)
        )
    else:
        raise ValueError(f"Unsupported MCP transport: {transport!r}")

    session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
    await session.initialize()
    return session


def _result_to_text(result: Any) -> str:
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
    text = "\n".join(parts) if parts else str(result)
    if getattr(result, "is_error", False):
        return f"Error: {text}"
    return text


class McpTool(Tool):
    """A single remote tool discovered from an MCP server's ``list_tools()``."""

    def __init__(self, session: ClientSession, name: str, description: str, input_schema: dict[str, Any]):
        self._session = session
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
        result = await self._session.call_tool(self._name, kwargs)
        return _result_to_text(result)


async def list_mcp_tools(session: ClientSession) -> list[McpTool]:
    """List every tool a connected MCP session exposes, wrapped as :class:`Tool`."""
    result = await session.list_tools()
    return [
        McpTool(session, tool.name, tool.description or "", tool.input_schema)
        for tool in result.tools
    ]
