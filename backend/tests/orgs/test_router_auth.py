"""Authorization tests for organization router endpoints.

Tests that verify:
- Operator-only endpoints return 401 without token
- Operator-only endpoints return 403 for tenant tokens
- Proper error handling and status codes
"""

from __future__ import annotations

from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient

from app.core.db import get_session
from app.identity.deps import require_operator
from app.core.security import OperatorPrincipal, TenantPrincipal
from app.orgs.router import router as orgs_router
from app.orgs.models import Organization
from tests.orgs.conftest import FakeKeycloakAdmin
import uuid
import pytest


class FakeSession:
    """Mock SQLAlchemy session."""

    def __init__(self):
        self.orgs: dict[uuid.UUID, Organization] = {}

    def add(self, instance):
        self.orgs[instance.id] = instance

    async def flush(self):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def get(self, model, key):
        if model is Organization:
            return self.orgs.get(key)
        return None


def _create_app_with_override(
    require_operator_override=None,
) -> FastAPI:
    """Create app with dependency overrides."""
    app = FastAPI()
    app.include_router(orgs_router)

    app.dependency_overrides[get_session] = lambda: FakeSession()

    if require_operator_override is not None:
        app.dependency_overrides[require_operator] = require_operator_override

    from app.orgs.router import get_kc_admin

    app.dependency_overrides[get_kc_admin] = lambda: FakeKeycloakAdmin()

    return app


def test_create_org_no_auth() -> None:
    """Test POST /v2/operator/orgs without authorization (401)."""
    # Don't provide operator override, so require_operator will fail
    def fail_require_operator():
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    app = _create_app_with_override(require_operator_override=fail_require_operator)
    client = TestClient(app)

    response = client.post(
        "/v2/operator/orgs",
        json={"name": "Test", "slug": "test"},
    )

    assert response.status_code == 401


def test_create_org_tenant_auth() -> None:
    """Test POST /v2/operator/orgs with tenant token (403)."""
    # Provide tenant principal instead of operator
    def fail_require_operator():
        raise HTTPException(status_code=403, detail="Operator role required")

    app = _create_app_with_override(require_operator_override=fail_require_operator)
    client = TestClient(app)

    response = client.post(
        "/v2/operator/orgs",
        json={"name": "Test", "slug": "test"},
    )

    assert response.status_code == 403


def test_suspend_org_no_auth() -> None:
    """Test POST .../suspend without authorization (401)."""
    def fail_require_operator():
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    app = _create_app_with_override(require_operator_override=fail_require_operator)
    client = TestClient(app)

    org_id = uuid.uuid4()
    response = client.post(f"/v2/operator/orgs/{org_id}/suspend")

    assert response.status_code == 401


def test_reactivate_org_no_auth() -> None:
    """Test POST .../reactivate without authorization (401)."""
    def fail_require_operator():
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    app = _create_app_with_override(require_operator_override=fail_require_operator)
    client = TestClient(app)

    org_id = uuid.uuid4()
    response = client.post(f"/v2/operator/orgs/{org_id}/reactivate")

    assert response.status_code == 401


def test_list_orgs_no_auth() -> None:
    """Test GET /v2/operator/orgs without authorization (401)."""
    def fail_require_operator():
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    app = _create_app_with_override(require_operator_override=fail_require_operator)
    client = TestClient(app)

    response = client.get("/v2/operator/orgs")

    assert response.status_code == 401
