"""ORM model for registered MCP (Model Context Protocol) servers.

An ``McpServer`` row is a remote HTTP/SSE endpoint an admin has registered;
agents opt into a server's tools by linking to it (see
``app.modules.agent.models.agent_mcp_servers``).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class McpServer(Base):
    __tablename__ = "mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    transport: Mapped[str] = mapped_column(String(16), nullable=False, default="http")
    headers: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    agents: Mapped[list["Agent"]] = relationship(  # noqa: F821
        "Agent", secondary="agent_mcp_servers", back_populates="mcp_servers"
    )
