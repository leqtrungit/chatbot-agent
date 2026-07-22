"""Tests for streaming chat job processing."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from sqlalchemy import select

from app.agent.core.types import AgentResponse, AgentStreamEvent, LLMResponse, Message, Role, ToolCall
from app.core.config import get_settings
from app.modules.conversation.models import ChatMessage
from app.modules.domain.models import Domain
from app.worker import tasks


class _FakeSearcher:
    """Stand-in for PgVectorKnowledgeSearcher: records domain-scoped calls."""

    instances: list["_FakeSearcher"] = []

    def __init__(self, session_maker: Any, embedding_provider: Any, embedding_model: str):
        self.session_maker = session_maker
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.calls: list[dict[str, Any]] = []
        _FakeSearcher.instances.append(self)

    async def search(self, query: str, domain_id: str, limit: int):
        self.calls.append({"query": query, "domain_id": domain_id, "limit": limit})
        return []


@pytest.fixture(autouse=True)
def _reset_fake_searcher_instances():
    _FakeSearcher.instances = []
    yield
    _FakeSearcher.instances = []


class _FakeRedis:
    """Minimal fake Redis for testing pubsub."""

    def __init__(self):
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, channel: str, message: str) -> int:
        """Record published messages (decode JSON for easier assertions)."""
        self.published.append((channel, json.loads(message)))
        return 1


async def _seed_domain(session_maker) -> uuid.UUID:
    async with session_maker() as session:
        domain = Domain(name="Chat Domain", slug="chat-domain", description="A test domain")
        session.add(domain)
        await session.commit()
        return domain.id


def _make_fake_session_maker():
    """Create a fake session maker that doesn't need a real database."""
    class _FakeSessionMaker:
        def __call__(self):
            return self

        async def __aenter__(self):
            return object()  # Sentinel session object

        async def __aexit__(self, *exc_info):
            return False

    return _FakeSessionMaker()


async def _make_ctx(session_maker=None, redis: _FakeRedis | None = None, settings=None) -> dict[str, Any]:
    """Create a context dict for task invocation. session_maker defaults to fake if not provided."""
    if session_maker is None:
        session_maker = _make_fake_session_maker()
    return {
        "session_maker": session_maker,
        "embedding_provider": object(),
        "settings": settings or get_settings(),
        "redis": redis or _FakeRedis(),
        "job_id": "test-job-1",
    }


class _FakeAgent:
    """Fake agent with run_stream that yields AgentStreamEvent objects."""

    def __init__(self, stream_chunks: list[AgentStreamEvent] | None = None):
        self.stream_chunks = stream_chunks or []
        self.stream_calls: list[dict[str, Any]] = []

    async def run_stream(self, text: str, history: list[Message] | None = None):
        """Async generator yielding scripted AgentStreamEvents."""
        self.stream_calls.append({"text": text, "history": history})
        for chunk in self.stream_chunks:
            yield chunk


def _make_fake_get_domain(domain_id: uuid.UUID):
    """Create a fake get_domain that returns a Domain with the given ID."""
    async def fake_get_domain(session, domain_uuid):
        domain = Domain(name="Test Domain", slug="test-domain", description="")
        domain.id = domain_uuid
        return domain
    return fake_get_domain


def _make_fake_load_history(history):
    """Create a fake load_history that returns the given history list."""
    async def fake_load_history(session, domain_uuid, session_id, limit):
        return history
    return fake_load_history


def _make_fake_append_turn():
    """Create a fake append_turn that does nothing (for tests that don't verify persistence)."""
    async def fake_append_turn(session, domain_uuid, session_id, text, content):
        pass
    return fake_append_turn


async def test_process_chat_job_stream_publishes_tokens_then_done(monkeypatch):
    """Fake agent yields 2 deltas then 1 final; verify Redis publishes in order."""
    domain_id = uuid.uuid4()
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "get_domain", _make_fake_get_domain(domain_id))
    monkeypatch.setattr(tasks, "load_history", _make_fake_load_history([]))
    monkeypatch.setattr(tasks, "append_turn", _make_fake_append_turn())

    fake_redis = _FakeRedis()
    ctx = await _make_ctx(redis=fake_redis)

    final_response = AgentResponse(
        content="Hello!", messages=[], iterations=1, stopped_on="final_answer"
    )
    stream_events = [
        AgentStreamEvent(type="delta", delta="Hel"),
        AgentStreamEvent(type="delta", delta="lo!"),
        AgentStreamEvent(type="final", response=final_response),
    ]
    fake_agent = _FakeAgent(stream_chunks=stream_events)
    monkeypatch.setattr(tasks, "build_domain_agent", lambda *args, **kwargs: fake_agent)

    result = await tasks.process_chat_job_stream(
        ctx,
        domain_id=str(domain_id),
        session_id="sess-1",
        text="Say hello",
        metadata={},
        platform="generic",
    )

    # Verify Redis pubsub messages in order
    channel = "chat:job:test-job-1"
    assert len(fake_redis.published) == 3
    assert fake_redis.published[0] == (channel, {"type": "token", "delta": "Hel"})
    assert fake_redis.published[1] == (channel, {"type": "token", "delta": "lo!"})
    assert fake_redis.published[2] == (
        channel,
        {
            "type": "done",
            "reply": "Hello!",
            "session_id": "sess-1",
            "iterations": 1,
            "stopped_on": "final_answer",
        },
    )

    # Verify return value matches done payload (minus type key)
    assert result == {
        "reply": "Hello!",
        "session_id": "sess-1",
        "iterations": 1,
        "stopped_on": "final_answer",
    }


async def test_process_chat_job_stream_tool_call_then_final_publishes_only_final_iteration_tokens(
    monkeypatch
):
    """Simulate tool-call iteration: no deltas, then deltas, then final.
    Verify only the deltas from the final iteration are published."""
    domain_id = uuid.uuid4()
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "get_domain", _make_fake_get_domain(domain_id))
    monkeypatch.setattr(tasks, "load_history", _make_fake_load_history([]))
    monkeypatch.setattr(tasks, "append_turn", _make_fake_append_turn())

    fake_redis = _FakeRedis()
    ctx = await _make_ctx(redis=fake_redis)

    final_response = AgentResponse(
        content="Found it!", messages=[], iterations=2, stopped_on="final_answer"
    )
    # Simulate tool-call iteration: no deltas for iteration 1, then deltas for iteration 2
    stream_events = [
        # Iteration 1: tool call, no deltas
        # (skipped in this fake; agent would have tool_calls in its LLM response)
        # Iteration 2: final answer with deltas
        AgentStreamEvent(type="delta", delta="Found"),
        AgentStreamEvent(type="delta", delta=" it!"),
        AgentStreamEvent(type="final", response=final_response),
    ]
    fake_agent = _FakeAgent(stream_chunks=stream_events)
    monkeypatch.setattr(tasks, "build_domain_agent", lambda *args, **kwargs: fake_agent)

    await tasks.process_chat_job_stream(
        ctx,
        domain_id=str(domain_id),
        session_id="sess-tool",
        text="Search for something",
        metadata={},
        platform="generic",
    )

    channel = "chat:job:test-job-1"
    # Only 3 messages: 2 deltas + 1 done
    assert len(fake_redis.published) == 3
    assert fake_redis.published[0][1]["type"] == "token"
    assert fake_redis.published[0][1]["delta"] == "Found"
    assert fake_redis.published[1][1]["type"] == "token"
    assert fake_redis.published[1][1]["delta"] == " it!"
    assert fake_redis.published[2][1]["type"] == "done"


async def test_process_chat_job_stream_persists_turn_and_reuses_history(session_maker, monkeypatch):
    """Verify turn is persisted and history is reused across calls.

    This test requires a real database (session_maker fixture).
    """
    domain_id = await _seed_domain(session_maker)
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)

    fake_redis = _FakeRedis()
    ctx = await _make_ctx(session_maker=session_maker, redis=fake_redis)

    fake_agent = _FakeAgent(
        stream_chunks=[
            AgentStreamEvent(type="final", response=AgentResponse(content="First answer", messages=[], iterations=1, stopped_on="final_answer")),
        ]
    )
    monkeypatch.setattr(tasks, "build_domain_agent", lambda *args, **kwargs: fake_agent)

    # First call
    await tasks.process_chat_job_stream(
        ctx,
        domain_id=str(domain_id),
        session_id="sess-hist",
        text="First question",
        metadata={},
        platform="generic",
    )

    # Reset fake agent for second call
    fake_agent = _FakeAgent(
        stream_chunks=[
            AgentStreamEvent(type="final", response=AgentResponse(content="Second answer", messages=[], iterations=1, stopped_on="final_answer")),
        ]
    )
    monkeypatch.setattr(tasks, "build_domain_agent", lambda *args, **kwargs: fake_agent)

    # Second call with same session
    await tasks.process_chat_job_stream(
        ctx,
        domain_id=str(domain_id),
        session_id="sess-hist",
        text="Second question",
        metadata={},
        platform="generic",
    )

    # Verify history was persisted: should see both turns
    async with session_maker() as session:
        result = await session.execute(
            select(ChatMessage)
            .where(ChatMessage.domain_id == domain_id, ChatMessage.session_id == "sess-hist")
            .order_by(ChatMessage.created_at, ChatMessage.id)
        )
        rows = list(result.scalars().all())

    assert [r.role for r in rows] == ["user", "assistant", "user", "assistant"]
    assert [r.content for r in rows] == [
        "First question",
        "First answer",
        "Second question",
        "Second answer",
    ]


async def test_process_chat_job_stream_publishes_error_and_reraises(monkeypatch):
    """Verify exception during streaming is published and re-raised.

    When an exception occurs during streaming:
    - any tokens already yielded are published
    - the error message is published to Redis
    - the exception is re-raised so arq records job failure
    """
    domain_id = uuid.uuid4()
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "get_domain", _make_fake_get_domain(domain_id))
    monkeypatch.setattr(tasks, "load_history", _make_fake_load_history([]))

    fake_redis = _FakeRedis()
    ctx = await _make_ctx(redis=fake_redis)

    class _StreamingExplodingAgent:
        async def run_stream(self, text, history=None):
            yield AgentStreamEvent(type="delta", delta="x")
            raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "build_domain_agent", lambda *args, **kwargs: _StreamingExplodingAgent())

    with pytest.raises(RuntimeError, match="boom"):
        await tasks.process_chat_job_stream(
            ctx,
            domain_id=str(domain_id),
            session_id="sess-err",
            text="Will fail",
            metadata={},
            platform="generic",
        )

    # Verify error was published to Redis
    channel = "chat:job:test-job-1"
    assert len(fake_redis.published) == 2
    assert fake_redis.published[0] == (channel, {"type": "token", "delta": "x"})
    assert fake_redis.published[1][0] == channel
    assert fake_redis.published[1][1]["type"] == "error"
    assert fake_redis.published[1][1]["message"] == "boom"


def test_process_chat_job_stream_registered_in_worker_settings():
    """Verify the streaming task is registered in WorkerSettings."""
    from app.worker.settings import WorkerSettings

    # Check that process_chat_job_stream is in the functions list
    func_names = [f.name for f in WorkerSettings.functions]
    assert "process_chat_job_stream" in func_names
