"""DB-backed tests for agents API: persistence, org-scoping, KB linking."""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import TenantPrincipal
from app.identity.deps import require_org_member
from app.identity.org_access import require_org_access
from app.main import create_app
from app.agents.models import Agent, kb_agents
from app.agents.router import get_agent_router
from app.knowledge.models import KnowledgeBase
from app.orgs.models import Organization

async def _create_org(session: AsyncSession, org_id: uuid.UUID, name: str) -> Organization:
    """Create an organization in the test DB."""
    org = Organization(id=org_id, name=name, slug=name.lower(), status="active")
    session.add(org)
    await session.commit()
    return org


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


def _principal(alias: str) -> TenantPrincipal:
    """Create a tenant principal."""
    return TenantPrincipal(user_id="user-1", email=None, org_alias=alias, role="admin")


def _make_app(
    session: AsyncSession, principal: TenantPrincipal
) -> FastAPI:
    """Create app with DB session and principal overrides."""
    app = create_app()
    app.include_router(get_agent_router())
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[require_org_member] = lambda: principal
    return app


@pytest.mark.asyncio
async def test_create_agent_persists_to_db(
    db_session: AsyncSession
) -> None:
    """Create agent is persisted to database."""
    org_id = uuid.uuid4()
    await _create_org(db_session, org_id, "TestOrg")

    app = _make_app(db_session, _principal("testorg"))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/v2/orgs/{org_id}/agents",
            json={
                "name": "Persistent Bot",
                "provider": "ollama",
                "model_name": "qwen",
            },
        )
        assert resp.status_code == 201
        agent_id = resp.json()["id"]

    # Verify in database directly
    agent = await session.get(Agent, agent_id)
    assert agent is not None
    assert agent.org_id == org_id
    assert agent.name == "Persistent Bot"
    assert agent.provider == "ollama"


