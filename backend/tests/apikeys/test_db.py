"""DB-backed integration tests for API keys (cross-org isolation - NFR-SEC1)."""

from __future__ import annotations

import hashlib
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.apikeys.models import ApiKey
from app.core.db import get_session
from app.core.security import TenantPrincipal
from app.identity.deps import require_org_member
from app.main import create_app
from app.orgs.models import Organization


pytestmark = pytest.mark.asyncio


async def _create_org(session: AsyncSession, name: str, slug: str) -> Organization:
    """Create an organization in the test database."""
    org = Organization(id=uuid.uuid4(), name=name, slug=slug, status="active")
    session.add(org)
    await session.commit()
    await session.refresh(org)
    return org


async def _create_api_key(
    session: AsyncSession,
    org_id: uuid.UUID,
    name: str,
    rate_limit_per_minute: int | None = None,
) -> tuple[ApiKey, str]:
    """Create an API key in the test database."""
    from app.apikeys import service

    raw_key = service.generate_raw_key()
    key_hash = service.hash_key(raw_key)
    api_key = ApiKey(
        id=uuid.uuid4(),
        org_id=org_id,
        name=name,
        key_hash=key_hash,
        rate_limit_per_minute=rate_limit_per_minute,
        revoked_at=None,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return api_key, raw_key


def _make_app(
    db_session: AsyncSession, principal: TenantPrincipal
) -> FastAPI:
    """Create app with DB session and principal overrides."""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[require_org_member] = lambda: principal
    return app


async def test_admin_org_a_cannot_list_keys_in_org_b(
    db_session: AsyncSession
) -> None:
    """Admin of org A requesting /v2/orgs/{org_b_id}/api-keys gets 404."""
    # Create two orgs
    org_a = await _create_org(db_session, "ACME", "acme")
    org_b = await _create_org(db_session, "Globex", "globex")

    # Create a key in org B
    await _create_api_key(db_session, org_b.id, "Key in B")

    # Create app with admin principal for org A
    principal_a = TenantPrincipal(
        user_id="admin_a", email=None, org_alias="acme", role="admin"
    )
    app = _make_app(db_session, principal_a)

    # Try to list keys in org B (should get 404)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(f"/v2/orgs/{org_b.id}/api-keys")

    assert resp.status_code == 404


async def test_admin_org_a_cannot_revoke_key_in_org_b(
    db_session: AsyncSession
) -> None:
    """Admin of org A cannot revoke a key in org B (404)."""
    # Create two orgs
    org_a = await _create_org(db_session, "ACME", "acme")
    org_b = await _create_org(db_session, "Globex", "globex")

    # Create a key in org B
    key_b, _ = await _create_api_key(db_session, org_b.id, "Key in B")

    # Create app with admin principal for org A
    principal_a = TenantPrincipal(
        user_id="admin_a", email=None, org_alias="acme", role="admin"
    )
    app = _make_app(db_session, principal_a)

    # Try to revoke key in org B (should get 404)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(f"/v2/orgs/{org_b.id}/api-keys/{key_b.id}/revoke")

    assert resp.status_code == 404


async def test_create_key_in_org_a_admin_org_a_can_list_it(
    db_session: AsyncSession
) -> None:
    """Admin of org A can create and list keys in org A."""
    # Create org A
    org_a = await _create_org(db_session, "ACME", "acme")

    # Create app with admin principal for org A
    principal_a = TenantPrincipal(
        user_id="admin_a", email=None, org_alias="acme", role="admin"
    )
    app = _make_app(db_session, principal_a)

    # Create a key
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/v2/orgs/{org_a.id}/api-keys",
            json={"name": "Widget"},
        )

    assert resp.status_code == 201
    key_data = resp.json()
    assert key_data["name"] == "Widget"
    raw_key = key_data["key"]

    # List keys should show it (without exposing the raw key)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(f"/v2/orgs/{org_a.id}/api-keys")

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "Widget"
    assert "key" not in items[0]
    assert "key_hash" not in items[0]


async def test_suspended_org_blocks_access(
    db_session: AsyncSession
) -> None:
    """Requests to a suspended org return 403."""
    # Create org and immediately suspend it
    org = await _create_org(db_session, "Suspended", "suspended")
    org.status = "suspended"
    await db_session.merge(org)
    await db_session.commit()

    # Create app with principal for that org
    principal = TenantPrincipal(
        user_id="admin", email=None, org_alias="suspended", role="admin"
    )
    app = _make_app(db_session, principal)

    # Try to access - should get 403
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(f"/v2/orgs/{org.id}/api-keys")

    assert resp.status_code == 403
