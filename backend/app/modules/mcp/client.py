"""DB-facing glue: turn an agent's linked :class:`McpServer` rows into live
:class:`Tool` instances, connecting to each remote server via the pure
connector in ``app.agent.tools.mcp``.

Lives outside ``app.agent`` (which must stay framework-free) since it reads
SQLAlchemy models.
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack

from app.agent.tools.base import Tool
from app.agent.tools.mcp import connect_mcp_server, list_mcp_tools
from app.modules.mcp.models import McpServer

logger = logging.getLogger(__name__)


async def build_mcp_tools(mcp_servers: list[McpServer], *, stack: AsyncExitStack) -> list[Tool]:
    """Connect to every active server and collect its tools.

    A server that fails to connect (unreachable, misconfigured, ...) is
    logged and skipped rather than failing the whole agent build — one bad
    admin-registered endpoint shouldn't take down every domain using this
    agent. ``stack`` owns the resulting connections' lifetime.
    """
    tools: list[Tool] = []
    for server in mcp_servers:
        if not server.is_active:
            continue
        try:
            session = await connect_mcp_server(server.url, server.transport, server.headers, stack=stack)
            tools.extend(await list_mcp_tools(session))
        except Exception:
            logger.warning("Failed to connect to MCP server %r (%s)", server.name, server.url, exc_info=True)
    return tools
