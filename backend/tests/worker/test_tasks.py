from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.agent.core.types import LLMResponse, ToolCall
from app.core.config import get_settings
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


async def _seed_domain(session_maker) -> uuid.UUID:
    async with session_maker() as session:
        domain = Domain(name="Chat Domain", slug="chat-domain", description="A test domain")
        session.add(domain)
        await session.commit()
        return domain.id


async def test_process_chat_job_runs_agent_and_scopes_search(
    session_maker, monkeypatch, mock_llm
):
    domain_id = await _seed_domain(session_maker)

    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "build_llm_provider", lambda settings: mock_llm)

    mock_llm.queue(
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="call_0", name="knowledge_search", arguments={"query": "hours"})],
        )
    )
    mock_llm.queue(LLMResponse(content="We are open 9-5.", finish_reason="stop"))

    ctx = {
        "session_maker": session_maker,
        "embedding_provider": object(),
        "settings": get_settings(),
    }

    result = await tasks.process_chat_job(
        ctx,
        domain_id=str(domain_id),
        session_id="sess-1",
        text="What are your hours?",
        metadata={},
        platform="generic",
    )

    assert result == {
        "reply": "We are open 9-5.",
        "session_id": "sess-1",
        "iterations": 2,
        "stopped_on": "final_answer",
    }
    assert len(mock_llm.calls) == 2

    assert len(_FakeSearcher.instances) == 1
    searcher = _FakeSearcher.instances[0]
    assert len(searcher.calls) == 1
    assert searcher.calls[0]["domain_id"] == str(domain_id)
    assert searcher.calls[0]["query"] == "hours"


async def test_ingest_document_task_delegates_to_pipeline(monkeypatch):
    calls: list[dict[str, Any]] = []

    async def _fake_ingest_document(document_id, session, embedding_provider, *, embedding_model=None, **kwargs):
        calls.append(
            {
                "document_id": document_id,
                "session": session,
                "embedding_provider": embedding_provider,
                "embedding_model": embedding_model,
            }
        )

    monkeypatch.setattr(tasks, "ingest_document", _fake_ingest_document)

    sentinel_session = object()

    class _FakeSessionMaker:
        def __call__(self):
            return self

        async def __aenter__(self):
            return sentinel_session

        async def __aexit__(self, *exc_info):
            return False

    sentinel_embedding_provider = object()
    settings = get_settings()

    ctx = {
        "session_maker": _FakeSessionMaker(),
        "embedding_provider": sentinel_embedding_provider,
        "settings": settings,
    }

    document_id = uuid.uuid4()
    await tasks.ingest_document_task(ctx, str(document_id))

    assert len(calls) == 1
    assert calls[0]["document_id"] == document_id
    assert calls[0]["session"] is sentinel_session
    assert calls[0]["embedding_provider"] is sentinel_embedding_provider
    assert calls[0]["embedding_model"] == settings.EMBEDDING_MODEL
