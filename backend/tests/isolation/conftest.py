"""Fixtures for cross-tenant isolation tests."""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import TenantPrincipal
from app.identity.deps import require_org_member
from app.main import create_app
from app.orgs.models import Organization
from app.agents.models import Agent
from app.knowledge.models import KnowledgeBase, Document
from app.apikeys.models import ApiKey


# Organization IDs and metadata
ORG_A_ID = uuid.uuid4()
ORG_A_SLUG = "org-a"
ORG_A_NAME = "Organization A"

ORG_B_ID = uuid.uuid4()
ORG_B_SLUG = "org-b"
ORG_B_NAME = "Organization B"


@pytest.fixture
def org_a_principal() -> TenantPrincipal:
    """Tenant admin principal for org A."""
    return TenantPrincipal(
        user_id="user-a",
        email="admin-a@org-a.test",
        org_alias=ORG_A_SLUG,
        role="admin",
    )


@pytest.fixture
def org_b_principal() -> TenantPrincipal:
    """Tenant admin principal for org B."""
    return TenantPrincipal(
        user_id="user-b",
        email="admin-b@org-b.test",
        org_alias=ORG_B_SLUG,
        role="admin",
    )


async def _create_org(
    session: AsyncSession, org_id: uuid.UUID, name: str, slug: str, status: str = "active"
) -> Organization:
    """Create an organization in the test DB."""
    org = Organization(id=org_id, name=name, slug=slug, status=status)
    session.add(org)
    await session.commit()
    return org


async def _create_agent(
    session: AsyncSession, org_id: uuid.UUID, name: str
) -> Agent:
    """Create an agent in the test DB."""
    agent = Agent(
        id=uuid.uuid4(),
        org_id=org_id,
        name=name,
        provider="ollama",
        model_name="qwen",
    )
    session.add(agent)
    await session.commit()
    return agent


async def _create_kb(
    session: AsyncSession, org_id: uuid.UUID, name: str
) -> KnowledgeBase:
    """Create a knowledge base in the test DB."""
    kb = KnowledgeBase(
        id=uuid.uuid4(),
        org_id=org_id,
        name=name,
        slug=name.lower().replace(" ", "-"),
    )
    session.add(kb)
    await session.commit()
    return kb


async def _create_document(
    session: AsyncSession, org_id: uuid.UUID, kb_id: uuid.UUID, name: str
) -> Document:
    """Create a document in the test DB."""
    doc = Document(
        id=uuid.uuid4(),
        org_id=org_id,
        knowledge_base_id=kb_id,
        filename=name,
        mime_type="text/plain",
        status="completed",
    )
    session.add(doc)
    await session.commit()
    return doc


async def _create_api_key(
    session: AsyncSession, org_id: uuid.UUID, name: str
) -> ApiKey:
    """Create an API key in the test DB."""
    key = ApiKey(
        id=uuid.uuid4(),
        org_id=org_id,
        name=name,
        key_hash="test_hash_" + str(uuid.uuid4()),  # Not a real hash
    )
    session.add(key)
    await session.commit()
    return key


@pytest.fixture
async def isolation_db_session(db_session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Set up two organizations with data, then yield the session."""
    # Create organizations
    await _create_org(db_session, ORG_A_ID, ORG_A_NAME, ORG_A_SLUG)
    await _create_org(db_session, ORG_B_ID, ORG_B_NAME, ORG_B_SLUG)

    # Create agents for each org
    agent_a = await _create_agent(db_session, ORG_A_ID, "Agent A")
    agent_b = await _create_agent(db_session, ORG_B_ID, "Agent B")

    # Create knowledge bases for each org
    kb_a = await _create_kb(db_session, ORG_A_ID, "KB A")
    kb_b = await _create_kb(db_session, ORG_B_ID, "KB B")

    # Create documents for each KB
    doc_a = await _create_document(db_session, ORG_A_ID, kb_a.id, "Doc A")
    doc_b = await _create_document(db_session, ORG_B_ID, kb_b.id, "Doc B")

    # Create API keys for each org
    key_a = await _create_api_key(db_session, ORG_A_ID, "Key A")
    key_b = await _create_api_key(db_session, ORG_B_ID, "Key B")

    # Store IDs for test access
    db_session.org_a_id = ORG_A_ID
    db_session.org_b_id = ORG_B_ID
    db_session.agent_a_id = agent_a.id
    db_session.agent_b_id = agent_b.id
    db_session.kb_a_id = kb_a.id
    db_session.kb_b_id = kb_b.id
    db_session.doc_a_id = doc_a.id
    db_session.doc_b_id = doc_b.id
    db_session.key_a_id = key_a.id
    db_session.key_b_id = key_b.id

    yield db_session


@pytest.fixture
def isolation_app_org_a(
    isolation_db_session: AsyncSession, org_a_principal: TenantPrincipal
) -> FastAPI:
    """FastAPI app as org A principal with isolation DB."""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: isolation_db_session
    app.dependency_overrides[require_org_member] = lambda: org_a_principal
    return app


@pytest.fixture
def isolation_app_org_b(
    isolation_db_session: AsyncSession, org_b_principal: TenantPrincipal
) -> FastAPI:
    """FastAPI app as org B principal with isolation DB."""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: isolation_db_session
    app.dependency_overrides[require_org_member] = lambda: org_b_principal
    return app


@pytest.fixture
async def client_org_a(isolation_app_org_a: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async HTTP client for org A."""
    async with AsyncClient(
        transport=ASGITransport(app=isolation_app_org_a), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
async def client_org_b(isolation_app_org_b: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async HTTP client for org B."""
    async with AsyncClient(
        transport=ASGITransport(app=isolation_app_org_b), base_url="http://test"
    ) as client:
        yield client
