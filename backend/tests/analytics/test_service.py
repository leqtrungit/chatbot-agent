from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.modules.agent import service as agent_service
from app.modules.agent.schemas import AgentCreate
from app.modules.analytics import service
from app.modules.analytics.models import RequestLog
from app.modules.apikey import service as apikey_service
from app.modules.apikey.schemas import ApiKeyCreate

pytestmark = pytest.mark.usefixtures("db_session")


async def _make_api_key(session, name="App"):
    api_key, _raw = await apikey_service.create_api_key(session, ApiKeyCreate(name=name))
    return api_key


async def _make_agent(session, name="Agent", model_name="gpt-4o-mini", provider="openai"):
    return await agent_service.create_agent(
        session, AgentCreate(name=name, provider=provider, model_name=model_name)
    )


async def _record(
    session,
    *,
    api_key_id,
    agent_id,
    model_name="gpt-4o-mini",
    provider="openai",
    status="success",
    prompt_tokens=10,
    completion_tokens=5,
    latency_ms=100,
    created_at=None,
):
    log = await service.record_request(
        session,
        job_id="job-1",
        api_key_id=api_key_id,
        agent_id=agent_id,
        session_id="sess-1",
        platform="generic",
        model_name=model_name,
        provider=provider,
        usage={"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        iterations=1,
        stopped_on="final_answer",
        status=status,
        error_message=None if status == "success" else "boom",
        latency_ms=latency_ms,
    )
    if created_at is not None:
        await session.execute(
            update(RequestLog).where(RequestLog.id == log.id).values(created_at=created_at)
        )
        await session.commit()
    return log


async def test_record_request_computes_total_tokens(db_session):
    api_key = await _make_api_key(db_session)
    agent = await _make_agent(db_session)

    log = await _record(db_session, api_key_id=api_key.id, agent_id=agent.id, prompt_tokens=10, completion_tokens=5)

    assert log.prompt_tokens == 10
    assert log.completion_tokens == 5
    assert log.total_tokens == 15


async def test_record_request_truncates_long_error_message(db_session):
    api_key = await _make_api_key(db_session)
    agent = await _make_agent(db_session)

    log = await service.record_request(
        db_session,
        job_id="job-1",
        api_key_id=api_key.id,
        agent_id=agent.id,
        session_id="sess-1",
        platform="generic",
        model_name="gpt-4o-mini",
        provider="openai",
        usage={},
        iterations=1,
        stopped_on="error",
        status="error",
        error_message="x" * 1000,
        latency_ms=50,
    )

    assert log.error_message is not None
    assert len(log.error_message) == 500


async def test_get_summary_aggregates_totals_and_error_rate(db_session):
    api_key = await _make_api_key(db_session)
    agent = await _make_agent(db_session)

    await _record(db_session, api_key_id=api_key.id, agent_id=agent.id, status="success", prompt_tokens=10, completion_tokens=5, latency_ms=100)
    await _record(db_session, api_key_id=api_key.id, agent_id=agent.id, status="success", prompt_tokens=20, completion_tokens=10, latency_ms=200)
    await _record(db_session, api_key_id=api_key.id, agent_id=agent.id, status="error", prompt_tokens=5, completion_tokens=0, latency_ms=50)

    since = datetime.now(timezone.utc) - timedelta(days=1)
    summary = await service.get_summary(db_session, since)

    assert summary.total_requests == 3
    assert summary.success_requests == 2
    assert summary.error_requests == 1
    assert summary.error_rate == pytest.approx(1 / 3)
    assert summary.total_prompt_tokens == 35
    assert summary.total_completion_tokens == 15
    assert summary.total_tokens == 50
    assert summary.avg_latency_ms == pytest.approx((100 + 200 + 50) / 3)


async def test_get_summary_excludes_rows_before_since(db_session):
    api_key = await _make_api_key(db_session)
    agent = await _make_agent(db_session)

    old = datetime.now(timezone.utc) - timedelta(days=10)
    await _record(db_session, api_key_id=api_key.id, agent_id=agent.id, created_at=old)

    since = datetime.now(timezone.utc) - timedelta(days=1)
    summary = await service.get_summary(db_session, since)

    assert summary.total_requests == 0


async def test_get_timeseries_buckets_by_day(db_session):
    api_key = await _make_api_key(db_session)
    agent = await _make_agent(db_session)

    day1 = datetime(2026, 8, 1, 10, tzinfo=timezone.utc)
    day2 = datetime(2026, 8, 2, 10, tzinfo=timezone.utc)
    await _record(db_session, api_key_id=api_key.id, agent_id=agent.id, created_at=day1, status="success")
    await _record(db_session, api_key_id=api_key.id, agent_id=agent.id, created_at=day1, status="error")
    await _record(db_session, api_key_id=api_key.id, agent_id=agent.id, created_at=day2, status="success")

    since = datetime(2026, 7, 30, tzinfo=timezone.utc)
    points = await service.get_timeseries(db_session, since, "day")

    assert len(points) == 2
    assert points[0].requests == 2
    assert points[0].error_count == 1
    assert points[1].requests == 1
    assert points[1].error_count == 0


async def test_get_breakdown_by_api_key(db_session):
    key_a = await _make_api_key(db_session, name="A")
    key_b = await _make_api_key(db_session, name="B")
    agent = await _make_agent(db_session)

    await _record(db_session, api_key_id=key_a.id, agent_id=agent.id)
    await _record(db_session, api_key_id=key_a.id, agent_id=agent.id)
    await _record(db_session, api_key_id=key_b.id, agent_id=agent.id)

    since = datetime.now(timezone.utc) - timedelta(days=1)
    rows = await service.get_breakdown(db_session, since, "api_key")

    by_name = {r.key: r for r in rows}
    assert by_name["A"].requests == 2
    assert by_name["B"].requests == 1
    assert by_name["A"].key_id == str(key_a.id)


async def test_get_breakdown_by_model(db_session):
    api_key = await _make_api_key(db_session)
    agent = await _make_agent(db_session)

    await _record(db_session, api_key_id=api_key.id, agent_id=agent.id, model_name="gpt-4o-mini")
    await _record(db_session, api_key_id=api_key.id, agent_id=agent.id, model_name="qwen2.5")
    await _record(db_session, api_key_id=api_key.id, agent_id=agent.id, model_name="qwen2.5")

    since = datetime.now(timezone.utc) - timedelta(days=1)
    rows = await service.get_breakdown(db_session, since, "model")

    by_name = {r.key: r for r in rows}
    assert by_name["qwen2.5"].requests == 2
    assert by_name["gpt-4o-mini"].requests == 1
    assert by_name["qwen2.5"].key_id is None


async def test_get_breakdown_by_status(db_session):
    api_key = await _make_api_key(db_session)
    agent = await _make_agent(db_session)

    await _record(db_session, api_key_id=api_key.id, agent_id=agent.id, status="success")
    await _record(db_session, api_key_id=api_key.id, agent_id=agent.id, status="error")

    since = datetime.now(timezone.utc) - timedelta(days=1)
    rows = await service.get_breakdown(db_session, since, "status")

    by_name = {r.key: r for r in rows}
    assert by_name["success"].requests == 1
    assert by_name["error"].requests == 1


def test_range_to_since():
    now = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)
    assert service.range_to_since("24h", now=now) == now - timedelta(hours=24)
    assert service.range_to_since("7d", now=now) == now - timedelta(days=7)
    assert service.range_to_since("30d", now=now) == now - timedelta(days=30)


def test_bucket_for_range():
    assert service.bucket_for_range("24h") == "hour"
    assert service.bucket_for_range("7d") == "day"
    assert service.bucket_for_range("30d") == "day"
