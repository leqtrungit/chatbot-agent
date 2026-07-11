from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select

from app.modules.apikey.models import ApiKey

pytestmark = pytest.mark.usefixtures("db_session")


async def test_create_requires_auth(client):
    resp = await client.post("/api/api-keys", json={"name": "Website widget"})
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Basic"


async def test_list_requires_auth(client):
    resp = await client.get("/api/api-keys")
    assert resp.status_code == 401


async def test_create_returns_plaintext_key_once(client, admin_auth_header, session_maker):
    resp = await client.post(
        "/api/api-keys",
        json={"name": "Website widget"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Website widget"
    assert "id" in body
    assert body["key"].startswith("cba_")
    # cba_ + 32 hex chars
    assert len(body["key"]) == len("cba_") + 32

    # DB stores only the hash, never the plaintext key.
    async with session_maker() as session:
        result = await session.execute(select(ApiKey))
        rows = result.scalars().all()
    assert len(rows) == 1
    stored = rows[0]
    assert stored.key_hash == hashlib.sha256(body["key"].encode()).hexdigest()
    assert stored.key_prefix == body["key"][:8]
    # never store the raw key itself anywhere on the row
    for value in (stored.key_hash, stored.key_prefix):
        assert value != body["key"]


async def test_create_with_custom_rate_limit(client, admin_auth_header):
    resp = await client.post(
        "/api/api-keys",
        json={"name": "High-volume app", "rate_limit_per_minute": 500},
        headers=admin_auth_header,
    )
    assert resp.status_code == 201, resp.text

    list_resp = await client.get("/api/api-keys", headers=admin_auth_header)
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["rate_limit_per_minute"] == 500
    assert "key" not in items[0]
    assert "key_hash" not in items[0]


async def test_list_does_not_leak_raw_key(client, admin_auth_header):
    create_resp = await client.post(
        "/api/api-keys", json={"name": "App A"}, headers=admin_auth_header
    )
    raw_key = create_resp.json()["key"]

    list_resp = await client.get("/api/api-keys", headers=admin_auth_header)
    assert list_resp.status_code == 200
    assert raw_key not in list_resp.text
    item = list_resp.json()[0]
    assert item["key_prefix"] == raw_key[:8]
    assert item["revoked_at"] is None


async def test_revoke_sets_revoked_at(client, admin_auth_header):
    create_resp = await client.post(
        "/api/api-keys", json={"name": "App to revoke"}, headers=admin_auth_header
    )
    api_key_id = create_resp.json()["id"]

    revoke_resp = await client.post(
        f"/api/api-keys/{api_key_id}/revoke", headers=admin_auth_header
    )
    assert revoke_resp.status_code == 200, revoke_resp.text
    assert revoke_resp.json()["revoked_at"] is not None

    list_resp = await client.get("/api/api-keys", headers=admin_auth_header)
    item = next(i for i in list_resp.json() if i["id"] == api_key_id)
    assert item["revoked_at"] is not None


async def test_revoke_unknown_id_returns_404(client, admin_auth_header):
    resp = await client.post(
        "/api/api-keys/00000000-0000-0000-0000-000000000000/revoke",
        headers=admin_auth_header,
    )
    assert resp.status_code == 404


async def test_revoke_requires_auth(client, admin_auth_header):
    create_resp = await client.post(
        "/api/api-keys", json={"name": "App"}, headers=admin_auth_header
    )
    api_key_id = create_resp.json()["id"]

    resp = await client.post(f"/api/api-keys/{api_key_id}/revoke")
    assert resp.status_code == 401
