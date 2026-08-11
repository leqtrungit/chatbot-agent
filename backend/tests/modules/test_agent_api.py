from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("db_session")


async def _create_domain(client, admin_auth_header, name="Sales"):
    resp = await client.post("/api/domains", json={"name": name}, headers=admin_auth_header)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_mcp_server(client, admin_auth_header, name="Docs"):
    resp = await client.post(
        "/api/mcp-servers",
        json={"name": name, "url": "https://mcp.example.com/mcp", "transport": "http"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_list_agents_requires_auth(client):
    resp = await client.get("/api/agents")
    assert resp.status_code == 401


async def test_create_and_list_agent(client, admin_auth_header):
    resp = await client.post(
        "/api/agents",
        json={"name": "Support Bot", "provider": "ollama", "model_name": "qwen2.5"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Support Bot"
    assert body["provider"] == "ollama"
    assert body["system_prompt"] is None
    assert body["max_iterations"] == 10
    assert body["enable_knowledge_search"] is True
    assert body["domain_ids"] == []
    assert body["mcp_server_ids"] == []

    resp = await client.get("/api/agents", headers=admin_auth_header)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_create_agent_rejects_unknown_provider(client, admin_auth_header):
    resp = await client.post(
        "/api/agents",
        json={"name": "Bad", "provider": "gpt4chan", "model_name": "x"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 422


async def test_create_agent_without_system_prompt_defaults_to_none(client, admin_auth_header):
    resp = await client.post(
        "/api/agents",
        json={"name": "No Prompt Bot", "provider": "ollama", "model_name": "x"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["system_prompt"] is None


async def test_create_agent_with_custom_system_prompt_roundtrips_verbatim(client, admin_auth_header):
    custom_prompt = "You are a pirate. Answer every question in pirate speak."
    resp = await client.post(
        "/api/agents",
        json={
            "name": "Pirate Bot",
            "provider": "ollama",
            "model_name": "x",
            "system_prompt": custom_prompt,
        },
        headers=admin_auth_header,
    )
    assert resp.status_code == 201, resp.text
    agent_id = resp.json()["id"]
    assert resp.json()["system_prompt"] == custom_prompt

    resp = await client.get(f"/api/agents/{agent_id}", headers=admin_auth_header)
    assert resp.status_code == 200
    assert resp.json()["system_prompt"] == custom_prompt


async def test_create_agent_with_domains_and_mcp_servers(client, admin_auth_header):
    domain_id = await _create_domain(client, admin_auth_header)
    server_id = await _create_mcp_server(client, admin_auth_header)

    resp = await client.post(
        "/api/agents",
        json={
            "name": "Wired Bot",
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "api_key": "sk-test",
            "domain_ids": [domain_id],
            "mcp_server_ids": [server_id],
        },
        headers=admin_auth_header,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["domain_ids"] == [domain_id]
    assert body["mcp_server_ids"] == [server_id]
    # api_key is write-only, never echoed back
    assert "api_key" not in body


async def test_create_agent_rejects_unknown_domain_id(client, admin_auth_header):
    resp = await client.post(
        "/api/agents",
        json={
            "name": "Orphan",
            "provider": "ollama",
            "model_name": "x",
            "domain_ids": ["00000000-0000-0000-0000-000000000000"],
        },
        headers=admin_auth_header,
    )
    assert resp.status_code == 422


async def test_duplicate_agent_name_conflicts(client, admin_auth_header):
    payload = {"name": "Dup", "provider": "ollama", "model_name": "x"}
    resp = await client.post("/api/agents", json=payload, headers=admin_auth_header)
    assert resp.status_code == 201
    resp = await client.post("/api/agents", json=payload, headers=admin_auth_header)
    assert resp.status_code == 409


async def test_get_update_delete_agent(client, admin_auth_header):
    create = await client.post(
        "/api/agents",
        json={"name": "Toggle Bot", "provider": "ollama", "model_name": "x"},
        headers=admin_auth_header,
    )
    agent_id = create.json()["id"]

    resp = await client.get(f"/api/agents/{agent_id}", headers=admin_auth_header)
    assert resp.status_code == 200

    resp = await client.put(
        f"/api/agents/{agent_id}",
        json={"is_active": False, "temperature": 0.2},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    assert resp.json()["temperature"] == 0.2

    resp = await client.delete(f"/api/agents/{agent_id}", headers=admin_auth_header)
    assert resp.status_code == 204

    # Delete is a soft delete (is_active=False) — the row (and its history) stays
    # visible to admins, matching ApiKey's revoked_at pattern.
    resp = await client.get(f"/api/agents/{agent_id}", headers=admin_auth_header)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


async def test_get_agent_not_found(client, admin_auth_header):
    resp = await client.get(
        "/api/agents/00000000-0000-0000-0000-000000000000", headers=admin_auth_header
    )
    assert resp.status_code == 404


async def test_set_agent_domains_endpoint(client, admin_auth_header):
    domain_a = await _create_domain(client, admin_auth_header, "A")
    domain_b = await _create_domain(client, admin_auth_header, "B")
    create = await client.post(
        "/api/agents",
        json={"name": "Multi Domain Bot", "provider": "ollama", "model_name": "x", "domain_ids": [domain_a]},
        headers=admin_auth_header,
    )
    agent_id = create.json()["id"]

    resp = await client.put(
        f"/api/agents/{agent_id}/domains",
        json={"domain_ids": [domain_a, domain_b]},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert sorted(resp.json()["domain_ids"]) == sorted([domain_a, domain_b])

    resp = await client.put(
        f"/api/agents/{agent_id}/domains",
        json={"domain_ids": []},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["domain_ids"] == []


async def test_set_domain_agents_endpoint(client, admin_auth_header):
    domain_id = await _create_domain(client, admin_auth_header)
    agent_a = (
        await client.post(
            "/api/agents",
            json={"name": "Agent A", "provider": "ollama", "model_name": "x"},
            headers=admin_auth_header,
        )
    ).json()["id"]
    agent_b = (
        await client.post(
            "/api/agents",
            json={"name": "Agent B", "provider": "ollama", "model_name": "x"},
            headers=admin_auth_header,
        )
    ).json()["id"]

    resp = await client.put(
        f"/api/domains/{domain_id}/agents",
        json={"agent_ids": [agent_a, agent_b]},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200, resp.text
    assert sorted(resp.json()["agent_ids"]) == sorted([agent_a, agent_b])

    domain = (await client.get(f"/api/domains/{domain_id}", headers=admin_auth_header)).json()
    assert sorted(domain["agent_ids"]) == sorted([agent_a, agent_b])
