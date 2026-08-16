from __future__ import annotations

from types import SimpleNamespace

import pytest

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


async def _create_api_key(client, admin_auth_header, *, name="Test App", rate_limit_per_minute=None):
    payload: dict = {"name": name}
    if rate_limit_per_minute is not None:
        payload["rate_limit_per_minute"] = rate_limit_per_minute
    resp = await client.post("/api/api-keys", json=payload, headers=admin_auth_header)
    assert resp.status_code == 201, resp.text
    return resp.json()


class FakeRedis:
    """Minimal in-memory stand-in for the arq/redis pool, just enough for
    ``app.core.ratelimit.check_rate_limit`` (INCR + EXPIRE + TTL)."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        return None

    async def ttl(self, key: str) -> int:
        return 60


def _patch_enqueue(monkeypatch):
    calls: list[dict] = []

    async def _fake_enqueue(**kwargs) -> str:
        calls.append(kwargs)
        return "job-123"

    monkeypatch.setattr("app.modules.webhook.jobs.enqueue_chat_job", _fake_enqueue)
    return calls


def _patch_fake_redis(monkeypatch) -> FakeRedis:
    fake_redis = FakeRedis()

    async def _fake_get_arq_pool():
        return fake_redis

    monkeypatch.setattr("app.modules.webhook.jobs.get_arq_pool", _fake_get_arq_pool)
    return fake_redis


# ---- Unknown platform / bad payload / unknown agent (still require auth) ----


async def test_unknown_platform_returns_404(client, admin_auth_header, api_key_header):
    resp = await client.post(
        "/api/webhooks/nonexistent",
        json={"agent_id": "a", "message": "hi"},
        headers=api_key_header,
    )
    assert resp.status_code == 404


async def test_invalid_payload_returns_422(client, admin_auth_header, api_key_header):
    resp = await client.post(
        "/api/webhooks/generic",
        json={"agent_id": "a"},  # missing "message"
        headers=api_key_header,
    )
    assert resp.status_code == 422


async def test_unknown_agent_returns_404(client, admin_auth_header, api_key_header):
    resp = await client.post(
        "/api/webhooks/generic",
        json={
            "agent_id": "00000000-0000-0000-0000-000000000000",
            "message": "hi",
        },
        headers=api_key_header,
    )
    assert resp.status_code == 404


async def test_inactive_agent_returns_404(client, admin_auth_header, api_key_header):
    domain = await _create_domain(client, admin_auth_header)
    agent = await _create_agent(client, admin_auth_header, domain["id"])
    deactivate = await client.put(
        f"/api/agents/{agent['id']}", json={"is_active": False}, headers=admin_auth_header
    )
    assert deactivate.status_code == 200

    resp = await client.post(
        "/api/webhooks/generic",
        json={"agent_id": agent["id"], "message": "hi"},
        headers=api_key_header,
    )
    assert resp.status_code == 404


# ---- API key auth ----


async def test_missing_api_key_returns_401(client, admin_auth_header):
    resp = await client.post(
        "/api/webhooks/generic",
        json={"agent_id": "a", "message": "hi"},
    )
    assert resp.status_code == 401


async def test_invalid_api_key_returns_401(client, admin_auth_header):
    resp = await client.post(
        "/api/webhooks/generic",
        json={"agent_id": "a", "message": "hi"},
        headers={"X-API-Key": "cba_not-a-real-key"},
    )
    assert resp.status_code == 401


async def test_revoked_api_key_returns_401(client, admin_auth_header):
    key = await _create_api_key(client, admin_auth_header)
    revoke_resp = await client.post(
        f"/api/api-keys/{key['id']}/revoke", headers=admin_auth_header
    )
    assert revoke_resp.status_code == 200

    resp = await client.post(
        "/api/webhooks/generic",
        json={"agent_id": "a", "message": "hi"},
        headers={"X-API-Key": key["key"]},
    )
    assert resp.status_code == 401


async def test_job_status_requires_api_key(client, monkeypatch):
    async def _fake_get_job_status(job_id: str) -> dict:
        return {"job_id": job_id, "status": "queued", "result": None}

    monkeypatch.setattr("app.modules.webhook.jobs.get_job_status", _fake_get_job_status)

    resp = await client.get("/api/jobs/j1")
    assert resp.status_code == 401


# ---- Happy path (metadata carries the calling app's identity) ----


async def test_happy_path_enqueues_and_returns_202(client, admin_auth_header, api_key_header, monkeypatch):
    domain = await _create_domain(client, admin_auth_header)
    agent = await _create_agent(client, admin_auth_header, domain["id"])
    calls = _patch_enqueue(monkeypatch)

    resp = await client.post(
        "/api/webhooks/generic",
        json={
            "agent_id": agent["id"],
            "session_id": "sess-1",
            "message": "hello there",
        },
        headers=api_key_header,
    )
    assert resp.status_code == 202, resp.text
    assert resp.json() == {"job_id": "job-123"}
    assert len(calls) == 1
    assert calls[0]["agent_id"] == agent["id"]
    assert calls[0]["session_id"] == "sess-1"
    assert calls[0]["text"] == "hello there"
    assert calls[0]["platform"] == "generic"
    assert "app_id" in calls[0]["metadata"]
    assert "app_name" in calls[0]["metadata"]
    assert calls[0]["metadata"]["app_name"] == "Test App"


async def test_history_absent_passes_none(client, admin_auth_header, api_key_header, monkeypatch):
    domain = await _create_domain(client, admin_auth_header)
    agent = await _create_agent(client, admin_auth_header, domain["id"])
    calls = _patch_enqueue(monkeypatch)

    resp = await client.post(
        "/api/webhooks/generic",
        json={"agent_id": agent["id"], "session_id": "sess-1", "message": "hello there"},
        headers=api_key_header,
    )
    assert resp.status_code == 202, resp.text
    assert calls[0]["history"] is None


async def test_history_present_threaded_to_job_as_plain_dicts(
    client, admin_auth_header, api_key_header, monkeypatch
):
    domain = await _create_domain(client, admin_auth_header)
    agent = await _create_agent(client, admin_auth_header, domain["id"])
    calls = _patch_enqueue(monkeypatch)

    resp = await client.post(
        "/api/webhooks/generic",
        json={
            "agent_id": agent["id"],
            "session_id": "sess-1",
            "message": "hello there",
            "history": [
                {"role": "user", "content": "Earlier question"},
                {"role": "assistant", "content": "Earlier answer"},
            ],
        },
        headers=api_key_header,
    )
    assert resp.status_code == 202, resp.text
    assert calls[0]["history"] == [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier answer"},
    ]


async def test_history_bad_shape_returns_422(client, admin_auth_header, api_key_header):
    resp = await client.post(
        "/api/webhooks/generic",
        json={"agent_id": "a", "message": "hi", "history": [{"role": "system", "content": "x"}]},
        headers=api_key_header,
    )
    assert resp.status_code == 422


# ---- Rate limiting ----


async def test_key_rate_limit_exceeded_returns_429(client, admin_auth_header, monkeypatch):
    domain = await _create_domain(client, admin_auth_header)
    agent = await _create_agent(client, admin_auth_header, domain["id"])
    key = await _create_api_key(client, admin_auth_header, rate_limit_per_minute=1)
    headers = {"X-API-Key": key["key"]}

    _patch_enqueue(monkeypatch)
    _patch_fake_redis(monkeypatch)

    resp1 = await client.post(
        "/api/webhooks/generic",
        json={"agent_id": agent["id"], "session_id": "s1", "message": "hi"},
        headers=headers,
    )
    assert resp1.status_code == 202, resp1.text

    resp2 = await client.post(
        "/api/webhooks/generic",
        json={"agent_id": agent["id"], "session_id": "s2", "message": "hi again"},
        headers=headers,
    )
    assert resp2.status_code == 429
    assert "Retry-After" in resp2.headers


async def test_session_rate_limit_exceeded_returns_429(
    client, admin_auth_header, api_key_header, monkeypatch
):
    domain = await _create_domain(client, admin_auth_header)
    agent = await _create_agent(client, admin_auth_header, domain["id"])

    _patch_enqueue(monkeypatch)
    _patch_fake_redis(monkeypatch)

    fake_settings = SimpleNamespace(
        RATE_LIMIT_PER_MINUTE=1000,
        RATE_LIMIT_SESSION_PER_MINUTE=1,
    )
    monkeypatch.setattr("app.modules.webhook.router.get_settings", lambda: fake_settings)

    resp1 = await client.post(
        "/api/webhooks/generic",
        json={"agent_id": agent["id"], "session_id": "same-session", "message": "hi"},
        headers=api_key_header,
    )
    assert resp1.status_code == 202, resp1.text

    resp2 = await client.post(
        "/api/webhooks/generic",
        json={"agent_id": agent["id"], "session_id": "same-session", "message": "again"},
        headers=api_key_header,
    )
    assert resp2.status_code == 429
    assert "Retry-After" in resp2.headers


# ---- Job status polling ----


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
async def test_job_status_mapping(
    client, api_key_header, monkeypatch, fake_status, expected_status, expected_result
):
    async def _fake_get_job_status(job_id: str) -> dict:
        return fake_status

    monkeypatch.setattr("app.modules.webhook.jobs.get_job_status", _fake_get_job_status)

    resp = await client.get("/api/jobs/j1", headers=api_key_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == expected_status
    assert body["result"] == expected_result


async def test_job_status_not_found_returns_404(client, api_key_header, monkeypatch):
    async def _fake_get_job_status(job_id: str) -> dict:
        return {"job_id": job_id, "status": "not_found", "result": None}

    monkeypatch.setattr("app.modules.webhook.jobs.get_job_status", _fake_get_job_status)

    resp = await client.get("/api/jobs/missing", headers=api_key_header)
    assert resp.status_code == 404
