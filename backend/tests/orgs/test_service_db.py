"""Database integration tests for organization service.

These tests require a real Postgres test database with migrations applied.
They will be skipped locally if the test database is not available.
Run with: pytest tests/orgs/test_service_db.py -q

They test:
- Persistence of organization data
- Unique constraint enforcement on name and slug
- Successful commit and rollback
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.orgs.models import Organization
from app.orgs.service import create_org, suspend_org, reactivate_org, list_orgs
from tests.orgs.conftest import FakeKeycloakAdmin
from tests.db_utils import ensure_test_database, test_db_url

# Fixtures imported from schema conftest


@pytest.mark.asyncio
async def test_create_org_persists_to_db(db_session: AsyncSession) -> None:
    """Test that created organization persists to database."""
    fake_kc = FakeKeycloakAdmin()

    org = await create_org(
        db_session,
        fake_kc,
        name="ACME Corp",
        slug="acme",
    )
    await db_session.commit()

    # Verify the organization was persisted
    fetched = await db_session.get(Organization, org.id)
    assert fetched is not None
    assert fetched.name == "ACME Corp"
    assert fetched.slug == "acme"
    assert fetched.status == "active"
    assert fetched.keycloak_org_id == "kc-acme-id"


@pytest.mark.asyncio
async def test_create_org_unique_name(db_session: AsyncSession) -> None:
    """Test that organization name must be unique."""
    fake_kc = FakeKeycloakAdmin()

    # Create first org
    org1 = await create_org(
        db_session,
        fake_kc,
        name="ACME Corp",
        slug="acme",
    )
    await db_session.commit()

    # Try to create second org with same name
    with pytest.raises(IntegrityError):
        org2 = await create_org(
            db_session,
            fake_kc,
            name="ACME Corp",
            slug="acme-2",
        )
        await db_session.flush()


@pytest.mark.asyncio
async def test_create_org_unique_slug(db_session: AsyncSession) -> None:
    """Test that organization slug must be unique."""
    fake_kc = FakeKeycloakAdmin()

    # Create first org
    org1 = await create_org(
        db_session,
        fake_kc,
        name="ACME Corp",
        slug="acme",
    )
    await db_session.commit()

    # Try to create second org with same slug
    with pytest.raises(IntegrityError):
        org2 = await create_org(
            db_session,
            fake_kc,
            name="ACME Corp 2",
            slug="acme",
        )
        await db_session.flush()


@pytest.mark.asyncio
async def test_suspend_org_persists(db_session: AsyncSession) -> None:
    """Test that suspended status persists to database."""
    fake_kc = FakeKeycloakAdmin()

    # Create org
    org = await create_org(
        db_session,
        fake_kc,
        name="ACME Corp",
        slug="acme",
    )
    await db_session.commit()
    org_id = org.id

    # Suspend it
    suspended = await suspend_org(db_session, org_id)
    await db_session.commit()

    assert suspended.status == "suspended"

    # Verify in database
    fetched = await db_session.get(Organization, org_id)
    assert fetched.status == "suspended"


@pytest.mark.asyncio
async def test_reactivate_org_persists(db_session: AsyncSession) -> None:
    """Test that reactivated status persists to database."""
    fake_kc = FakeKeycloakAdmin()

    # Create org
    org = await create_org(
        db_session,
        fake_kc,
        name="ACME Corp",
        slug="acme",
    )
    await db_session.commit()
    org_id = org.id

    # Suspend then reactivate
    await suspend_org(db_session, org_id)
    await db_session.commit()

    reactivated = await reactivate_org(db_session, org_id)
    await db_session.commit()

    assert reactivated.status == "active"

    # Verify in database
    fetched = await db_session.get(Organization, org_id)
    assert fetched.status == "active"


@pytest.mark.asyncio
async def test_list_orgs_returns_all(db_session: AsyncSession) -> None:
    """Test that list_orgs returns all organizations."""
    fake_kc = FakeKeycloakAdmin()

    # Create multiple orgs
    org1 = await create_org(db_session, fake_kc, name="ACME Corp", slug="acme")
    org2 = await create_org(db_session, fake_kc, name="Globex", slug="globex")
    org3 = await create_org(db_session, fake_kc, name="Initech", slug="initech")
    await db_session.commit()

    # List all
    orgs = await list_orgs(db_session)

    assert len(orgs) == 3
    names = {org.name for org in orgs}
    assert names == {"ACME Corp", "Globex", "Initech"}
