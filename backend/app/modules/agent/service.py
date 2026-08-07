"""Business logic for agents: CRUD plus managing the domain/MCP-server links."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.agent.models import Agent
from app.modules.agent.schemas import VALID_PROVIDERS, AgentCreate, AgentUpdate
from app.modules.domain.models import Domain
from app.modules.mcp.models import McpServer


class AgentNotFoundError(Exception):
    pass


class AgentConflictError(Exception):
    pass


class AgentValidationError(Exception):
    pass


_LOAD_OPTS = (selectinload(Agent.mcp_servers), selectinload(Agent.domains))


def _validate(provider: str) -> None:
    if provider not in VALID_PROVIDERS:
        raise AgentValidationError(
            f"Unknown provider {provider!r}; must be one of {', '.join(VALID_PROVIDERS)}"
        )


async def _check_conflict(session: AsyncSession, name: str, exclude_id: uuid.UUID | None = None) -> None:
    stmt = select(Agent).where(Agent.name == name)
    result = await session.execute(stmt)
    existing = result.scalars().first()
    if existing is not None and existing.id != exclude_id:
        raise AgentConflictError(f"Agent with name '{name}' already exists")


async def _resolve_domains(session: AsyncSession, domain_ids: list[uuid.UUID]) -> list[Domain]:
    if not domain_ids:
        return []
    result = await session.execute(select(Domain).where(Domain.id.in_(domain_ids)))
    found = list(result.scalars().all())
    missing = set(domain_ids) - {d.id for d in found}
    if missing:
        raise AgentValidationError(f"Unknown domain id(s): {', '.join(str(m) for m in missing)}")
    return found


async def _resolve_mcp_servers(session: AsyncSession, mcp_server_ids: list[uuid.UUID]) -> list[McpServer]:
    if not mcp_server_ids:
        return []
    result = await session.execute(select(McpServer).where(McpServer.id.in_(mcp_server_ids)))
    found = list(result.scalars().all())
    missing = set(mcp_server_ids) - {s.id for s in found}
    if missing:
        raise AgentValidationError(f"Unknown MCP server id(s): {', '.join(str(m) for m in missing)}")
    return found


async def list_agents(session: AsyncSession) -> list[Agent]:
    result = await session.execute(select(Agent).options(*_LOAD_OPTS).order_by(Agent.created_at))
    return list(result.scalars().all())


async def get_agent(session: AsyncSession, agent_id: uuid.UUID) -> Agent:
    result = await session.execute(select(Agent).options(*_LOAD_OPTS).where(Agent.id == agent_id))
    agent = result.scalars().first()
    if agent is None:
        raise AgentNotFoundError(str(agent_id))
    return agent


async def create_agent(session: AsyncSession, data: AgentCreate) -> Agent:
    _validate(data.provider)
    await _check_conflict(session, data.name)
    domains = await _resolve_domains(session, data.domain_ids)
    mcp_servers = await _resolve_mcp_servers(session, data.mcp_server_ids)

    agent = Agent(
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
        domains=domains,
        mcp_servers=mcp_servers,
    )
    session.add(agent)
    await session.commit()
    return await get_agent(session, agent.id)


async def update_agent(session: AsyncSession, agent_id: uuid.UUID, data: AgentUpdate) -> Agent:
    agent = await get_agent(session, agent_id)

    new_provider = data.provider if data.provider is not None else agent.provider
    _validate(new_provider)

    if data.name is not None and data.name != agent.name:
        await _check_conflict(session, data.name, exclude_id=agent.id)
        agent.name = data.name

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
    if data.domain_ids is not None:
        agent.domains = await _resolve_domains(session, data.domain_ids)
    if data.mcp_server_ids is not None:
        agent.mcp_servers = await _resolve_mcp_servers(session, data.mcp_server_ids)

    await session.commit()
    return await get_agent(session, agent.id)


async def delete_agent(session: AsyncSession, agent_id: uuid.UUID) -> None:
    agent = await get_agent(session, agent_id)
    await session.delete(agent)
    await session.commit()


async def set_agent_domains(session: AsyncSession, agent_id: uuid.UUID, domain_ids: list[uuid.UUID]) -> Agent:
    agent = await get_agent(session, agent_id)
    agent.domains = await _resolve_domains(session, domain_ids)
    await session.commit()
    return await get_agent(session, agent.id)


async def set_domain_agents(session: AsyncSession, domain_id: uuid.UUID, agent_ids: list[uuid.UUID]) -> Domain:
    from app.modules.domain.service import DomainNotFoundError

    # populate_existing=True: see the comment on the equivalent call in
    # app.modules.domain.service.get_domain — without it session.get()
    # silently ignores ``options`` for objects already in the identity map.
    domain = await session.get(
        Domain, domain_id, options=[selectinload(Domain.agents)], populate_existing=True
    )
    if domain is None:
        raise DomainNotFoundError(str(domain_id))

    if not agent_ids:
        domain.agents = []
    else:
        result = await session.execute(select(Agent).where(Agent.id.in_(agent_ids)))
        found = list(result.scalars().all())
        missing = set(agent_ids) - {a.id for a in found}
        if missing:
            raise AgentValidationError(f"Unknown agent id(s): {', '.join(str(m) for m in missing)}")
        domain.agents = found

    await session.commit()
    await session.refresh(domain, attribute_names=["agents"])
    return domain


async def is_agent_assigned_to_domain(session: AsyncSession, domain_id: uuid.UUID, agent_id: uuid.UUID) -> bool:
    from app.modules.agent.models import domain_agents

    stmt = select(domain_agents.c.agent_id).where(
        domain_agents.c.domain_id == domain_id, domain_agents.c.agent_id == agent_id
    )
    result = await session.execute(stmt)
    return result.first() is not None
