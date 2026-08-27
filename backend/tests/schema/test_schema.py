"""Tests for schema architecture, tenancy enforcement, and CRUD operations."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import ForeignKey, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.db import Base
from app.core.tenancy import OrgScopedRepo, TenancyViolationError, org_query
from app.apikeys.models import ApiKey
from app.agents.models import Agent
from app.knowledge.models import KnowledgeBase, Document
from app.orgs.models import Organization


class TestSchemaArchitecture:
    """Test that schema follows multi-tenant conventions."""

    def test_all_business_tables_have_org_id(self):
        """Verify that all business tables (except link tables) have org_id column."""
        # These tables are allowed to not have org_id: organizations (it IS the org)
        # and link tables (kb_agents)
        org_table_names = {"organizations", "kb_agents"}

        for table_name, table in Base.metadata.tables.items():
            if table_name in org_table_names:
                continue

            # All other tables must have org_id
            assert "org_id" in table.columns, (
                f"Table {table_name} must have org_id column (NFR-SEC1)"
            )

            org_id_col = table.columns["org_id"]
            assert not org_id_col.nullable, (
                f"Column org_id in {table_name} must be NOT NULL"
            )

    def test_all_business_tables_have_org_fk(self):
        """Verify that all business tables with org_id have FK to organizations."""
        org_table_names = {"organizations", "kb_agents"}

        for table_name, table in Base.metadata.tables.items():
            if table_name not in org_table_names and "org_id" in table.columns:
                # Check for FK to organizations
                fks = [fk for fk in table.foreign_keys if fk.column.table.name == "organizations"]
                assert len(fks) > 0, (
                    f"Table {table_name} has org_id but no FK to organizations"
                )


class TestOrgQuery:
    """Test the org_query helper function."""

    @pytest.mark.asyncio
    async def test_org_query_filters_by_org_id(self, db_session: AsyncSession):
        """Test that org_query creates a query filtered by org_id."""
        org1_id = uuid.uuid4()
        org2_id = uuid.uuid4()

        # Create two organizations
        org1 = Organization(id=org1_id, name="Org 1", slug="org-1", status="active")
        org2 = Organization(id=org2_id, name="Org 2", slug="org-2", status="active")
        db_session.add(org1)
        db_session.add(org2)
        await db_session.flush()

        # Create agents for each org
        agent1 = Agent(
            id=uuid.uuid4(),
            org_id=org1_id,
            name="Agent 1",
            provider="openai",
            model_name="gpt-4",
        )
        agent2 = Agent(
            id=uuid.uuid4(),
            org_id=org2_id,
            name="Agent 2",
            provider="openai",
            model_name="gpt-4",
        )
        db_session.add(agent1)
        db_session.add(agent2)
        await db_session.flush()

        # Query agents for org1
        stmt = org_query(Agent, org1_id)
        result = await db_session.execute(stmt)
        agents = result.scalars().all()

        assert len(agents) == 1
        assert agents[0].org_id == org1_id


class TestOrgScopedRepo:
    """Test the OrgScopedRepo data-access helper."""

    @pytest.mark.asyncio
    async def test_get_returns_none_for_wrong_org(self, db_session: AsyncSession):
        """Test that OrgScopedRepo.get() returns None when org_id doesn't match."""
        org1_id = uuid.uuid4()
        org2_id = uuid.uuid4()

        org1 = Organization(id=org1_id, name="Org 1", slug="org-1", status="active")
        org2 = Organization(id=org2_id, name="Org 2", slug="org-2", status="active")
        db_session.add(org1)
        db_session.add(org2)
        await db_session.flush()

        agent_id = uuid.uuid4()
        agent = Agent(
            id=agent_id,
            org_id=org1_id,
            name="Test Agent",
            provider="openai",
            model_name="gpt-4",
        )
        db_session.add(agent)
        await db_session.commit()

        # Create repo scoped to org1
        repo1 = OrgScopedRepo(db_session, org1_id)
        result1 = await repo1.get(Agent, agent_id)
        assert result1 is not None
        assert result1.org_id == org1_id

        # Create repo scoped to org2
        repo2 = OrgScopedRepo(db_session, org2_id)
        result2 = await repo2.get(Agent, agent_id)
        assert result2 is None

    @pytest.mark.asyncio
    async def test_add_raises_tenancy_violation(self, db_session: AsyncSession):
        """Test that OrgScopedRepo.add() raises TenancyViolationError when org_id doesn't match."""
        org1_id = uuid.uuid4()
        org2_id = uuid.uuid4()

        org1 = Organization(id=org1_id, name="Org 1", slug="org-1", status="active")
        org2 = Organization(id=org2_id, name="Org 2", slug="org-2", status="active")
        db_session.add(org1)
        db_session.add(org2)
        await db_session.flush()

        repo1 = OrgScopedRepo(db_session, org1_id)

        # Try to add agent for org2 to org1's repo
        agent = Agent(
            id=uuid.uuid4(),
            org_id=org2_id,
            name="Wrong Org Agent",
            provider="openai",
            model_name="gpt-4",
        )

        with pytest.raises(TenancyViolationError):
            await repo1.add(agent)

    @pytest.mark.asyncio
    async def test_list_filters_by_org(self, db_session: AsyncSession):
        """Test that OrgScopedRepo.list() only returns entities for the scoped org."""
        org1_id = uuid.uuid4()
        org2_id = uuid.uuid4()

        org1 = Organization(id=org1_id, name="Org 1", slug="org-1", status="active")
        org2 = Organization(id=org2_id, name="Org 2", slug="org-2", status="active")
        db_session.add(org1)
        db_session.add(org2)
        await db_session.flush()

        # Create 2 agents in org1, 1 in org2
        for i in range(2):
            agent = Agent(
                id=uuid.uuid4(),
                org_id=org1_id,
                name=f"Org1 Agent {i}",
                provider="openai",
                model_name="gpt-4",
            )
            db_session.add(agent)

        agent2 = Agent(
            id=uuid.uuid4(),
            org_id=org2_id,
            name="Org2 Agent",
            provider="openai",
            model_name="gpt-4",
        )
        db_session.add(agent2)
        await db_session.commit()

        repo1 = OrgScopedRepo(db_session, org1_id)
        agents1 = await repo1.list(Agent)
        assert len(agents1) == 2
        assert all(a.org_id == org1_id for a in agents1)

        repo2 = OrgScopedRepo(db_session, org2_id)
        agents2 = await repo2.list(Agent)
        assert len(agents2) == 1
        assert agents2[0].org_id == org2_id

    @pytest.mark.asyncio
    async def test_delete_enforces_org_scoping(self, db_session: AsyncSession):
        """Test that OrgScopedRepo.delete() enforces org scoping."""
        org1_id = uuid.uuid4()
        org2_id = uuid.uuid4()

        org1 = Organization(id=org1_id, name="Org 1", slug="org-1", status="active")
        org2 = Organization(id=org2_id, name="Org 2", slug="org-2", status="active")
        db_session.add(org1)
        db_session.add(org2)
        await db_session.flush()

        agent1 = Agent(
            id=uuid.uuid4(),
            org_id=org1_id,
            name="Agent 1",
            provider="openai",
            model_name="gpt-4",
        )
        agent2 = Agent(
            id=uuid.uuid4(),
            org_id=org2_id,
            name="Agent 2",
            provider="openai",
            model_name="gpt-4",
        )
        db_session.add(agent1)
        db_session.add(agent2)
        await db_session.commit()

        repo1 = OrgScopedRepo(db_session, org1_id)

        # Try to delete agent from org2 using org1's repo
        with pytest.raises(TenancyViolationError):
            await repo1.delete(agent2)


