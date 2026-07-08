"""Pydantic schemas for the document module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    domain_id: uuid.UUID
    filename: str
    mime_type: str
    status: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime
