"""Tests for streaming chat job processing."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from sqlalchemy import select

from app.agent.core.types import AgentResponse, AgentStreamEvent, LLMResponse, Message, Role, ToolCall
from app.core.config import get_settings
from app.modules.agent.models import Agent
from app.modules.analytics.models import RequestLog
from app.modules.apikey import service as apikey_service
from app.modules.apikey.schemas import ApiKeyCreate
from app.modules.conversation.models import ChatMessage
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


async def _seed_agent(session_maker) -> uuid.UUID:
    async with session_maker() as session:
        agent = Agent(name=f"Test Agent {uuid.uuid4()}", provider="ollama", model_name="qwen2.5")
        session.add(agent)
        await session.commit()
        return agent.id


async def _seed_api_key(session_maker, name="App") -> uuid.UUID:
    async with session_maker() as session:
        api_key, _raw = await apikey_service.create_api_key(session, ApiKeyCreate(name=name))
        return api_key.id


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


def _make_fake_get_agent(agent_id: uuid.UUID):
    """Create a fake get_agent that returns a placeholder Agent row.

    ``build_agent`` is always monkeypatched separately in this file,
    so this stub's field values are never actually read.
    """
    async def fake_get_agent(session, agent_uuid):
        agent = Agent(name="Test Agent", provider="ollama", model_name="qwen2.5")
        agent.id = agent_uuid
        return agent
    return fake_get_agent


def _make_fake_load_history(history):
    """Create a fake load_history that returns the given history list."""
    async def fake_load_history(session, agent_uuid, session_id, limit):
        return history
    return fake_load_history


def _make_fake_append_turn():
    """Create a fake append_turn that does nothing (for tests that don't verify persistence)."""
    async def fake_append_turn(session, agent_uuid, session_id, text, content):
        pass
    return fake_append_turn


async def test_process_chat_job_stream_publishes_tokens_then_done(monkeypatch):
    """Fake agent yields 2 deltas then 1 final; verify Redis publishes in order."""
    agent_id = uuid.uuid4()
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "get_agent", _make_fake_get_agent(agent_id))
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

    async def _fake_build_agent(*args, **kwargs):
        return fake_agent

    monkeypatch.setattr(tasks, "build_agent", _fake_build_agent)

    result = await tasks.process_chat_job_stream(
        ctx,
        agent_id=str(agent_id),
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


async def test_process_chat_job_stream_publishes_thinking_before_tokens(monkeypatch):
    """Thinking deltas are published as their own event type, ahead of content tokens."""
    agent_id = uuid.uuid4()
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "get_agent", _make_fake_get_agent(agent_id))
    monkeypatch.setattr(tasks, "load_history", _make_fake_load_history([]))
    monkeypatch.setattr(tasks, "append_turn", _make_fake_append_turn())

    fake_redis = _FakeRedis()
    ctx = await _make_ctx(redis=fake_redis)

    final_response = AgentResponse(
        content="Answer", messages=[], iterations=1, stopped_on="final_answer"
    )
    stream_events = [
        AgentStreamEvent(type="thinking", thinking="Let me "),
        AgentStreamEvent(type="thinking", thinking="think..."),
        AgentStreamEvent(type="delta", delta="Answer"),
        AgentStreamEvent(type="final", response=final_response),
    ]
    fake_agent = _FakeAgent(stream_chunks=stream_events)

    async def _fake_build_agent(*args, **kwargs):
        return fake_agent

    monkeypatch.setattr(tasks, "build_agent", _fake_build_agent)

    await tasks.process_chat_job_stream(
        ctx,
        agent_id=str(agent_id),
        session_id="sess-think",
        text="Explain something",
        metadata={},
        platform="generic",
    )

    channel = "chat:job:test-job-1"
    assert len(fake_redis.published) == 4
    assert fake_redis.published[0] == (channel, {"type": "thinking", "delta": "Let me "})
    assert fake_redis.published[1] == (channel, {"type": "thinking", "delta": "think..."})
    assert fake_redis.published[2] == (channel, {"type": "token", "delta": "Answer"})
    assert fake_redis.published[3][1]["type"] == "done"


