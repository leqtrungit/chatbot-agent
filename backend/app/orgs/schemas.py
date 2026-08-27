"""Pydantic schemas for the organizations module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrgCreate(BaseModel):
    """Request schema for creating an organization."""

    name: str = Field(..., min_length=1, max_length=255, description="Organization name")
    slug: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9-]+$",
        description="URL-friendly slug (lowercase, alphanumeric, hyphens only)",
    )


class OrgRead(BaseModel):
    """Response schema for organization."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: str = Field(description="Organization status: 'active' or 'suspended'")
    keycloak_org_id: str | None = Field(description="Keycloak Organization ID")
    created_at: datetime
