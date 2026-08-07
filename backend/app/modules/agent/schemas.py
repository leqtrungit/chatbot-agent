"""Pydantic schemas for the agent module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

VALID_PROVIDERS = ("ollama", "openai")


class AgentCreate(BaseModel):
    name: str
    provider: str
    base_url: str | None = None
    api_key: str | None = None
    model_name: str
    system_prompt: str | None = None
    max_iterations: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    enable_knowledge_search: bool = True
    is_active: bool = True
    mcp_server_ids: list[uuid.UUID] = []
    domain_ids: list[uuid.UUID] = []


class AgentUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    system_prompt: str | None = None
    max_iterations: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    enable_knowledge_search: bool | None = None
    is_active: bool | None = None
    mcp_server_ids: list[uuid.UUID] | None = None
    domain_ids: list[uuid.UUID] | None = None


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    provider: str
    base_url: str | None = None
    model_name: str
    system_prompt: str | None = None
    max_iterations: int
    temperature: float | None = None
    top_p: float | None = None
    enable_knowledge_search: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    mcp_server_ids: list[uuid.UUID] = []
    domain_ids: list[uuid.UUID] = []

    @classmethod
    def from_agent(cls, agent) -> "AgentRead":  # noqa: ANN001
        return cls(
            id=agent.id,
            name=agent.name,
            provider=agent.provider,
            base_url=agent.base_url,
            model_name=agent.model_name,
            system_prompt=agent.system_prompt,
            max_iterations=agent.max_iterations,
            temperature=agent.temperature,
            top_p=agent.top_p,
            enable_knowledge_search=agent.enable_knowledge_search,
            is_active=agent.is_active,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            mcp_server_ids=[s.id for s in agent.mcp_servers],
            domain_ids=[d.id for d in agent.domains],
        )


class SetDomainIds(BaseModel):
    domain_ids: list[uuid.UUID]
