"""REST endpoints for agents (org-scoped, v2)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.tenancy import OrgScopedRepo
from app.identity.org_access import OrgContext, require_org_access
from app.agents import service
from app.agents.models import Agent
from app.agents.schemas import (
    AgentCreate,
    AgentRead,
    AgentUpdate,
    SetKnowledgeBaseIds,
)


def get_agent_router() -> APIRouter:
    """Create the agents router with org-scoped endpoints."""
    router = APIRouter(
        prefix="/v2/orgs/{org_id}/agents",
        tags=["agents"],
    )

    @router.get("", response_model=list[AgentRead])
    async def list_agents(
        org_id: uuid.UUID,
        ctx: OrgContext = Depends(require_org_access),
        session: AsyncSession = Depends(get_session),
    ) -> list[AgentRead]:
        """List all agents in the organization."""
        repo = OrgScopedRepo(session, org_id)
        agents = await service.list_agents(repo)
        return [AgentRead.from_orm(a) for a in agents]

    @router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
    async def create_agent(
        org_id: uuid.UUID,
        data: AgentCreate,
        ctx: OrgContext = Depends(require_org_access),
        session: AsyncSession = Depends(get_session),
    ) -> AgentRead:
        """Create a new agent in the organization."""
        repo = OrgScopedRepo(session, org_id)
        try:
            agent = await service.create_agent(repo, session, org_id, data)
        except service.AgentConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except service.AgentValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        return AgentRead.from_orm(agent)

    @router.get("/{agent_id}", response_model=AgentRead)
    async def get_agent(
        org_id: uuid.UUID,
        agent_id: uuid.UUID,
        ctx: OrgContext = Depends(require_org_access),
        session: AsyncSession = Depends(get_session),
    ) -> AgentRead:
        """Get a specific agent by ID."""
        repo = OrgScopedRepo(session, org_id)
        try:
            agent = await service.get_agent(repo, agent_id)
        except service.AgentNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )
        return AgentRead.from_orm(agent)

    @router.put("/{agent_id}", response_model=AgentRead)
    async def update_agent(
        org_id: uuid.UUID,
        agent_id: uuid.UUID,
        data: AgentUpdate,
        ctx: OrgContext = Depends(require_org_access),
        session: AsyncSession = Depends(get_session),
    ) -> AgentRead:
        """Update an agent."""
        repo = OrgScopedRepo(session, org_id)
        try:
            agent = await service.update_agent(repo, session, agent_id, org_id, data)
        except service.AgentNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )
        except service.AgentConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except service.AgentValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        return AgentRead.from_orm(agent)

    @router.post("/{agent_id}/deactivate", response_model=AgentRead)
    async def deactivate_agent(
        org_id: uuid.UUID,
        agent_id: uuid.UUID,
        ctx: OrgContext = Depends(require_org_access),
        session: AsyncSession = Depends(get_session),
    ) -> AgentRead:
        """Soft-deactivate an agent (sets is_active=False)."""
        repo = OrgScopedRepo(session, org_id)
        try:
            agent = await service.deactivate_agent(repo, session, agent_id)
        except service.AgentNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )
        return AgentRead.from_orm(agent)

    @router.put("/{agent_id}/knowledge-bases", response_model=AgentRead)
    async def set_agent_knowledge_bases(
        org_id: uuid.UUID,
        agent_id: uuid.UUID,
        data: SetKnowledgeBaseIds,
        ctx: OrgContext = Depends(require_org_access),
        session: AsyncSession = Depends(get_session),
    ) -> AgentRead:
        """Set knowledge base links for an agent."""
        repo = OrgScopedRepo(session, org_id)
        try:
            agent = await service.set_agent_knowledge_bases(
                repo, session, agent_id, org_id, data.knowledge_base_ids
            )
        except service.AgentNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )
        except service.AgentValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        return AgentRead.from_orm(agent)

    return router
