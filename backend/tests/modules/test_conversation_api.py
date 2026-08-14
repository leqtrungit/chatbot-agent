from __future__ import annotations

import uuid

import pytest

from app.modules.conversation import service as conversation_service

pytestmark = pytest.mark.usefixtures("db_session")


async def _create_domain(client, admin_auth_header, name="Support"):
    resp = await client.post("/api/domains", json={"name": name}, headers=admin_auth_header)
    assert resp.status_code == 201
    return resp.json()


async def _create_agent(client, admin_auth_header, domain_id, *, name="Test Agent"):
    resp = await client.post(
        "/api/agents",
        json={"name": name, "provider": "ollama", "model_name": "qwen2.5", "domain_ids": [domain_id]},
        headers=admin_auth_header,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_api_key(client, admin_auth_header, *, name="Test App"):
    resp = await client.post("/api/api-keys", json={"name": name}, headers=admin_auth_header)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_returns_empty_list_when_no_messages(client, admin_auth_header, api_key_header):
    domain = await _create_domain(client, admin_auth_header)
    agent = await _create_agent(client, admin_auth_header, domain["id"])

    resp = await client.get(
        f"/api/conversations/{agent['id']}/some-session/messages",
        headers=api_key_header,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"messages": []}


async def test_returns_messages_in_chronological_order(
    client, admin_auth_header, api_key_header, db_session
):
    domain = await _create_domain(client, admin_auth_header)
    agent = await _create_agent(client, admin_auth_header, domain["id"])
    agent_uuid = uuid.UUID(agent["id"])

    await conversation_service.append_turn(
        db_session, agent_uuid, "sess-1", "hello", "hi there"
    )
    await conversation_service.append_turn(
        db_session, agent_uuid, "sess-1", "how are you", "great, thanks"
    )

    resp = await client.get(
        f"/api/conversations/{agent['id']}/sess-1/messages",
        headers=api_key_header,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    roles_and_content = [(m["role"], m["content"]) for m in body["messages"]]
    assert roles_and_content == [
        ("user", "hello"),
        ("assistant", "hi there"),
        ("user", "how are you"),
        ("assistant", "great, thanks"),
    ]


async def test_returns_citations_for_assistant_message_and_null_for_user(
    client, admin_auth_header, api_key_header, db_session
):
    domain = await _create_domain(client, admin_auth_header)
    agent = await _create_agent(client, admin_auth_header, domain["id"])
    agent_uuid = uuid.UUID(agent["id"])

    citations = [
        {
            "marker": 1,
            "source_id": "doc-1:0",
            "title": "handbook.pdf",
            "snippet": "We are open 9-5.",
            "score": 0.9,
            "metadata": {"document_id": "doc-1", "chunk_index": 0, "filename": "handbook.pdf"},
        }
    ]
    await conversation_service.append_turn(
        db_session,
        agent_uuid,
        "sess-cit",
        "What are your hours?",
        "We are open 9-5. [1]",
        citations=citations,
    )

    resp = await client.get(
        f"/api/conversations/{agent['id']}/sess-cit/messages",
        headers=api_key_header,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["messages"]) == 2
    user_msg, assistant_msg = body["messages"]
    assert user_msg["role"] == "user"
    assert user_msg["citations"] is None
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["citations"] == citations


async def test_only_returns_messages_for_requested_session(
    client, admin_auth_header, api_key_header, db_session
):
    domain = await _create_domain(client, admin_auth_header)
    agent = await _create_agent(client, admin_auth_header, domain["id"])
    agent_uuid = uuid.UUID(agent["id"])

    await conversation_service.append_turn(db_session, agent_uuid, "sess-a", "hi", "hello")
    await conversation_service.append_turn(db_session, agent_uuid, "sess-b", "yo", "hey")

    resp = await client.get(
        f"/api/conversations/{agent['id']}/sess-a/messages",
        headers=api_key_header,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["messages"]) == 2
    assert all(m["content"] in ("hi", "hello") for m in body["messages"])


async def test_limit_query_param_is_respected(
    client, admin_auth_header, api_key_header, db_session
):
    domain = await _create_domain(client, admin_auth_header)
    agent = await _create_agent(client, admin_auth_header, domain["id"])
    agent_uuid = uuid.UUID(agent["id"])

    for i in range(3):
        await conversation_service.append_turn(
            db_session, agent_uuid, "sess-1", f"msg-{i}", f"reply-{i}"
        )

    resp = await client.get(
        f"/api/conversations/{agent['id']}/sess-1/messages",
        params={"limit": 2},
        headers=api_key_header,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["messages"]) == 2
    # Most recent turn only, in chronological order.
    assert [m["content"] for m in body["messages"]] == ["msg-2", "reply-2"]


async def test_unknown_agent_returns_404(client, admin_auth_header, api_key_header):
    resp = await client.get(
        "/api/conversations/00000000-0000-0000-0000-000000000000/sess-1/messages",
        headers=api_key_header,
    )
    assert resp.status_code == 404


async def test_invalid_agent_id_returns_404(client, admin_auth_header, api_key_header):
    resp = await client.get(
        "/api/conversations/not-a-uuid/sess-1/messages",
        headers=api_key_header,
    )
    assert resp.status_code == 404


async def test_missing_api_key_returns_401(client, admin_auth_header):
    resp = await client.get(
        "/api/conversations/00000000-0000-0000-0000-000000000000/sess-1/messages",
    )
    assert resp.status_code == 401


async def test_revoked_api_key_returns_401(client, admin_auth_header):
    key = await _create_api_key(client, admin_auth_header)
    revoke_resp = await client.post(f"/api/api-keys/{key['id']}/revoke", headers=admin_auth_header)
    assert revoke_resp.status_code == 200

    resp = await client.get(
        "/api/conversations/00000000-0000-0000-0000-000000000000/sess-1/messages",
        headers={"X-API-Key": key["key"]},
    )
    assert resp.status_code == 401
