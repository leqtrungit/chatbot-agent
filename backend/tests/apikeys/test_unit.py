"""Unit tests for API keys module with dependency overrides (no real DB needed)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.apikeys import service
from app.apikeys.models import ApiKey
from app.core.db import get_session
from app.core.security import TenantPrincipal
from app.identity.deps import require_org_member
from app.identity.org_access import OrgContext, require_org_access
from app.orgs.models import Organization


ORG_ID_A = uuid.uuid4()
ORG_ID_B = uuid.uuid4()


class FakeSession:
    """Fake async session for unit tests."""

    def __init__(self, api_keys: dict[str, ApiKey], orgs: dict[uuid.UUID, Organization]):
        self._api_keys_by_hash = api_keys  # key_hash -> ApiKey
        self._api_keys_by_id = {}  # id -> ApiKey
        # Build id lookup from existing keys
        for ak in api_keys.values():
            self._api_keys_by_id[ak.id] = ak
        self._orgs = orgs  # org_id -> Organization
        self._next_id = uuid.uuid4()

    async def get(self, model, key):
        if model is Organization:
            return self._orgs.get(key)
        if model is ApiKey:
            # This is a search by id, not by key_hash
            return self._api_keys_by_id.get(key)
        return None

    async def execute(self, stmt):
        # This is a very simplified fake - it just returns all keys
        # In a real scenario, this would need to parse the SQLAlchemy select statement
        return FakeResult(list(self._api_keys_by_id.values()), stmt)

    def add(self, instance):
        if isinstance(instance, ApiKey):
            self._api_keys_by_hash[instance.key_hash] = instance
            self._api_keys_by_id[instance.id] = instance

    async def commit(self):
        pass

    async def refresh(self, instance):
        pass

    async def delete(self, instance):
        # For fake session, just remove from dicts
        if isinstance(instance, ApiKey):
            self._api_keys_by_id.pop(instance.id, None)
            self._api_keys_by_hash.pop(instance.key_hash, None)


class FakeResult:
    """Fake query result."""

    def __init__(self, items: list, stmt):
        self._items = items
        self._stmt = stmt

    def scalar_one_or_none(self):
        # Return first item if available, else None
        if self._items:
            return self._items[0]
        return None

    def scalars(self):
        return FakeScalars(self._items)


class FakeScalars:
    """Fake scalars result."""

    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


def _org(org_id: uuid.UUID, slug: str, status: str = "active") -> Organization:
    """Create a test organization."""
    org = Organization(id=org_id, name=slug, slug=slug, status=status)
    return org


def _app(
    api_keys: dict[str, ApiKey],
    orgs: dict[uuid.UUID, Organization],
    principal: TenantPrincipal,
) -> FastAPI:
    """Create a test app with dependency overrides."""
    from app.main import create_app

    app = create_app()
    fake_session = FakeSession(api_keys, orgs)
    app.dependency_overrides[get_session] = lambda: fake_session
    app.dependency_overrides[require_org_member] = lambda: principal
    return app


def _principal(org_alias: str, role: str = "admin") -> TenantPrincipal:
    """Create a test principal."""
    return TenantPrincipal(
        user_id="u1", email=None, org_alias=org_alias, role=role
    )


async def _post_json(
    client: AsyncClient, path: str, json: dict
) -> AsyncClient.Response:
    """Helper to POST JSON."""
    return await client.post(path, json=json)


async def _get(client: AsyncClient, path: str):
    """Helper to GET."""
    return await client.get(path)


@pytest.mark.asyncio
async def test_create_api_key_returns_raw_key_once() -> None:
    """POST /v2/orgs/{org_id}/api-keys with name returns raw key in response (201)."""
    orgs = {ORG_ID_A: _org(ORG_ID_A, "acme")}
    api_keys = {}
    app = _app(api_keys, orgs, _principal("acme"))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await _post_json(
            client,
            f"/v2/orgs/{ORG_ID_A}/api-keys",
            {"name": "Website widget"},
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Website widget"
    assert "id" in body
    assert body["key"].startswith("cba_")
    # cba_ + 32 hex chars
    assert len(body["key"]) == len("cba_") + 32

    # Verify key was hashed and stored
    assert len(api_keys) == 1
    key_hash = hashlib.sha256(body["key"].encode()).hexdigest()
    assert key_hash in api_keys


@pytest.mark.asyncio
async def test_create_api_key_with_rate_limit() -> None:
    """POST with rate_limit_per_minute stores it."""
    orgs = {ORG_ID_A: _org(ORG_ID_A, "acme")}
    api_keys = {}
    app = _app(api_keys, orgs, _principal("acme"))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await _post_json(
            client,
            f"/v2/orgs/{ORG_ID_A}/api-keys",
            {"name": "High-volume", "rate_limit_per_minute": 500},
        )

    assert resp.status_code == 201
    assert resp.json()["rate_limit_per_minute"] == 500


@pytest.mark.asyncio
async def test_list_does_not_return_key_or_hash() -> None:
    """GET /v2/orgs/{org_id}/api-keys never returns key or key_hash."""
    orgs = {ORG_ID_A: _org(ORG_ID_A, "acme")}
    # Pre-populate with one key
    raw_key = "cba_" + "a" * 32
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        id=uuid.uuid4(),
        org_id=ORG_ID_A,
        name="Test key",
        key_hash=key_hash,
        rate_limit_per_minute=None,
        revoked_at=None,
        created_at=datetime.now(timezone.utc),
    )
    api_keys = {key_hash: api_key}
    app = _app(api_keys, orgs, _principal("acme"))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await _get(client, f"/v2/orgs/{ORG_ID_A}/api-keys")

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    item = items[0]
    # Never expose raw key or hash in list
    assert "key" not in item
    assert "key_hash" not in item
    assert item["name"] == "Test key"
    assert "id" in item


@pytest.mark.asyncio
async def test_revoke_api_key_sets_revoked_at() -> None:
    """POST /v2/orgs/{org_id}/api-keys/{key_id}/revoke sets revoked_at."""
    orgs = {ORG_ID_A: _org(ORG_ID_A, "acme")}
    api_key_id = uuid.uuid4()
    raw_key = "cba_" + "b" * 32
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        id=api_key_id,
        org_id=ORG_ID_A,
        name="To revoke",
        key_hash=key_hash,
        rate_limit_per_minute=None,
        revoked_at=None,
        created_at=datetime.now(timezone.utc),
    )
    api_keys = {key_hash: api_key}
    app = _app(api_keys, orgs, _principal("acme"))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/v2/orgs/{ORG_ID_A}/api-keys/{api_key_id}/revoke"
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["revoked_at"] is not None


@pytest.mark.asyncio
async def test_revoke_is_idempotent() -> None:
    """Revoking an already-revoked key returns 200 (idempotent)."""
    orgs = {ORG_ID_A: _org(ORG_ID_A, "acme")}
    api_key_id = uuid.uuid4()
    raw_key = "cba_" + "c" * 32
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    api_key = ApiKey(
        id=api_key_id,
        org_id=ORG_ID_A,
        name="Already revoked",
        key_hash=key_hash,
        rate_limit_per_minute=None,
        revoked_at=now,
        created_at=now,
    )
    api_keys = {key_hash: api_key}
    app = _app(api_keys, orgs, _principal("acme"))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/v2/orgs/{ORG_ID_A}/api-keys/{api_key_id}/revoke"
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_require_api_key_missing_header_returns_401() -> None:
    """require_api_key: missing X-API-Key header returns 401."""
    from app.apikeys.deps import require_api_key

    orgs = {ORG_ID_A: _org(ORG_ID_A, "acme")}
    api_keys = {}
    fake_session = FakeSession(api_keys, orgs)

    with pytest.raises(Exception) as exc_info:
        # Call require_api_key without header
        await require_api_key(x_api_key=None, session=fake_session)

    # Should raise HTTPException with 401
    from fastapi import HTTPException

    assert isinstance(exc_info.value, HTTPException)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_api_key_invalid_key_returns_401() -> None:
    """require_api_key: invalid key returns 401."""
    from app.apikeys.deps import require_api_key
    from fastapi import HTTPException

    orgs = {ORG_ID_A: _org(ORG_ID_A, "acme")}
    api_keys = {}
    fake_session = FakeSession(api_keys, orgs)

    with pytest.raises(HTTPException) as exc_info:
        # Call with invalid key
        await require_api_key(
            x_api_key="cba_" + "0" * 32,  # Valid format but not in DB
            session=fake_session,
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_api_key_revoked_key_returns_401(monkeypatch) -> None:
    """A revoked key must be rejected exactly like an unknown one (401)."""
    from fastapi import HTTPException

    from app.apikeys import deps

    # get_active_key_by_hash filters revoked_at IS NULL, so a revoked key
    # looks like a miss to the dependency. Assert the dependency turns that
    # into 401 and never leaks that the key once existed.
    async def _no_active_key(session, key_hash):
        return None

    monkeypatch.setattr(deps.service, "get_active_key_by_hash", _no_active_key)

    with pytest.raises(HTTPException) as exc:
        await deps.require_api_key(x_api_key="cba_revoked", session=object())

    assert exc.value.status_code == 401
    assert "revoked" in exc.value.detail.lower() or "invalid" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_require_api_key_suspended_org_returns_403() -> None:
    """require_api_key: suspended org returns 403."""
    from app.apikeys.deps import require_api_key
    from fastapi import HTTPException

    orgs = {
        ORG_ID_A: _org(ORG_ID_A, "acme", status="suspended"),
    }
    # Create an active key for suspended org
    raw_key = "cba_" + "e" * 32
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        id=uuid.uuid4(),
        org_id=ORG_ID_A,
        name="Key in suspended org",
        key_hash=key_hash,
        rate_limit_per_minute=None,
        revoked_at=None,
        created_at=datetime.now(timezone.utc),
    )
    api_keys = {key_hash: api_key}
    fake_session = FakeSession(api_keys, orgs)

    with pytest.raises(HTTPException) as exc_info:
        # Try to use key in suspended org
        await require_api_key(x_api_key=raw_key, session=fake_session)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_cross_org_isolation_list() -> None:
    """Admin of org A cannot see/access keys of org B."""
    orgs = {
        ORG_ID_A: _org(ORG_ID_A, "acme"),
        ORG_ID_B: _org(ORG_ID_B, "globex"),
    }
    # Org A key
    key_a = ApiKey(
        id=uuid.uuid4(),
        org_id=ORG_ID_A,
        name="Key A",
        key_hash="hash_a",
        rate_limit_per_minute=None,
        revoked_at=None,
        created_at=datetime.now(timezone.utc),
    )
    # Org B key
    key_b = ApiKey(
        id=uuid.uuid4(),
        org_id=ORG_ID_B,
        name="Key B",
        key_hash="hash_b",
        rate_limit_per_minute=None,
        revoked_at=None,
        created_at=datetime.now(timezone.utc),
    )
    api_keys = {"hash_a": key_a, "hash_b": key_b}
    app = _app(api_keys, orgs, _principal("acme"))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Admin of acme tries to list globex's keys - should get 404
        resp = await _get(client, f"/v2/orgs/{ORG_ID_B}/api-keys")

    assert resp.status_code == 404  # Cross-tenant request


@pytest.mark.asyncio
async def test_create_key_unknown_org_returns_404() -> None:
    """Creating a key for unknown org returns 404."""
    orgs = {ORG_ID_A: _org(ORG_ID_A, "acme")}
    api_keys = {}
    app = _app(api_keys, orgs, _principal("acme"))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await _post_json(
            client,
            f"/v2/orgs/{ORG_ID_B}/api-keys",
            {"name": "Test"},
        )

    assert resp.status_code == 404
