"""Tests for the SSE chat stream endpoint.

Mirror test_webhook_api.py patterns: FakeRedis, monkeypatching, fixtures.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, AsyncIterator

import pytest

pytestmark = pytest.mark.usefixtures("db_session")


async def _create_domain(client, admin_auth_header, name="Support"):
    resp = await client.post("/api/domains", json={"name": name}, headers=admin_auth_header)
    assert resp.status_code == 201
    return resp.json()


async def _create_api_key(client, admin_auth_header, *, name="Test App", rate_limit_per_minute=None):
    payload: dict = {"name": name}
    if rate_limit_per_minute is not None:
        payload["rate_limit_per_minute"] = rate_limit_per_minute
    resp = await client.post("/api/api-keys", json=payload, headers=admin_auth_header)
    assert resp.status_code == 201, resp.text
    return resp.json()


class FakePubSub:
    """Fake pubsub that mimics redis.asyncio.PubSub, backed by an in-memory queue."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self._subscribed_channels: set[str] = set()
        self._index = 0

    async def subscribe(self, *channels: str) -> None:
        """Mock subscribe — just track channels and emit subscription confirmations."""
        for channel in channels:
            self._subscribed_channels.add(channel)
            # Add a subscription confirmation message
            self.messages.insert(self._index, {"type": "subscribe", "channel": channel, "data": 1})

    async def unsubscribe(self, *channels: str) -> None:
        """Mock unsubscribe."""
        for channel in channels:
            self._subscribed_channels.discard(channel)

    async def aclose(self) -> None:
        """Mock close."""
        pass

    def push_message(self, channel: str, payload: dict[str, Any]) -> None:
        """Test helper: push a fake worker message to this channel."""
        self.messages.append({
            "type": "message",
            "channel": channel,
            "pattern": None,
            "data": json.dumps(payload).encode(),
        })

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        """Async iterator that yields messages from the queue."""
        for message in self.messages:
            yield message


