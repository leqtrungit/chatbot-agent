"""REST endpoints for registered MCP servers."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import require_admin
from app.modules.mcp import service
from app.modules.mcp.schemas import McpServerCreate, McpServerRead, McpServerUpdate

router = APIRouter(prefix="/api/mcp-servers", tags=["mcp-servers"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[McpServerRead])
async def list_mcp_servers(session: AsyncSession = Depends(get_session)) -> list[McpServerRead]:
    servers = await service.list_mcp_servers(session)
    return [McpServerRead.model_validate(s) for s in servers]


@router.post("", response_model=McpServerRead, status_code=status.HTTP_201_CREATED)
async def create_mcp_server(
    data: McpServerCreate, session: AsyncSession = Depends(get_session)
) -> McpServerRead:
    try:
        server = await service.create_mcp_server(session, data)
    except service.McpServerConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except service.McpServerValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return McpServerRead.model_validate(server)


@router.get("/{mcp_server_id}", response_model=McpServerRead)
async def get_mcp_server(
    mcp_server_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> McpServerRead:
    try:
        server = await service.get_mcp_server(session, mcp_server_id)
    except service.McpServerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found") from exc
    return McpServerRead.model_validate(server)


@router.put("/{mcp_server_id}", response_model=McpServerRead)
async def update_mcp_server(
    mcp_server_id: uuid.UUID, data: McpServerUpdate, session: AsyncSession = Depends(get_session)
) -> McpServerRead:
    try:
        server = await service.update_mcp_server(session, mcp_server_id, data)
    except service.McpServerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found") from exc
    except service.McpServerConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except service.McpServerValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return McpServerRead.model_validate(server)


@router.delete("/{mcp_server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(mcp_server_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> None:
    try:
        await service.delete_mcp_server(session, mcp_server_id)
    except service.McpServerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found") from exc