@pytest.mark.asyncio
async def test_unique_agent_name_per_org(db_session: AsyncSession) -> None:
    """Agent names must be unique within an org, but can repeat across orgs."""
    org1_id = uuid.uuid4()
    org2_id = uuid.uuid4()
    await _create_org(db_session, org1_id, "Org1")
    await _create_org(db_session, org2_id, "Org2")

    # Create agent in org1
    app1 = _make_app(db_session, _principal("org1"))
    async with AsyncClient(
        transport=ASGITransport(app=app1), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/v2/orgs/{org1_id}/agents",
            json={"name": "SharedName", "provider": "ollama", "model_name": "x"},
        )
        assert resp.status_code == 201

        # Try to create same name in org1 again
        resp = await client.post(
            f"/v2/orgs/{org1_id}/agents",
            json={"name": "SharedName", "provider": "ollama", "model_name": "x"},
        )
        assert resp.status_code == 409

    # Create same name in org2 (should succeed)
    app2 = _make_app(session, _principal("org2"))
    async with AsyncClient(
        transport=ASGITransport(app=app2), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/v2/orgs/{org2_id}/agents",
            json={"name": "SharedName", "provider": "ollama", "model_name": "x"},
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
async def test_cross_org_agent_not_accessible(
    db_session: AsyncSession
) -> None:
    """Agent in org1 is not accessible by principal of org2."""
    org1_id = uuid.uuid4()
    org2_id = uuid.uuid4()
    await _create_org(db_session, org1_id, "Org1")
    await _create_org(db_session, org2_id, "Org2")

    # Create agent in org1
    app1 = _make_app(db_session, _principal("org1"))
    async with AsyncClient(
        transport=ASGITransport(app=app1), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/v2/orgs/{org1_id}/agents",
            json={"name": "OrgSpecific", "provider": "ollama", "model_name": "x"},
        )
        assert resp.status_code == 201
        agent_id = resp.json()["id"]

    # Try to access from org2
    app2 = _make_app(session, _principal("org2"))
    async with AsyncClient(
        transport=ASGITransport(app=app2), base_url="http://test"
    ) as client:
        resp = await client.get(f"/v2/orgs/{org1_id}/agents/{agent_id}")
        assert resp.status_code == 404  # Not found from org2 perspective


@pytest.mark.asyncio
async def test_set_agent_knowledge_bases_same_org(
    db_session: AsyncSession
) -> None:
    """Link agent to knowledge bases within same org."""
    org_id = uuid.uuid4()
    await _create_org(db_session, org_id, "TestOrg")
    kb1 = await _create_kb(db_session, org_id, "KB1")
    kb2 = await _create_kb(db_session, org_id, "KB2")

    app = _make_app(db_session, _principal("testorg"))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create agent
        create_resp = await client.post(
            f"/v2/orgs/{org_id}/agents",
            json={"name": "Multi KB Bot", "provider": "ollama", "model_name": "x"},
        )
        agent_id = create_resp.json()["id"]

        # Link to KBs
        set_resp = await client.put(
            f"/v2/orgs/{org_id}/agents/{agent_id}/knowledge-bases",
            json={"knowledge_base_ids": [kb1.id, kb2.id]},
        )
        assert set_resp.status_code == 200
        assert sorted(set_resp.json()["knowledge_base_ids"]) == sorted(
            [kb1.id, kb2.id]
        )

    # Verify in DB
    stmt = (
        "SELECT agent_id, knowledge_base_id FROM kb_agents WHERE agent_id = %s"
    )
    # Note: in real test need to use SQLAlchemy, but showing the concept


@pytest.mark.asyncio
async def test_set_agent_knowledge_bases_cross_org_404(
    db_session: AsyncSession
) -> None:
    """Linking agent to KB from different org returns 404."""
    org1_id = uuid.uuid4()
    org2_id = uuid.uuid4()
    await _create_org(db_session, org1_id, "Org1")
    await _create_org(db_session, org2_id, "Org2")
    kb2 = await _create_kb(db_session, org2_id, "Org2KB")

    app1 = _make_app(db_session, _principal("org1"))
    async with AsyncClient(
        transport=ASGITransport(app=app1), base_url="http://test"
    ) as client:
        # Create agent in org1
        create_resp = await client.post(
            f"/v2/orgs/{org1_id}/agents",
            json={"name": "Org1 Bot", "provider": "ollama", "model_name": "x"},
        )
        agent_id = create_resp.json()["id"]

        # Try to link to KB from org2
        set_resp = await client.put(
            f"/v2/orgs/{org1_id}/agents/{agent_id}/knowledge-bases",
            json={"knowledge_base_ids": [kb2.id]},
        )
        # Should return 404 with message indicating missing KB ID
        assert set_resp.status_code == 404
        assert kb2.id in set_resp.json()["detail"]


@pytest.mark.asyncio
async def test_update_agent_in_db(db_session: AsyncSession) -> None:
    """Update agent persists to database."""
    org_id = uuid.uuid4()
    await _create_org(db_session, org_id, "TestOrg")

    app = _make_app(db_session, _principal("testorg"))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create
        create_resp = await client.post(
            f"/v2/orgs/{org_id}/agents",
            json={
                "name": "Updatable",
                "provider": "ollama",
                "model_name": "qwen",
                "temperature": 0.5,
            },
        )
        agent_id = create_resp.json()["id"]

        # Update
        update_resp = await client.put(
            f"/v2/orgs/{org_id}/agents/{agent_id}",
            json={"temperature": 0.9, "max_iterations": 3},
        )
        assert update_resp.status_code == 200

    # Verify in DB
    agent = await session.get(Agent, agent_id)
    assert agent.temperature == 0.9
    assert agent.max_iterations == 3


@pytest.mark.asyncio
async def test_deactivate_agent_in_db(db_session: AsyncSession) -> None:
    """Deactivate agent sets is_active=False in database."""
    org_id = uuid.uuid4()
    await _create_org(db_session, org_id, "TestOrg")

    app = _make_app(db_session, _principal("testorg"))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create
        create_resp = await client.post(
            f"/v2/orgs/{org_id}/agents",
            json={"name": "Deactivatable", "provider": "ollama", "model_name": "x"},
        )
        agent_id = create_resp.json()["id"]

        # Deactivate
        deactivate_resp = await client.post(
            f"/v2/orgs/{org_id}/agents/{agent_id}/deactivate"
        )
        assert deactivate_resp.status_code == 200
        assert deactivate_resp.json()["is_active"] is False

    # Verify in DB
    agent = await session.get(Agent, agent_id)
    assert agent.is_active is False
    assert agent is not None  # Row still exists (soft delete)
