"""Fixtures for agents API tests."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import TenantPrincipal
from app.identity.deps import require_org_member
from app.identity.org_access import OrgContext, require_org_access
from app.main import create_app
from app.orgs.models import Organization
from app.agents.models import Agent
from app.agents.router import get_agent_router
from app.knowledge.models import KnowledgeBase


ORG_ID_1 = uuid.uuid4()
ORG_ID_2 = uuid.uuid4()
USER_ID_1 = "user-1"
USER_ID_2 = "user-2"


@pytest.fixture
def principal_org1() -> TenantPrincipal:
    """Tenant admin principal for org 1."""
    return TenantPrincipal(user_id=USER_ID_1, email=None, org_alias="acme", role="admin")


@pytest.fixture
def principal_org2() -> TenantPrincipal:
    """Tenant admin principal for org 2."""
    return TenantPrincipal(user_id=USER_ID_2, email=None, org_alias="globex", role="admin")


class _FakeSession:
    """Fake async session for unit tests (minimal DB operations)."""

    def __init__(self, orgs: dict[uuid.UUID, Organization]):
        from datetime import datetime, timezone
        self._orgs = orgs
        self._agents: dict[uuid.UUID, Agent] = {}
        self._now = datetime.now(timezone.utc)

    async def get(self, model: type, key: uuid.UUID) -> Any:
        """Get an entity by ID."""
        if model is Organization:
            return self._orgs.get(key)
        elif model is Agent:
            return self._agents.get(key)
        return None

    async def execute(self, stmt: Any) -> Any:
        """Execute a SQL statement (minimal mock for testing)."""
        # This is a minimal mock that handles basic select statements
        # For unit tests, we don't actually need full SQL execution
        return _FakeResult([])

    def add(self, instance: Any) -> None:
        """Add an instance to the session."""
        if isinstance(instance, Agent):
            self._agents[instance.id] = instance

    async def commit(self) -> None:
        """Commit the session - set defaults for id/created_at/updated_at."""
        from datetime import datetime, timezone
        # Create a new dict to update agents with proper defaults
        updated_agents = {}
        for agent_id, agent in self._agents.items():
            if agent.id is None:
                agent.id = uuid.uuid4()
            if agent.created_at is None:
                agent.created_at = datetime.now(timezone.utc)
            if agent.updated_at is None:
                agent.updated_at = datetime.now(timezone.utc)
            updated_agents[agent.id] = agent
        self._agents = updated_agents

    async def refresh(self, instance: Any) -> None:
        """Refresh an instance from the database."""
        pass


class _FakeResult:
    """Fake SQLAlchemy result."""

    def __init__(self, rows: list[Any]):
        self._rows = rows

    def scalars(self):
        """Return scalars view."""
        return self

    def all(self):
        """Return all rows."""
        return self._rows

    def first(self):
        """Return first row."""
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        """Return single row or None."""
        return self._rows[0] if self._rows else None


def _make_org(org_id: uuid.UUID, slug: str, status: str = "active") -> Organization:
    """Create a fake organization."""
    org = Organization(id=org_id, name=slug, slug=slug, status=status)
    return org


@pytest.fixture
def app_unit(principal_org1: TenantPrincipal) -> FastAPI:
    """FastAPI app with dependency overrides for unit tests (no DB needed)."""
    app = create_app()
    app.include_router(get_agent_router())
    orgs = {
        ORG_ID_1: _make_org(ORG_ID_1, "acme"),
        ORG_ID_2: _make_org(ORG_ID_2, "globex"),
    }
    app.dependency_overrides[get_session] = lambda: _FakeSession(orgs)
    app.dependency_overrides[require_org_member] = lambda: principal_org1
    return app


@pytest.fixture
async def client_unit(app_unit: FastAPI) -> AsyncClient:
    """Async HTTP client for unit tests."""
    async with AsyncClient(
        transport=ASGITransport(app=app_unit),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
async def db_client(app: FastAPI, session_maker) -> AsyncClient:
    """Async HTTP client for DB-backed tests."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
