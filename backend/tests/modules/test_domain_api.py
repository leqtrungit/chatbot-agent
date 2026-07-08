from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("db_session")


async def test_list_domains_requires_auth(client):
    resp = await client.get("/api/domains")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Basic"


async def test_create_and_list_domain(client, admin_auth_header):
    resp = await client.post(
        "/api/domains",
        json={"name": "HR Policies"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "HR Policies"
    assert body["slug"] == "hr-policies"
    assert "id" in body

    resp = await client.get("/api/domains", headers=admin_auth_header)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "HR Policies"


async def test_create_domain_with_explicit_slug(client, admin_auth_header):
    resp = await client.post(
        "/api/domains",
        json={"name": "Sales", "slug": "custom-slug"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 201
    assert resp.json()["slug"] == "custom-slug"


async def test_get_domain_by_id(client, admin_auth_header):
    create = await client.post(
        "/api/domains", json={"name": "Legal"}, headers=admin_auth_header
    )
    domain_id = create.json()["id"]

    resp = await client.get(f"/api/domains/{domain_id}", headers=admin_auth_header)
    assert resp.status_code == 200
    assert resp.json()["id"] == domain_id


async def test_get_domain_not_found(client, admin_auth_header):
    resp = await client.get(
        "/api/domains/00000000-0000-0000-0000-000000000000", headers=admin_auth_header
    )
    assert resp.status_code == 404


async def test_update_domain(client, admin_auth_header):
    create = await client.post(
        "/api/domains", json={"name": "Finance"}, headers=admin_auth_header
    )
    domain_id = create.json()["id"]

    resp = await client.put(
        f"/api/domains/{domain_id}",
        json={"description": "Finance docs"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Finance docs"
    assert resp.json()["name"] == "Finance"


async def test_delete_domain(client, admin_auth_header):
    create = await client.post(
        "/api/domains", json={"name": "Temp"}, headers=admin_auth_header
    )
    domain_id = create.json()["id"]

    resp = await client.delete(f"/api/domains/{domain_id}", headers=admin_auth_header)
    assert resp.status_code == 204

    resp = await client.get(f"/api/domains/{domain_id}", headers=admin_auth_header)
    assert resp.status_code == 404


async def test_duplicate_name_conflict(client, admin_auth_header):
    await client.post("/api/domains", json={"name": "Dup"}, headers=admin_auth_header)
    resp = await client.post("/api/domains", json={"name": "Dup"}, headers=admin_auth_header)
    assert resp.status_code == 409


async def test_duplicate_slug_conflict(client, admin_auth_header):
    await client.post(
        "/api/domains", json={"name": "One", "slug": "same-slug"}, headers=admin_auth_header
    )
    resp = await client.post(
        "/api/domains", json={"name": "Two", "slug": "same-slug"}, headers=admin_auth_header
    )
    assert resp.status_code == 409
