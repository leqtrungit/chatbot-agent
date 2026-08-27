"""Pydantic schemas for the agents module (org-scoped, v2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

VALID_PROVIDERS = ("ollama", "openai")


class AgentCreate(BaseModel):
    """Schema for creating a new agent."""

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
    knowledge_base_ids: list[uuid.UUID] = []


class AgentUpdate(BaseModel):
    """Schema for updating an agent."""

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
    knowledge_base_ids: list[uuid.UUID] | None = None


class AgentRead(BaseModel):
    """Schema for reading/returning an agent."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
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
    knowledge_base_ids: list[uuid.UUID] = []

    @classmethod
    def from_orm(cls, agent) -> AgentRead:  # noqa: ANN001
        """Create AgentRead from ORM agent instance."""
        kb_ids = [kb.id for kb in agent.knowledge_bases]
        return cls(
            id=agent.id,
            org_id=agent.org_id,
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
            knowledge_base_ids=kb_ids,
        )


class SetKnowledgeBaseIds(BaseModel):
    """Schema for setting knowledge base links for an agent."""

    knowledge_base_ids: list[uuid.UUID]
