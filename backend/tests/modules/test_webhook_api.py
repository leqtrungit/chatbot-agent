from __future__ import annotations

import pytest


async def _create_domain(client, admin_auth_header, name="Support"):
    resp = await client.post("/api/domains", json={"name": name}, headers=admin_auth_header)
    assert resp.status_code == 201
    return resp.json()


async def test_unknown_platform_returns_404(client):
    resp = await client.post(
        "/api/webhooks/nonexistent", json={"domain_id": "d", "message": "hi"}
    )
    assert resp.status_code == 404


async def test_invalid_payload_returns_422(client, admin_auth_header):
    domain = await _create_domain(client, admin_auth_header)
    resp = await client.post(
        "/api/webhooks/generic", json={"domain_id": domain["id"]}  # missing "message"
    )
    assert resp.status_code == 422


async def test_unknown_domain_returns_404(client):
    resp = await client.post(
        "/api/webhooks/generic",
        json={"domain_id": "00000000-0000-0000-0000-000000000000", "message": "hi"},
    )
    assert resp.status_code == 404


async def test_happy_path_enqueues_and_returns_202(client, admin_auth_header, monkeypatch):
    domain = await _create_domain(client, admin_auth_header)

    calls: list[dict] = []

    async def _fake_enqueue(**kwargs) -> str:
        calls.append(kwargs)
        return "job-123"

    monkeypatch.setattr("app.modules.webhook.jobs.enqueue_chat_job", _fake_enqueue)

    resp = await client.post(
        "/api/webhooks/generic",
        json={"domain_id": domain["id"], "session_id": "sess-1", "message": "hello there"},
    )
    assert resp.status_code == 202, resp.text
    assert resp.json() == {"job_id": "job-123"}
    assert len(calls) == 1
    assert calls[0] == {
        "domain_id": domain["id"],
        "session_id": "sess-1",
        "text": "hello there",
        "metadata": {},
        "platform": "generic",
    }


async def test_happy_path_by_slug(client, admin_auth_header, monkeypatch):
    domain = await _create_domain(client, admin_auth_header, name="By Slug Domain")

    async def _fake_enqueue(**kwargs) -> str:
        return "job-xyz"

    monkeypatch.setattr("app.modules.webhook.jobs.enqueue_chat_job", _fake_enqueue)

    resp = await client.post(
        "/api/webhooks/generic",
        json={"domain_id": domain["slug"], "message": "hi"},
    )
    assert resp.status_code == 202
    assert resp.json() == {"job_id": "job-xyz"}


@pytest.mark.parametrize(
    "fake_status, expected_status, expected_result",
    [
        ({"job_id": "j1", "status": "queued", "result": None}, "queued", None),
        ({"job_id": "j1", "status": "in_progress", "result": None}, "in_progress", None),
        (
            {"job_id": "j1", "status": "complete", "result": {"reply": "hi"}},
            "complete",
            {"reply": "hi"},
        ),
        (
            {"job_id": "j1", "status": "failed", "result": {"error": "boom"}},
            "failed",
            {"error": "boom"},
        ),
    ],
)
async def test_job_status_mapping(client, monkeypatch, fake_status, expected_status, expected_result):
    async def _fake_get_job_status(job_id: str) -> dict:
        return fake_status

    monkeypatch.setattr("app.modules.webhook.jobs.get_job_status", _fake_get_job_status)

    resp = await client.get("/api/jobs/j1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == expected_status
    assert body["result"] == expected_result


async def test_job_status_not_found_returns_404(client, monkeypatch):
    async def _fake_get_job_status(job_id: str) -> dict:
        return {"job_id": job_id, "status": "not_found", "result": None}

    monkeypatch.setattr("app.modules.webhook.jobs.get_job_status", _fake_get_job_status)

    resp = await client.get("/api/jobs/missing")
    assert resp.status_code == 404
