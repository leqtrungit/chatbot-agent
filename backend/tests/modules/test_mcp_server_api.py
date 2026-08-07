from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("db_session")


async def test_list_mcp_servers_requires_auth(client):
    resp = await client.get("/api/mcp-servers")
    assert resp.status_code == 401


async def test_create_and_list_mcp_server(client, admin_auth_header):
    resp = await client.post(
        "/api/mcp-servers",
        json={"name": "Docs Search", "url": "https://mcp.example.com/mcp", "transport": "http"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Docs Search"
    assert body["transport"] == "http"
    assert body["is_active"] is True

    resp = await client.get("/api/mcp-servers", headers=admin_auth_header)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "Docs Search"


async def test_create_mcp_server_rejects_unknown_transport(client, admin_auth_header):
    resp = await client.post(
        "/api/mcp-servers",
        json={"name": "Bad", "url": "https://x.example.com", "transport": "carrier-pigeon"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 422


async def test_create_mcp_server_with_headers(client, admin_auth_header):
    resp = await client.post(
        "/api/mcp-servers",
        json={
            "name": "Auth'd Server",
            "url": "https://mcp.example.com/sse",
            "transport": "sse",
            "headers": {"Authorization": "Bearer secret-token"},
        },
        headers=admin_auth_header,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["headers"] == {"Authorization": "Bearer secret-token"}


async def test_duplicate_name_conflicts(client, admin_auth_header):
    payload = {"name": "Dup", "url": "https://a.example.com", "transport": "http"}
    resp = await client.post("/api/mcp-servers", json=payload, headers=admin_auth_header)
    assert resp.status_code == 201

    payload["url"] = "https://b.example.com"
    resp = await client.post("/api/mcp-servers", json=payload, headers=admin_auth_header)
    assert resp.status_code == 409


async def test_get_update_delete_mcp_server(client, admin_auth_header):
    create = await client.post(
        "/api/mcp-servers",
        json={"name": "Toggle", "url": "https://c.example.com", "transport": "http"},
        headers=admin_auth_header,
    )
    server_id = create.json()["id"]

    resp = await client.get(f"/api/mcp-servers/{server_id}", headers=admin_auth_header)
    assert resp.status_code == 200

    resp = await client.put(
        f"/api/mcp-servers/{server_id}",
        json={"is_active": False},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    resp = await client.delete(f"/api/mcp-servers/{server_id}", headers=admin_auth_header)
    assert resp.status_code == 204

    resp = await client.get(f"/api/mcp-servers/{server_id}", headers=admin_auth_header)
    assert resp.status_code == 404


async def test_get_mcp_server_not_found(client, admin_auth_header):
    resp = await client.get(
        "/api/mcp-servers/00000000-0000-0000-0000-000000000000", headers=admin_auth_header
    )
    assert resp.status_code == 404
