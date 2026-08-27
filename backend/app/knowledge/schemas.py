"""Pydantic schemas for the knowledge module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    """Schema for creating a KnowledgeBase."""

    name: str = Field(..., description="Knowledge base name")
    slug: str | None = Field(None, description="URL-friendly slug (auto-generated from name if omitted)")
    description: str | None = Field(None, description="Optional description")


class KnowledgeBaseUpdate(BaseModel):
    """Schema for updating a KnowledgeBase."""

    name: str | None = Field(None, description="New name (if updating)")
    slug: str | None = Field(None, description="New slug (if updating)")
    description: str | None = Field(None, description="New description (if updating)")


class KnowledgeBaseRead(BaseModel):
    """Schema for reading a KnowledgeBase."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentCreate(BaseModel):
    """Schema for creating a Document (file upload)."""

    # Note: file content and filename come from multipart form, not JSON


class DocumentRead(BaseModel):
    """Schema for reading a Document."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    org_id: uuid.UUID
    filename: str
    mime_type: str
    status: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime
