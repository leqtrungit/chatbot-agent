"""Pydantic schemas for the domain module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DomainCreate(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None


class DomainUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None


class DomainRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    agent_ids: list[uuid.UUID] = []

    @classmethod
    def from_domain(cls, domain) -> "DomainRead":  # noqa: ANN001
        return cls(
            id=domain.id,
            name=domain.name,
            slug=domain.slug,
            description=domain.description,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            agent_ids=[a.id for a in domain.agents],
        )


class SetAgentIds(BaseModel):
    agent_ids: list[uuid.UUID]
