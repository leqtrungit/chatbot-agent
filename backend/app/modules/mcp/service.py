"""Business logic for registered MCP servers."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mcp.models import McpServer
from app.modules.mcp.schemas import VALID_TRANSPORTS, McpServerCreate, McpServerUpdate


class McpServerNotFoundError(Exception):
    pass


class McpServerConflictError(Exception):
    pass


class McpServerValidationError(Exception):
    pass


def _validate_transport(transport: str) -> None:
    if transport not in VALID_TRANSPORTS:
        raise McpServerValidationError(
            f"Unknown transport {transport!r}; must be one of {', '.join(VALID_TRANSPORTS)}"
        )


async def _check_conflict(session: AsyncSession, name: str, exclude_id: uuid.UUID | None = None) -> None:
    stmt = select(McpServer).where(McpServer.name == name)
    result = await session.execute(stmt)
    existing = result.scalars().first()
    if existing is not None and existing.id != exclude_id:
        raise McpServerConflictError(f"MCP server with name '{name}' already exists")


async def list_mcp_servers(session: AsyncSession) -> list[McpServer]:
    result = await session.execute(select(McpServer).order_by(McpServer.created_at))
    return list(result.scalars().all())


async def get_mcp_server(session: AsyncSession, mcp_server_id: uuid.UUID) -> McpServer:
    server = await session.get(McpServer, mcp_server_id)
    if server is None:
        raise McpServerNotFoundError(str(mcp_server_id))
    return server


async def create_mcp_server(session: AsyncSession, data: McpServerCreate) -> McpServer:
    _validate_transport(data.transport)
    await _check_conflict(session, data.name)
    server = McpServer(
        name=data.name,
        url=data.url,
        transport=data.transport,
        headers=data.headers,
        is_active=data.is_active,
    )
    session.add(server)
    await session.commit()
    await session.refresh(server)
    return server


async def update_mcp_server(session: AsyncSession, mcp_server_id: uuid.UUID, data: McpServerUpdate) -> McpServer:
    server = await get_mcp_server(session, mcp_server_id)

    if data.name is not None and data.name != server.name:
        await _check_conflict(session, data.name, exclude_id=server.id)
        server.name = data.name
    if data.url is not None:
        server.url = data.url
    if data.transport is not None:
        _validate_transport(data.transport)
        server.transport = data.transport
    if data.headers is not None:
        server.headers = data.headers
    if data.is_active is not None:
        server.is_active = data.is_active

    await session.commit()
    await session.refresh(server)
    return server


async def delete_mcp_server(session: AsyncSession, mcp_server_id: uuid.UUID) -> None:
    server = await get_mcp_server(session, mcp_server_id)
    await session.delete(server)
    await session.commit()
