"""Unit tests for organization router endpoints (no real DB)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.identity.deps import require_operator
from app.core.security import OperatorPrincipal
from app.orgs.models import Organization
from app.orgs.router import router as orgs_router
from tests.orgs.conftest import FakeKeycloakAdmin


class FakeSession:
    """Mock SQLAlchemy session for routing tests."""

    def __init__(self):
        """Initialize fake session."""
        self.orgs: dict[uuid.UUID, Organization] = {}
        self.next_org: Organization | None = None

    def add(self, instance):
        """Mock add."""
        # Ensure id is set
        if instance.id is None:
            instance.id = uuid.uuid4()
        # Ensure created_at is set
        if instance.created_at is None:
            instance.created_at = datetime.now(timezone.utc)
        self.orgs[instance.id] = instance

    async def flush(self):
        """Mock flush."""
        pass

    async def commit(self):
        """Mock commit."""
        pass

    async def rollback(self):
        """Mock rollback."""
        pass

    async def get(self, model, key):
        """Mock get."""
        if model is Organization:
            org = None
            if key in self.orgs:
                org = self.orgs[key]
            elif self.next_org is not None:
                org = self.next_org
            # Ensure created_at is set
            if org is not None and org.created_at is None:
                org.created_at = datetime.now(timezone.utc)
            return org
        return None

    async def execute(self, stmt):
        """Mock execute (for list)."""
        class Result:
            def __init__(self, orgs_list):
                self._orgs = orgs_list

            def scalars(self):
                class Scalars:
                    def __init__(self, orgs_list):
                        self._orgs = orgs_list

                    def all(self):
                        # Ensure all orgs have created_at
                        for org in self._orgs:
                            if org.created_at is None:
                                org.created_at = datetime.now(timezone.utc)
                        return self._orgs

                return Scalars(self._orgs)

        return Result(list(self.orgs.values()))


def _create_test_app(
    session: FakeSession, principal: OperatorPrincipal, kc: FakeKeycloakAdmin
) -> FastAPI:
    """Create a test FastAPI app with mocked dependencies."""
    app = FastAPI()
    app.include_router(orgs_router)

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[require_operator] = lambda: principal

    # Override Keycloak Admin client
    from app.orgs.router import get_kc_admin

    app.dependency_overrides[get_kc_admin] = lambda: kc

    return app


def _test_principal() -> OperatorPrincipal:
    """Create a test operator principal."""
    return OperatorPrincipal(user_id="operator-user", email="operator@test.local")


@pytest.mark.asyncio
async def test_create_org_success(fake_kc: FakeKeycloakAdmin) -> None:
    """Test creating an organization via POST /v2/operator/orgs."""
    session = FakeSession()
    app = _create_test_app(session, _test_principal(), fake_kc)

    client = TestClient(app)
    response = client.post(
        "/v2/operator/orgs",
        json={"name": "ACME Corp", "slug": "acme"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "ACME Corp"
    assert data["slug"] == "acme"
    assert data["status"] == "active"
    assert data["keycloak_org_id"] == "kc-acme-id"


def test_create_org_invalid_slug(fake_kc: FakeKeycloakAdmin) -> None:
    """Test creating an organization with invalid slug."""
    session = FakeSession()
    app = _create_test_app(session, _test_principal(), fake_kc)

    client = TestClient(app)
    response = client.post(
        "/v2/operator/orgs",
        json={"name": "ACME Corp", "slug": "INVALID_UPPERCASE"},
    )

    # Should fail validation (422)
    assert response.status_code == 422




def test_suspend_org(fake_kc: FakeKeycloakAdmin) -> None:
    """Test suspending an organization."""
    org_id = uuid.uuid4()
    org = Organization(
        id=org_id,
        name="ACME",
        slug="acme",
        status="active",
        keycloak_org_id="kc-acme",
        created_at=datetime.now(timezone.utc),
    )

    session = FakeSession()
    session.next_org = org

    app = _create_test_app(session, _test_principal(), fake_kc)
    client = TestClient(app)

    response = client.post(f"/v2/operator/orgs/{org_id}/suspend")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "suspended"


def test_suspend_org_not_found(fake_kc: FakeKeycloakAdmin) -> None:
    """Test suspending a non-existent organization."""
    session = FakeSession()
    app = _create_test_app(session, _test_principal(), fake_kc)
    client = TestClient(app)

    org_id = uuid.uuid4()
    response = client.post(f"/v2/operator/orgs/{org_id}/suspend")

    assert response.status_code == 404


def test_reactivate_org(fake_kc: FakeKeycloakAdmin) -> None:
    """Test reactivating a suspended organization."""
    org_id = uuid.uuid4()
    org = Organization(
        id=org_id,
        name="ACME",
        slug="acme",
        status="suspended",
        keycloak_org_id="kc-acme",
        created_at=datetime.now(timezone.utc),
    )

    session = FakeSession()
    session.next_org = org

    app = _create_test_app(session, _test_principal(), fake_kc)
    client = TestClient(app)

    response = client.post(f"/v2/operator/orgs/{org_id}/reactivate")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "active"


def test_list_orgs(fake_kc: FakeKeycloakAdmin) -> None:
    """Test listing organizations."""
    session = FakeSession()
    now = datetime.now(timezone.utc)
    org1 = Organization(
        id=uuid.uuid4(),
        name="ACME",
        slug="acme",
        status="active",
        keycloak_org_id="kc-acme",
        created_at=now,
    )
    org2 = Organization(
        id=uuid.uuid4(),
        name="Globex",
        slug="globex",
        status="suspended",
        keycloak_org_id="kc-globex",
        created_at=now,
    )
    session.orgs[org1.id] = org1
    session.orgs[org2.id] = org2

    app = _create_test_app(session, _test_principal(), fake_kc)
    client = TestClient(app)

    response = client.get("/v2/operator/orgs")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = {org["name"] for org in data}
    assert names == {"ACME", "Globex"}
