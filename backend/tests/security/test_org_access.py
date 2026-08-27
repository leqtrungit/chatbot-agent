"""require_org_access: path org vs token org binding (no real DB needed)."""

from __future__ import annotations

import uuid

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.identity.deps import require_org_member
from app.identity.org_access import OrgContext, require_org_access
from app.core.security import TenantPrincipal
from app.orgs.models import Organization

ORG_ID = uuid.uuid4()
OTHER_ORG_ID = uuid.uuid4()


class _FakeSession:
    def __init__(self, orgs: dict[uuid.UUID, Organization]):
        self._orgs = orgs

    async def get(self, model, key):
        assert model is Organization
        return self._orgs.get(key)


def _org(org_id: uuid.UUID, slug: str, status: str = "active") -> Organization:
    org = Organization(id=org_id, name=slug, slug=slug, status=status)
    return org


def _app(orgs: dict[uuid.UUID, Organization], principal: TenantPrincipal) -> FastAPI:
    app = FastAPI()

    @app.get("/v2/orgs/{org_id}/probe")
    async def probe(ctx: OrgContext = Depends(require_org_access)) -> dict:
        return {"org": str(ctx.org.id), "user": ctx.principal.user_id}

    app.dependency_overrides[get_session] = lambda: _FakeSession(orgs)
    app.dependency_overrides[require_org_member] = lambda: principal
    return app


def _principal(alias: str) -> TenantPrincipal:
    return TenantPrincipal(user_id="u1", email=None, org_alias=alias, role="admin")


async def _get(app: FastAPI, org_id: uuid.UUID):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.get(f"/v2/orgs/{org_id}/probe")


@pytest.mark.asyncio
async def test_own_active_org_passes() -> None:
    app = _app({ORG_ID: _org(ORG_ID, "acme")}, _principal("acme"))
    resp = await _get(app, ORG_ID)
    assert resp.status_code == 200
    assert resp.json()["org"] == str(ORG_ID)


@pytest.mark.asyncio
async def test_unknown_org_is_404() -> None:
    app = _app({}, _principal("acme"))
    assert (await _get(app, ORG_ID)).status_code == 404


@pytest.mark.asyncio
async def test_someone_elses_org_is_404_not_403() -> None:
    orgs = {
        ORG_ID: _org(ORG_ID, "acme"),
        OTHER_ORG_ID: _org(OTHER_ORG_ID, "globex"),
    }
    app = _app(orgs, _principal("acme"))
    resp = await _get(app, OTHER_ORG_ID)
    assert resp.status_code == 404  # indistinguishable from nonexistent


@pytest.mark.asyncio
async def test_suspended_org_is_403() -> None:
    app = _app({ORG_ID: _org(ORG_ID, "acme", status="suspended")}, _principal("acme"))
    assert (await _get(app, ORG_ID)).status_code == 403
