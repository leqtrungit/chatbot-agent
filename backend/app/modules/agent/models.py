"""ORM models for user-managed agents: provider/model/tools config, plus
the many-to-many links to domains and MCP servers.

An ``Agent`` row is a reusable chat configuration (provider, model,
credentials, system prompt template, tool set). It is not tied to a single
domain: ``domain_agents`` links it to every domain it may serve, and the
caller of the public webhook/chat-stream endpoint picks which linked agent
handles a given message by sending ``agent_id`` explicitly.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

domain_agents = Table(
    "domain_agents",
    Base.metadata,
    Column("domain_id", UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), primary_key=True),
    Column("agent_id", UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
)

agent_mcp_servers = Table(
    "agent_mcp_servers",
    Base.metadata,
    Column("agent_id", UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "mcp_server_id", UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), primary_key=True
    ),
)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    enable_knowledge_search: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    domains: Mapped[list["Domain"]] = relationship(  # noqa: F821
        "Domain", secondary=domain_agents, back_populates="agents"
    )
    mcp_servers: Mapped[list["McpServer"]] = relationship(  # noqa: F821
        "McpServer", secondary=agent_mcp_servers, back_populates="agents"
    )
