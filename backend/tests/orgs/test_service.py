"""Unit tests for organization service functions (no real DB)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.orgs.models import Organization
from app.orgs.service import create_org, suspend_org, reactivate_org, list_orgs
from tests.orgs.conftest import FakeKeycloakAdmin


class FakeSession:
    """Mock SQLAlchemy session for testing."""

    def __init__(self, should_fail_insert: bool = False):
        """Initialize fake session."""
        self.should_fail_insert = should_fail_insert
        self.added_instances: list = []
        self.flushed = False
        self.committed = False

    def add(self, instance):
        """Mock add."""
        self.added_instances.append(instance)

    async def flush(self):
        """Mock flush."""
        if self.should_fail_insert:
            raise IntegrityError("UNIQUE constraint failed", None, None)
        self.flushed = True

    async def commit(self):
        """Mock commit."""
        self.committed = True

    async def get(self, model, key):
        """Mock get."""
        # For testing suspend/reactivate
        if model is Organization:
            # Return a test org if key matches known ID
            org = Organization(
                id=key,
                name="test-org",
                slug="test-org",
                status="active",
            )
            return org
        return None


@pytest.mark.asyncio
async def test_create_org_success(fake_kc: FakeKeycloakAdmin) -> None:
    """Test successful organization creation."""
    session = FakeSession()
    org = await create_org(session, fake_kc, name="ACME Corp", slug="acme")

    assert org.name == "ACME Corp"
    assert org.slug == "acme"
    assert org.status == "active"
    assert org.keycloak_org_id == "kc-acme-id"
    assert session.flushed is True
    assert len(fake_kc.created_orgs) == 1
    assert "kc-acme-id" in fake_kc.created_orgs


@pytest.mark.asyncio
async def test_create_org_db_fail_calls_delete(fake_kc: FakeKeycloakAdmin) -> None:
    """Test that DB failure triggers Keycloak org deletion (rollback)."""
    session = FakeSession(should_fail_insert=True)

    with pytest.raises(IntegrityError):
        await create_org(session, fake_kc, name="ACME Corp", slug="acme")

    # Verify Keycloak org was created then deleted
    assert len(fake_kc.created_orgs) == 0  # Should be deleted
    assert "kc-acme-id" in fake_kc.deleted_orgs


@pytest.mark.asyncio
async def test_suspend_org(fake_kc: FakeKeycloakAdmin) -> None:
    """Test suspending an organization."""
    session = FakeSession()
    org_id = uuid.uuid4()

    org = await suspend_org(session, org_id)

    assert org.status == "suspended"
    assert session.flushed is True


@pytest.mark.asyncio
async def test_suspend_org_not_found() -> None:
    """Test suspending non-existent organization."""

    class FailSession(FakeSession):
        async def get(self, model, key):
            return None

    session = FailSession()
    org_id = uuid.uuid4()

    with pytest.raises(ValueError, match="Organization .* not found"):
        await suspend_org(session, org_id)


@pytest.mark.asyncio
async def test_reactivate_org(fake_kc: FakeKeycloakAdmin) -> None:
    """Test reactivating a suspended organization."""

    class SuspendedOrgSession(FakeSession):
        async def get(self, model, key):
            org = Organization(
                id=key,
                name="test-org",
                slug="test-org",
                status="suspended",
            )
            return org

    session = SuspendedOrgSession()
    org_id = uuid.uuid4()

    org = await reactivate_org(session, org_id)

    assert org.status == "active"
    assert session.flushed is True


@pytest.mark.asyncio
async def test_reactivate_org_not_found() -> None:
    """Test reactivating non-existent organization."""

    class FailSession(FakeSession):
        async def get(self, model, key):
            return None

    session = FailSession()
    org_id = uuid.uuid4()

    with pytest.raises(ValueError, match="Organization .* not found"):
        await reactivate_org(session, org_id)


@pytest.mark.asyncio
async def test_list_orgs() -> None:
    """Test listing all organizations."""

    class ListOrgSession(FakeSession):
        async def execute(self, stmt):
            class Result:
                def scalars(self):
                    class Scalars:
                        def all(self):
                            return [
                                Organization(
                                    id=uuid.uuid4(),
                                    name="org1",
                                    slug="org1",
                                    status="active",
                                ),
                                Organization(
                                    id=uuid.uuid4(),
                                    name="org2",
                                    slug="org2",
                                    status="suspended",
                                ),
                            ]

                    return Scalars()

            return Result()

    session = ListOrgSession()
    orgs = await list_orgs(session)

    assert len(orgs) == 2
    assert orgs[0].name == "org1"
    assert orgs[1].name == "org2"
    assert orgs[1].status == "suspended"
