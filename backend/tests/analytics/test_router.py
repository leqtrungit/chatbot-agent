from __future__ import annotations

import pytest

from app.modules.agent import service as agent_service
from app.modules.agent.schemas import AgentCreate
from app.modules.analytics import service
from app.modules.apikey import service as apikey_service
from app.modules.apikey.schemas import ApiKeyCreate

pytestmark = pytest.mark.usefixtures("db_session")


async def _seed_one_request_log(session):
    api_key, _raw = await apikey_service.create_api_key(session, ApiKeyCreate(name="App"))
    agent = await agent_service.create_agent(
        session, AgentCreate(name="Agent", provider="openai", model_name="gpt-4o-mini")
    )
    await service.record_request(
        session,
        job_id="job-1",
        api_key_id=api_key.id,
        agent_id=agent.id,
        session_id="sess-1",
        platform="generic",
        model_name="gpt-4o-mini",
        provider="openai",
        usage={"prompt_tokens": 10, "completion_tokens": 5},
        iterations=1,
        stopped_on="final_answer",
        status="success",
        error_message=None,
        latency_ms=100,
    )


async def test_summary_requires_auth(client):
    resp = await client.get("/api/analytics/summary")
    assert resp.status_code == 401


async def test_timeseries_requires_auth(client):
    resp = await client.get("/api/analytics/timeseries")
    assert resp.status_code == 401


async def test_breakdown_requires_auth(client):
    resp = await client.get("/api/analytics/breakdown", params={"by": "api_key"})
    assert resp.status_code == 401


async def test_summary_returns_aggregated_shape(client, admin_auth_header, session_maker):
    async with session_maker() as session:
        await _seed_one_request_log(session)

    resp = await client.get("/api/analytics/summary", headers=admin_auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_requests"] == 1
    assert body["total_prompt_tokens"] == 10
    assert body["total_completion_tokens"] == 5
    assert body["total_tokens"] == 15


async def test_timeseries_returns_points(client, admin_auth_header, session_maker):
    async with session_maker() as session:
        await _seed_one_request_log(session)

    resp = await client.get("/api/analytics/timeseries", headers=admin_auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["requests"] == 1


async def test_breakdown_returns_rows_for_each_dimension(client, admin_auth_header, session_maker):
    async with session_maker() as session:
        await _seed_one_request_log(session)

    for by in ("api_key", "agent", "model", "status"):
        resp = await client.get("/api/analytics/breakdown", params={"by": by}, headers=admin_auth_header)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body) == 1
        assert body[0]["requests"] == 1


async def test_breakdown_rejects_unknown_dimension(client, admin_auth_header):
    resp = await client.get("/api/analytics/breakdown", params={"by": "bogus"}, headers=admin_auth_header)
    assert resp.status_code == 422
