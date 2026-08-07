"""REST endpoints for agents."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import require_admin
from app.modules.agent import service
from app.modules.agent.schemas import AgentCreate, AgentRead, AgentUpdate, SetDomainIds

router = APIRouter(prefix="/api/agents", tags=["agents"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[AgentRead])
async def list_agents(session: AsyncSession = Depends(get_session)) -> list[AgentRead]:
    agents = await service.list_agents(session)
    return [AgentRead.from_agent(a) for a in agents]


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(data: AgentCreate, session: AsyncSession = Depends(get_session)) -> AgentRead:
    try:
        agent = await service.create_agent(session, data)
    except service.AgentConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except service.AgentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AgentRead.from_agent(agent)


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(agent_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> AgentRead:
    try:
        agent = await service.get_agent(session, agent_id)
    except service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    return AgentRead.from_agent(agent)


@router.put("/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: uuid.UUID, data: AgentUpdate, session: AsyncSession = Depends(get_session)
) -> AgentRead:
    try:
        agent = await service.update_agent(session, agent_id, data)
    except service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except service.AgentConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except service.AgentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AgentRead.from_agent(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> None:
    try:
        await service.delete_agent(session, agent_id)
    except service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc


@router.put("/{agent_id}/domains", response_model=AgentRead)
async def set_agent_domains(
    agent_id: uuid.UUID, data: SetDomainIds, session: AsyncSession = Depends(get_session)
) -> AgentRead:
    try:
        agent = await service.set_agent_domains(session, agent_id, data.domain_ids)
    except service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except service.AgentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AgentRead.from_agent(agent)