async def test_process_chat_job_stream_tool_call_then_final_publishes_only_final_iteration_tokens(
    monkeypatch
):
    """Simulate tool-call iteration: no deltas, then deltas, then final.
    Verify only the deltas from the final iteration are published."""
    agent_id = uuid.uuid4()
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "get_agent", _make_fake_get_agent(agent_id))
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

    async def _fake_build_agent(*args, **kwargs):
        return fake_agent

    monkeypatch.setattr(tasks, "build_agent", _fake_build_agent)

    await tasks.process_chat_job_stream(
        ctx,
        agent_id=str(agent_id),
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


async def test_process_chat_job_stream_client_managed_history_skips_db_load_and_persist(
    session_maker, monkeypatch
):
    """When ``history`` is supplied, the worker must use it as-is and must not
    touch ``chat_messages`` at all (neither load nor append)."""
    agent_id = await _seed_agent(session_maker)
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("load_history must not be called for client-managed history")

    monkeypatch.setattr(tasks, "load_history", _fail_if_called)

    fake_redis = _FakeRedis()
    ctx = await _make_ctx(session_maker=session_maker, redis=fake_redis)

    fake_agent = _FakeAgent(
        stream_chunks=[
            AgentStreamEvent(
                type="final",
                response=AgentResponse(content="Answer", messages=[], iterations=1, stopped_on="final_answer"),
            ),
        ]
    )

    async def _fake_build_agent(*args, **kwargs):
        return fake_agent

    monkeypatch.setattr(tasks, "build_agent", _fake_build_agent)

    await tasks.process_chat_job_stream(
        ctx,
        agent_id=str(agent_id),
        session_id="sess-client-managed-stream",
        text="New question",
        metadata={},
        platform="generic",
        history=[
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
        ],
    )

    passed_history = fake_agent.stream_calls[0]["history"]
    assert [m.content for m in passed_history] == ["Earlier question", "Earlier answer"]

    async with session_maker() as session:
        rows = list(
            (
                await session.execute(
                    select(ChatMessage).where(
                        ChatMessage.agent_id == agent_id,
                        ChatMessage.session_id == "sess-client-managed-stream",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert rows == []


async def test_process_chat_job_stream_persists_turn_and_reuses_history(session_maker, monkeypatch):
    """Verify turn is persisted and history is reused across calls.

    This test requires a real database (session_maker fixture).
    """
    agent_id = await _seed_agent(session_maker)
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)

    fake_redis = _FakeRedis()
    ctx = await _make_ctx(session_maker=session_maker, redis=fake_redis)

    fake_agent = _FakeAgent(
        stream_chunks=[
            AgentStreamEvent(type="final", response=AgentResponse(content="First answer", messages=[], iterations=1, stopped_on="final_answer")),
        ]
    )

    async def _fake_build_agent_first(*args, **kwargs):
        return fake_agent

    monkeypatch.setattr(tasks, "build_agent", _fake_build_agent_first)

    # First call
    await tasks.process_chat_job_stream(
        ctx,
        agent_id=str(agent_id),
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

    async def _fake_build_agent_second(*args, **kwargs):
        return fake_agent

    monkeypatch.setattr(tasks, "build_agent", _fake_build_agent_second)

    # Second call with same session
    await tasks.process_chat_job_stream(
        ctx,
        agent_id=str(agent_id),
        session_id="sess-hist",
        text="Second question",
        metadata={},
        platform="generic",
    )

    # Verify history was persisted: should see both turns
    async with session_maker() as session:
        result = await session.execute(
            select(ChatMessage)
            .where(ChatMessage.agent_id == agent_id, ChatMessage.session_id == "sess-hist")
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


async def test_process_chat_job_stream_writes_request_log_on_success(session_maker, monkeypatch):
    agent_id = await _seed_agent(session_maker)
    api_key_id = await _seed_api_key(session_maker)
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)

    fake_redis = _FakeRedis()
    ctx = await _make_ctx(session_maker=session_maker, redis=fake_redis)

    fake_agent = _FakeAgent(
        stream_chunks=[
            AgentStreamEvent(
                type="final",
                response=AgentResponse(
                    content="Answer",
                    messages=[],
                    iterations=1,
                    stopped_on="final_answer",
                    usage={"prompt_tokens": 8, "completion_tokens": 4},
                ),
            ),
        ]
    )

    async def _fake_build_agent(*args, **kwargs):
        return fake_agent

    monkeypatch.setattr(tasks, "build_agent", _fake_build_agent)

    await tasks.process_chat_job_stream(
        ctx,
        agent_id=str(agent_id),
        session_id="sess-log-stream",
        text="Hi",
        metadata={"app_id": str(api_key_id), "app_name": "App"},
        platform="generic",
    )

    async with session_maker() as session:
        rows = list((await session.execute(select(RequestLog))).scalars().all())

    assert len(rows) == 1
    row = rows[0]
    assert row.status == "success"
    assert row.api_key_id == api_key_id
    assert row.agent_id == agent_id
    assert row.prompt_tokens == 8
    assert row.completion_tokens == 4


async def test_process_chat_job_stream_writes_request_log_on_failure(session_maker, monkeypatch):
    agent_id = await _seed_agent(session_maker)
    api_key_id = await _seed_api_key(session_maker)
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)

    fake_redis = _FakeRedis()
    ctx = await _make_ctx(session_maker=session_maker, redis=fake_redis)

    class _StreamingExplodingAgent:
        async def run_stream(self, text, history=None):
            raise RuntimeError("stream boom")
            yield  # pragma: no cover - unreachable, makes this an async generator

    async def _fake_build_agent(*args, **kwargs):
        return _StreamingExplodingAgent()

    monkeypatch.setattr(tasks, "build_agent", _fake_build_agent)

    with pytest.raises(RuntimeError, match="stream boom"):
        await tasks.process_chat_job_stream(
            ctx,
            agent_id=str(agent_id),
            session_id="sess-log-stream-err",
            text="Hi",
            metadata={"app_id": str(api_key_id), "app_name": "App"},
            platform="generic",
        )

    async with session_maker() as session:
        rows = list((await session.execute(select(RequestLog))).scalars().all())

    assert len(rows) == 1
    row = rows[0]
    assert row.status == "error"
    assert row.error_message is not None


async def test_process_chat_job_stream_publishes_error_and_reraises(monkeypatch):
    """Verify exception during streaming is published and re-raised.

    When an exception occurs during streaming:
    - any tokens already yielded are published
    - the error message is published to Redis
    - the exception is re-raised so arq records job failure
    """
    agent_id = uuid.uuid4()
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "get_agent", _make_fake_get_agent(agent_id))
    monkeypatch.setattr(tasks, "load_history", _make_fake_load_history([]))

    fake_redis = _FakeRedis()
    ctx = await _make_ctx(redis=fake_redis)

    class _StreamingExplodingAgent:
        async def run_stream(self, text, history=None):
            yield AgentStreamEvent(type="delta", delta="x")
            raise RuntimeError("boom")

    async def _fake_build_agent(*args, **kwargs):
        return _StreamingExplodingAgent()

    monkeypatch.setattr(tasks, "build_agent", _fake_build_agent)

    with pytest.raises(RuntimeError, match="boom"):
        await tasks.process_chat_job_stream(
            ctx,
            agent_id=str(agent_id),
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