class TestUniqueConstraints:
    """Test that unique constraints work correctly across orgs."""

    @pytest.mark.asyncio
    async def test_agent_name_unique_within_org(self, db_session: AsyncSession):
        """Test that agent name is unique within an org but not across orgs."""
        org1_id = uuid.uuid4()
        org2_id = uuid.uuid4()

        org1 = Organization(id=org1_id, name="Org 1", slug="org-1", status="active")
        org2 = Organization(id=org2_id, name="Org 2", slug="org-2", status="active")
        db_session.add(org1)
        db_session.add(org2)
        await db_session.flush()

        # Create agent with same name in org1
        agent1 = Agent(
            id=uuid.uuid4(),
            org_id=org1_id,
            name="TestAgent",
            provider="openai",
            model_name="gpt-4",
        )
        db_session.add(agent1)
        await db_session.commit()

        # Should be able to create agent with same name in org2
        agent2 = Agent(
            id=uuid.uuid4(),
            org_id=org2_id,
            name="TestAgent",
            provider="openai",
            model_name="gpt-4",
        )
        db_session.add(agent2)
        await db_session.commit()

        # But should NOT be able to create another agent with same name in org1
        agent3 = Agent(
            id=uuid.uuid4(),
            org_id=org1_id,
            name="TestAgent",
            provider="openai",
            model_name="gpt-4",
        )
        db_session.add(agent3)

        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_org_name_globally_unique(self, db_session: AsyncSession):
        """Test that organization name is globally unique."""
        org1 = Organization(id=uuid.uuid4(), name="UniqueOrg", slug="unique-org", status="active")
        db_session.add(org1)
        await db_session.commit()

        org2 = Organization(id=uuid.uuid4(), name="UniqueOrg", slug="unique-org-2", status="active")
        db_session.add(org2)

        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_knowledge_base_name_unique_within_org(self, db_session: AsyncSession):
        """Test that KB name is unique within an org."""
        org_id = uuid.uuid4()
        org = Organization(id=org_id, name="Test Org", slug="test-org", status="active")
        db_session.add(org)
        await db_session.flush()

        kb1 = KnowledgeBase(
            id=uuid.uuid4(),
            org_id=org_id,
            name="TestKB",
            slug="test-kb",
        )
        db_session.add(kb1)
        await db_session.commit()

        kb2 = KnowledgeBase(
            id=uuid.uuid4(),
            org_id=org_id,
            name="TestKB",
            slug="test-kb-2",
        )
        db_session.add(kb2)

        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()


class TestMigrationIdempotent:
    """Test that migrations can be run multiple times safely."""

    @pytest.mark.asyncio
    async def test_schema_creation_is_idempotent(self, test_engine):
        """Test that running create_all twice doesn't fail."""
        async with test_engine.begin() as conn:
            # Already created in fixture, try again
            await conn.run_sync(Base.metadata.create_all)
        # If we get here without exception, test passes
        assert True