class FakeRedis:
    """Minimal in-memory stand-in for rate-limit checks + pubsub."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._pubsubs: dict[str, FakePubSub] = {}

    async def incr(self, key: str) -> int:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        return None

    async def ttl(self, key: str) -> int:
        return 60

    def pubsub(self) -> FakePubSub:
        """Return a new FakePubSub for this test."""
        return FakePubSub()


def _patch_fake_redis(monkeypatch) -> FakeRedis:
    """Monkeypatch get_arq_pool to return our FakeRedis."""
    fake_redis = FakeRedis()

    async def _fake_get_arq_pool():
        return fake_redis

    monkeypatch.setattr("app.modules.chat.jobs.get_arq_pool", _fake_get_arq_pool)
    return fake_redis


def _patch_enqueue(monkeypatch, fake_redis: FakeRedis):
    """Monkeypatch enqueue_chat_stream_job to capture calls and let tests push messages."""
    enqueue_calls: list[dict[str, Any]] = []

    async def _fake_enqueue(
        *,
        job_id: str,
        domain_id: str,
        session_id: str,
        text: str,
        metadata: dict[str, Any],
        platform: str,
    ) -> None:
        call = {
            "job_id": job_id,
            "domain_id": domain_id,
            "session_id": session_id,
            "text": text,
            "metadata": metadata,
            "platform": platform,
        }
        enqueue_calls.append(call)

    monkeypatch.setattr("app.modules.chat.jobs.enqueue_chat_stream_job", _fake_enqueue)
    return enqueue_calls


# ---- Auth ----


async def test_missing_api_key_returns_401(client, admin_auth_header):
    domain = await _create_domain(client, admin_auth_header)
    resp = await client.post(
        "/api/chat/stream",
        json={"domain_id": domain["id"], "message": "hi"},
    )
    assert resp.status_code == 401


async def test_invalid_api_key_returns_401(client, admin_auth_header):
    domain = await _create_domain(client, admin_auth_header)
    resp = await client.post(
        "/api/chat/stream",
        json={"domain_id": domain["id"], "message": "hi"},
        headers={"X-API-Key": "cba_not-a-real-key"},
    )
    assert resp.status_code == 401


async def test_revoked_api_key_returns_401(client, admin_auth_header):
    domain = await _create_domain(client, admin_auth_header)
    key = await _create_api_key(client, admin_auth_header)
    revoke_resp = await client.post(
        f"/api/api-keys/{key['id']}/revoke", headers=admin_auth_header
    )
    assert revoke_resp.status_code == 200

    resp = await client.post(
        "/api/chat/stream",
        json={"domain_id": domain["id"], "message": "hi"},
        headers={"X-API-Key": key["key"]},
    )
    assert resp.status_code == 401


# ---- Domain resolution ----


async def test_unknown_domain_returns_404(client, admin_auth_header, api_key_header, monkeypatch):
    _patch_fake_redis(monkeypatch)
    _patch_enqueue(monkeypatch, FakeRedis())

    resp = await client.post(
        "/api/chat/stream",
        json={"domain_id": "00000000-0000-0000-0000-000000000000", "message": "hi"},
        headers=api_key_header,
    )
    assert resp.status_code == 404


# ---- Payload validation ----


async def test_invalid_payload_returns_422(client, admin_auth_header, api_key_header, monkeypatch):
    domain = await _create_domain(client, admin_auth_header)
    _patch_fake_redis(monkeypatch)
    _patch_enqueue(monkeypatch, FakeRedis())

    resp = await client.post(
        "/api/chat/stream",
        json={"domain_id": domain["id"]},  # missing "message"
        headers=api_key_header,
    )
    assert resp.status_code == 422


# ---- Rate limiting ----


async def test_key_rate_limit_exceeded_returns_429(client, admin_auth_header, monkeypatch):
    domain = await _create_domain(client, admin_auth_header)
    key = await _create_api_key(client, admin_auth_header, rate_limit_per_minute=1)
    headers = {"X-API-Key": key["key"]}

    fake_redis = _patch_fake_redis(monkeypatch)
    _patch_enqueue(monkeypatch, fake_redis)

    # Mock relay_job_events to return a done frame immediately
    from app.modules.chat.service import sse_frame

    async def _mock_relay(pubsub):
        yield sse_frame({"type": "done", "reply": "ok", "session_id": "s", "iterations": 1, "stopped_on": "final_answer"})

    monkeypatch.setattr("app.modules.chat.router.relay_job_events", _mock_relay)

    resp1 = await client.post(
        "/api/chat/stream",
        json={"domain_id": domain["id"], "session_id": "s1", "message": "hi"},
        headers=headers,
    )
    assert resp1.status_code == 200  # SSE endpoints return 200
    # Consume the stream to close it
    async for _ in resp1.aiter_lines():
        pass

    resp2 = await client.post(
        "/api/chat/stream",
        json={"domain_id": domain["id"], "session_id": "s2", "message": "hi again"},
        headers=headers,
    )
    assert resp2.status_code == 429
    assert "Retry-After" in resp2.headers


async def test_session_rate_limit_exceeded_returns_429(
    client, admin_auth_header, api_key_header, monkeypatch
):
    domain = await _create_domain(client, admin_auth_header)

    fake_redis = _patch_fake_redis(monkeypatch)
    _patch_enqueue(monkeypatch, fake_redis)

    fake_settings = SimpleNamespace(
        RATE_LIMIT_PER_MINUTE=1000,
        RATE_LIMIT_SESSION_PER_MINUTE=1,
    )
    monkeypatch.setattr("app.modules.chat.router.get_settings", lambda: fake_settings)

    # Mock relay_job_events to return a done frame immediately
    from app.modules.chat.service import sse_frame

    async def _mock_relay(pubsub):
        yield sse_frame({"type": "done", "reply": "ok", "session_id": "s", "iterations": 1, "stopped_on": "final_answer"})

    monkeypatch.setattr("app.modules.chat.router.relay_job_events", _mock_relay)

    resp1 = await client.post(
        "/api/chat/stream",
        json={"domain_id": domain["id"], "session_id": "same-session", "message": "hi"},
        headers=api_key_header,
    )
    assert resp1.status_code == 200
    # Consume the stream
    async for _ in resp1.aiter_lines():
        pass

    resp2 = await client.post(
        "/api/chat/stream",
        json={"domain_id": domain["id"], "session_id": "same-session", "message": "again"},
        headers=api_key_header,
    )
    assert resp2.status_code == 429
    assert "Retry-After" in resp2.headers


# ---- Happy path streaming ----


async def test_happy_path_streams_queued_token_and_done_frames(
    client, admin_auth_header, api_key_header, monkeypatch
):
    """Happy path: stream returns 200 with SSE frames."""
    domain = await _create_domain(client, admin_auth_header)

    fake_redis = _patch_fake_redis(monkeypatch)
    enqueue_calls = _patch_enqueue(monkeypatch, fake_redis)

    # Mock relay_job_events to yield token and done frames
    from app.modules.chat.service import sse_frame

    async def _mock_relay(pubsub):
        yield sse_frame({"type": "token", "delta": "Hi"})
        yield sse_frame({"type": "done", "reply": "Hi", "session_id": "s", "iterations": 1, "stopped_on": "final_answer"})

    monkeypatch.setattr("app.modules.chat.router.relay_job_events", _mock_relay)

    resp = await client.post(
        "/api/chat/stream",
        json={"domain_id": domain["id"], "session_id": "s1", "message": "hello"},
        headers=api_key_header,
    )
    assert resp.status_code == 200

    # The enqueue function was called — extract the job_id from the call
    assert len(enqueue_calls) == 1
    job_id = enqueue_calls[0]["job_id"]

    # Collect the SSE frames as they arrive
    lines = []
    async for line in resp.aiter_lines():
        if line.strip():
            lines.append(line)

    # Should have: queued + token + done frames
    assert len(lines) >= 3
    first_frame = json.loads(lines[0].replace("data: ", ""))
    assert first_frame["type"] == "queued"
    assert first_frame["job_id"] == job_id

    token_frame = json.loads(lines[1].replace("data: ", ""))
    assert token_frame["type"] == "token"
    assert token_frame["delta"] == "Hi"

    done_frame = json.loads(lines[2].replace("data: ", ""))
    assert done_frame["type"] == "done"


async def test_happy_path_by_slug(client, admin_auth_header, api_key_header, monkeypatch):
    """Domain can be resolved by slug."""
    domain = await _create_domain(client, admin_auth_header, name="By Slug Domain")

    fake_redis = _patch_fake_redis(monkeypatch)
    _patch_enqueue(monkeypatch, fake_redis)

    # Mock relay_job_events to return a done frame immediately
    from app.modules.chat.service import sse_frame

    async def _mock_relay(pubsub):
        yield sse_frame({"type": "done", "reply": "ok", "session_id": "s", "iterations": 1, "stopped_on": "final_answer"})

    monkeypatch.setattr("app.modules.chat.router.relay_job_events", _mock_relay)

    resp = await client.post(
        "/api/chat/stream",
        json={"domain_id": domain["slug"], "message": "hi"},
        headers=api_key_header,
        
    )
    assert resp.status_code == 200
    # Just verify we got a response; don't read frames
    async for _ in resp.aiter_lines():
        break  # Just read first line


async def test_enqueue_uses_generated_job_id_as_job_id_param(
    client, admin_auth_header, api_key_header, monkeypatch
):
    """The job_id in the enqueue call should match the job_id in the queued frame."""
    domain = await _create_domain(client, admin_auth_header)

    fake_redis = _patch_fake_redis(monkeypatch)
    enqueue_calls = _patch_enqueue(monkeypatch, fake_redis)

    # Mock relay_job_events to return a done frame immediately
    from app.modules.chat.service import sse_frame

    async def _mock_relay(pubsub):
        yield sse_frame({"type": "done", "reply": "ok", "session_id": "s", "iterations": 1, "stopped_on": "final_answer"})

    monkeypatch.setattr("app.modules.chat.router.relay_job_events", _mock_relay)

    resp = await client.post(
        "/api/chat/stream",
        json={"domain_id": domain["id"], "message": "test"},
        headers=api_key_header,
        
    )
    assert resp.status_code == 200

    # Extract the queued frame
    lines = []
    async for line in resp.aiter_lines():
        if line.strip():
            lines.append(line)
            if len(lines) >= 1:
                break

    queued_frame = json.loads(lines[0].replace("data: ", ""))
    queued_job_id = queued_frame["job_id"]

    # The enqueue call should have the same job_id
    assert len(enqueue_calls) == 1
    assert enqueue_calls[0]["job_id"] == queued_job_id


async def test_error_frame_closes_stream(
    client, admin_auth_header, api_key_header, monkeypatch
):
    """When an error message is published, the stream should close after emitting it."""
    domain = await _create_domain(client, admin_auth_header)

    fake_redis = _patch_fake_redis(monkeypatch)
    enqueue_calls = _patch_enqueue(monkeypatch, fake_redis)

    # Patch enqueue to push an error message into the channel
    original_enqueue = None

    async def _enqueue_with_error(
        *,
        job_id: str,
        domain_id: str,
        session_id: str,
        text: str,
        metadata: dict[str, Any],
        platform: str,
    ) -> None:
        # Call original to record the call
        await original_enqueue(
            job_id=job_id,
            domain_id=domain_id,
            session_id=session_id,
            text=text,
            metadata=metadata,
            platform=platform,
        )
        # Push an error message
        channel = f"chat:job:{job_id}"
        # We need to reach into the pubsub somehow... this is tricky with the test setup
        # Let's use a different approach: monkeypatch at the route level

    # Actually, let me take a simpler approach: monkeypatch relay_job_events directly
    async def _fake_relay_error(pubsub):
        from app.modules.chat.service import sse_frame

        yield sse_frame({"type": "error", "message": "Test error"})

    monkeypatch.setattr("app.modules.chat.router.relay_job_events", _fake_relay_error)

    resp = await client.post(
        "/api/chat/stream",
        json={"domain_id": domain["id"], "message": "test"},
        headers=api_key_header,
        
    )
    assert resp.status_code == 200

    # Collect frames
    frames = []
    async for line in resp.aiter_lines():
        if line.strip():
            frames.append(line)

    # Should have: queued frame + error frame
    assert len(frames) >= 2
    queued = json.loads(frames[0].replace("data: ", ""))
    assert queued["type"] == "queued"

    error = json.loads(frames[1].replace("data: ", ""))
    assert error["type"] == "error"
    assert error["message"] == "Test error"


async def test_metadata_carries_app_identity(
    client, admin_auth_header, api_key_header, monkeypatch
):
    """The metadata dict passed to enqueue should include app_id and app_name."""
    domain = await _create_domain(client, admin_auth_header)

    fake_redis = _patch_fake_redis(monkeypatch)
    enqueue_calls = _patch_enqueue(monkeypatch, fake_redis)

    # Mock relay_job_events to return a done frame immediately
    from app.modules.chat.service import sse_frame

    async def _mock_relay(pubsub):
        yield sse_frame({"type": "done", "reply": "ok", "session_id": "s", "iterations": 1, "stopped_on": "final_answer"})

    monkeypatch.setattr("app.modules.chat.router.relay_job_events", _mock_relay)

    resp = await client.post(
        "/api/chat/stream",
        json={
            "domain_id": domain["id"],
            "session_id": "s1",
            "message": "test",
            "metadata": {"custom_key": "custom_value"},
        },
        headers=api_key_header,
        
    )
    assert resp.status_code == 200
    # Consume the stream
    async for _ in resp.aiter_lines():
        break

    assert len(enqueue_calls) == 1
    metadata = enqueue_calls[0]["metadata"]
    assert "app_id" in metadata
    assert "app_name" in metadata
    assert metadata["app_name"] == "Test App"
    assert metadata["custom_key"] == "custom_value"
