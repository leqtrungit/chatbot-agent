"""Business logic for agents (org-scoped)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.models import Agent, kb_agents
from app.agents.schemas import VALID_PROVIDERS, AgentCreate, AgentUpdate
from app.core.tenancy import OrgScopedRepo
from app.knowledge.models import KnowledgeBase


class AgentNotFoundError(Exception):
    """Raised when an agent is not found."""

    pass


class AgentConflictError(Exception):
    """Raised when there is a naming conflict."""

    pass


class AgentValidationError(Exception):
    """Raised when validation fails."""

    pass


def _validate_provider(provider: str) -> None:
    """Validate that the provider is in the allowed list."""
    if provider not in VALID_PROVIDERS:
        raise AgentValidationError(
            f"Unknown provider {provider!r}; must be one of {', '.join(VALID_PROVIDERS)}"
        )


async def list_agents(repo: OrgScopedRepo[Agent]) -> list[Agent]:
    """List all agents for the org."""
    agents = await repo.list(Agent)
    # Load relationships
    for agent in agents:
        if not hasattr(agent, "knowledge_bases"):
            # Lazy load relationships if needed
            pass
    return agents


async def get_agent(repo: OrgScopedRepo[Agent], agent_id: uuid.UUID) -> Agent:
    """Get a specific agent by ID, org-scoped."""
    agent = await repo.get(Agent, agent_id)
    if agent is None:
        raise AgentNotFoundError(str(agent_id))
    return agent


async def create_agent(
    repo: OrgScopedRepo[Agent],
    session: AsyncSession,
    org_id: uuid.UUID,
    data: AgentCreate,
) -> Agent:
    """Create a new agent in the org."""
    # Validate provider
    _validate_provider(data.provider)

    # Check for name conflict within org
    stmt = select(Agent).where(
        Agent.org_id == org_id,
        Agent.name == data.name,
    )
    result = await session.execute(stmt)
    if result.scalars().first() is not None:
        raise AgentConflictError(f"Agent with name '{data.name}' already exists in this organization")

    # Resolve knowledge bases (must be in same org)
    kbs = []
    if data.knowledge_base_ids:
        for kb_id in data.knowledge_base_ids:
            kb = await session.get(KnowledgeBase, kb_id)
            if kb is None or kb.org_id != org_id:
                raise AgentValidationError(f"Unknown or cross-org knowledge base id: {kb_id}")
            kbs.append(kb)

    # Create agent
    agent = Agent(
        org_id=org_id,
        name=data.name,
        provider=data.provider,
        base_url=data.base_url,
        api_key=data.api_key,
        model_name=data.model_name,
        system_prompt=data.system_prompt,
        max_iterations=data.max_iterations if data.max_iterations is not None else 10,
        temperature=data.temperature,
        top_p=data.top_p,
        enable_knowledge_search=data.enable_knowledge_search,
        is_active=data.is_active,
    )

    await repo.add(agent)
    await session.commit()

    # Link knowledge bases
    if kbs:
        for kb in kbs:
            stmt = kb_agents.insert().values(
                knowledge_base_id=kb.id,
                agent_id=agent.id,
            )
            await session.execute(stmt)
        await session.commit()

    # Refresh to get relationships
    await session.refresh(agent)
    return agent


async def update_agent(
    repo: OrgScopedRepo[Agent],
    session: AsyncSession,
    agent_id: uuid.UUID,
    org_id: uuid.UUID,
    data: AgentUpdate,
) -> Agent:
    """Update an agent."""
    agent = await repo.get(Agent, agent_id)
    if agent is None:
        raise AgentNotFoundError(str(agent_id))

    # Validate new provider if provided
    new_provider = data.provider if data.provider is not None else agent.provider
    _validate_provider(new_provider)

    # Check name conflict if changing name
    if data.name is not None and data.name != agent.name:
        stmt = select(Agent).where(
            Agent.org_id == org_id,
            Agent.name == data.name,
        )
        result = await session.execute(stmt)
        if result.scalars().first() is not None:
            raise AgentConflictError(
                f"Agent with name '{data.name}' already exists in this organization"
            )
        agent.name = data.name

    # Update scalar fields
    agent.provider = new_provider
    if data.system_prompt is not None:
        agent.system_prompt = data.system_prompt
    if data.base_url is not None:
        agent.base_url = data.base_url
    if data.api_key is not None:
        agent.api_key = data.api_key
    if data.model_name is not None:
        agent.model_name = data.model_name
    if data.max_iterations is not None:
        agent.max_iterations = data.max_iterations
    if data.temperature is not None:
        agent.temperature = data.temperature
    if data.top_p is not None:
        agent.top_p = data.top_p
    if data.enable_knowledge_search is not None:
        agent.enable_knowledge_search = data.enable_knowledge_search
    if data.is_active is not None:
        agent.is_active = data.is_active

    # Update knowledge bases if provided
    if data.knowledge_base_ids is not None:
        kbs = []
        for kb_id in data.knowledge_base_ids:
            kb = await session.get(KnowledgeBase, kb_id)
            if kb is None or kb.org_id != org_id:
                raise AgentValidationError(f"Unknown or cross-org knowledge base id: {kb_id}")
            kbs.append(kb)

        # Clear existing links
        stmt = kb_agents.delete().where(kb_agents.c.agent_id == agent.id)
        await session.execute(stmt)

        # Add new links
        for kb in kbs:
            stmt = kb_agents.insert().values(
                knowledge_base_id=kb.id,
                agent_id=agent.id,
            )
            await session.execute(stmt)

    await session.commit()
    await session.refresh(agent)
    return agent


async def deactivate_agent(
    repo: OrgScopedRepo[Agent], session: AsyncSession, agent_id: uuid.UUID
) -> Agent:
    """Soft-deactivate an agent (sets is_active=False)."""
    agent = await repo.get(Agent, agent_id)
    if agent is None:
        raise AgentNotFoundError(str(agent_id))

    agent.is_active = False
    await session.commit()
    await session.refresh(agent)
    return agent


async def set_agent_knowledge_bases(
    repo: OrgScopedRepo[Agent],
    session: AsyncSession,
    agent_id: uuid.UUID,
    org_id: uuid.UUID,
    kb_ids: list[uuid.UUID],
) -> Agent:
    """Set knowledge base links for an agent (replace all existing)."""
    agent = await repo.get(Agent, agent_id)
    if agent is None:
        raise AgentNotFoundError(str(agent_id))

    # Resolve and validate knowledge bases
    kbs = []
    for kb_id in kb_ids:
        kb = await session.get(KnowledgeBase, kb_id)
        if kb is None or kb.org_id != org_id:
            raise AgentValidationError(f"Unknown or cross-org knowledge base id: {kb_id}")
        kbs.append(kb)

    # Clear existing links
    stmt = kb_agents.delete().where(kb_agents.c.agent_id == agent.id)
    await session.execute(stmt)

    # Add new links
    for kb in kbs:
        stmt = kb_agents.insert().values(
            knowledge_base_id=kb.id,
            agent_id=agent.id,
        )
        await session.execute(stmt)

    await session.commit()
    await session.refresh(agent)
    return agent
