from __future__ import annotations

import uuid
from typing import Any

import pytest

from sqlalchemy import select

from app.agent.core.types import LLMResponse, Role, ToolCall
from app.agent.providers.ollama import OllamaProvider
from app.agent.providers.openai_compat import OpenAICompatProvider
from app.core.config import get_settings
from app.modules.agent.models import Agent
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


async def _seed_domain(session_maker) -> uuid.UUID:
    async with session_maker() as session:
        domain = Domain(name="Chat Domain", slug="chat-domain", description="A test domain")
        session.add(domain)
        await session.commit()
        return domain.id


async def _seed_agent(session_maker, domain_ids: list[uuid.UUID] | None = None, **overrides) -> uuid.UUID:
    async with session_maker() as session:
        domains = []
        if domain_ids:
            result = await session.execute(select(Domain).where(Domain.id.in_(domain_ids)))
            domains = list(result.scalars().all())
        agent = Agent(
            name=overrides.pop("name", f"Test Agent {uuid.uuid4()}"),
            provider="ollama",
            model_name="qwen2.5",
            domains=domains,
            **overrides,
        )
        session.add(agent)
        await session.commit()
        return agent.id


async def test_process_chat_job_runs_agent_and_scopes_search(
    session_maker, monkeypatch, mock_llm
):
    domain_id = await _seed_domain(session_maker)
    agent_id = await _seed_agent(session_maker, domain_ids=[domain_id])

    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "build_llm_provider", lambda agent, settings: mock_llm)

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
        agent_id=str(agent_id),
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


async def test_process_chat_job_uses_agent_system_prompt_verbatim(session_maker, monkeypatch, mock_llm):
    custom_prompt = "You are a pirate. Answer every question in pirate speak."
    agent_id = await _seed_agent(session_maker, system_prompt=custom_prompt)

    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "build_llm_provider", lambda agent, settings: mock_llm)

    mock_llm.queue(LLMResponse(content="Arrr!", finish_reason="stop"))

    ctx = await _make_ctx(session_maker)

    await tasks.process_chat_job(
        ctx,
        agent_id=str(agent_id),
        session_id="sess-pirate",
        text="What are your hours?",
        metadata={},
        platform="generic",
    )

    assert mock_llm.calls[0]["messages"][0].content == custom_prompt


async def test_process_chat_job_falls_back_to_builder_default_when_system_prompt_none(
    session_maker, monkeypatch, mock_llm
):
    agent_id = await _seed_agent(session_maker)

    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "build_llm_provider", lambda agent, settings: mock_llm)

    mock_llm.queue(LLMResponse(content="Sure thing.", finish_reason="stop"))

    ctx = await _make_ctx(session_maker)

    result = await tasks.process_chat_job(
        ctx,
        agent_id=str(agent_id),
        session_id="sess-default",
        text="What are your hours?",
        metadata={},
        platform="generic",
    )

    assert result["reply"] == "Sure thing."


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


async def _make_ctx(session_maker, settings=None) -> dict[str, Any]:
    return {
        "session_maker": session_maker,
        "embedding_provider": object(),
        "settings": settings or get_settings(),
    }


async def test_process_chat_job_persists_and_reuses_history(session_maker, monkeypatch, mock_llm):
    agent_id = await _seed_agent(session_maker)

    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "build_llm_provider", lambda agent, settings: mock_llm)

    ctx = await _make_ctx(session_maker)

    mock_llm.queue(LLMResponse(content="First answer", finish_reason="stop"))
    await tasks.process_chat_job(
        ctx,
        agent_id=str(agent_id),
        session_id="sess-1",
        text="First question",
        metadata={},
        platform="generic",
    )

    mock_llm.queue(LLMResponse(content="Second answer", finish_reason="stop"))
    await tasks.process_chat_job(
        ctx,
        agent_id=str(agent_id),
        session_id="sess-1",
        text="Second question",
        metadata={},
        platform="generic",
    )

    assert len(mock_llm.calls) == 2
    second_call_messages = mock_llm.calls[1]["messages"]
    # [system, history-user, history-assistant, new-user]
    assert len(second_call_messages) == 4
    assert second_call_messages[1].role == Role.USER
    assert second_call_messages[1].content == "First question"
    assert second_call_messages[2].role == Role.ASSISTANT
    assert second_call_messages[2].content == "First answer"
    assert second_call_messages[3].role == Role.USER
    assert second_call_messages[3].content == "Second question"

    async with session_maker() as session:
        result = await session.execute(
            select(ChatMessage)
            .where(ChatMessage.agent_id == agent_id, ChatMessage.session_id == "sess-1")
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


async def test_process_chat_job_history_scoped_by_session(session_maker, monkeypatch, mock_llm):
    agent_id = await _seed_agent(session_maker)
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "build_llm_provider", lambda agent, settings: mock_llm)

    ctx = await _make_ctx(session_maker)

    mock_llm.queue(LLMResponse(content="Answer A", finish_reason="stop"))
    await tasks.process_chat_job(
        ctx, agent_id=str(agent_id), session_id="sess-a", text="Question A", metadata={}, platform="generic"
    )

    mock_llm.queue(LLMResponse(content="Answer B", finish_reason="stop"))
    await tasks.process_chat_job(
        ctx, agent_id=str(agent_id), session_id="sess-b", text="Question B", metadata={}, platform="generic"
    )

    second_call_messages = mock_llm.calls[1]["messages"]
    # sess-b has no prior turns: just [system, new-user]
    assert len(second_call_messages) == 2
    assert second_call_messages[1].content == "Question B"


async def test_process_chat_job_history_scoped_by_agent(session_maker, monkeypatch, mock_llm):
    agent_a = await _seed_agent(session_maker)
    agent_b = await _seed_agent(session_maker)
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "build_llm_provider", lambda agent, settings: mock_llm)

    ctx = await _make_ctx(session_maker)

    mock_llm.queue(LLMResponse(content="Answer A", finish_reason="stop"))
    await tasks.process_chat_job(
        ctx, agent_id=str(agent_a), session_id="shared-session", text="Question A", metadata={}, platform="generic"
    )

    mock_llm.queue(LLMResponse(content="Answer B", finish_reason="stop"))
    await tasks.process_chat_job(
        ctx, agent_id=str(agent_b), session_id="shared-session", text="Question B", metadata={}, platform="generic"
    )

    second_call_messages = mock_llm.calls[1]["messages"]
    # same session_id but different agent: history must not leak across agents
    assert len(second_call_messages) == 2
    assert second_call_messages[1].content == "Question B"


async def test_process_chat_job_history_truncated_to_limit(session_maker, monkeypatch, mock_llm):
    agent_id = await _seed_agent(session_maker)
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "build_llm_provider", lambda agent, settings: mock_llm)

    settings = get_settings().model_copy(update={"CHAT_HISTORY_LIMIT": 2})
    ctx = await _make_ctx(session_maker, settings=settings)

    for i in range(3):
        mock_llm.queue(LLMResponse(content=f"Answer {i}", finish_reason="stop"))
        await tasks.process_chat_job(
            ctx,
            agent_id=str(agent_id),
            session_id="sess-limit",
            text=f"Question {i}",
            metadata={},
            platform="generic",
        )

    mock_llm.queue(LLMResponse(content="Answer 3", finish_reason="stop"))
    await tasks.process_chat_job(
        ctx,
        agent_id=str(agent_id),
        session_id="sess-limit",
        text="Question 3",
        metadata={},
        platform="generic",
    )

    last_call_messages = mock_llm.calls[-1]["messages"]
    # limit=2 rows -> exactly one prior turn (the most recent one) kept
    assert len(last_call_messages) == 4
    assert last_call_messages[1].content == "Question 2"
    assert last_call_messages[2].content == "Answer 2"
    assert last_call_messages[3].content == "Question 3"


async def test_process_chat_job_does_not_persist_when_agent_raises(session_maker, monkeypatch, mock_llm):
    agent_id = await _seed_agent(session_maker)
    monkeypatch.setattr(tasks, "PgVectorKnowledgeSearcher", _FakeSearcher)
    monkeypatch.setattr(tasks, "build_llm_provider", lambda agent, settings: mock_llm)

    class _ExplodingAgent:
        async def run(self, text, history=None):
            raise RuntimeError("boom")

    async def _fake_build_agent(*args, **kwargs):
        return _ExplodingAgent()

    monkeypatch.setattr(tasks, "build_agent", _fake_build_agent)

    ctx = await _make_ctx(session_maker)

    with pytest.raises(RuntimeError):
        await tasks.process_chat_job(
            ctx,
            agent_id=str(agent_id),
            session_id="sess-err",
            text="What are your hours?",
            metadata={},
            platform="generic",
        )

    async with session_maker() as session:
        rows = list(
            (
                await session.execute(
                    select(ChatMessage).where(
                        ChatMessage.agent_id == agent_id, ChatMessage.session_id == "sess-err"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert rows == []


def _make_agent_row(**overrides) -> Agent:
    defaults = dict(name="x", provider="ollama", model_name="qwen2.5", base_url=None, api_key=None)
    defaults.update(overrides)
    return Agent(**defaults)


def test_build_llm_provider_uses_agent_base_url_over_settings_default():
    settings = get_settings().model_copy(update={"OLLAMA_BASE_URL": "http://settings-default.local"})
    agent = _make_agent_row(provider="ollama", base_url="http://agent-specific.local")
    provider = tasks.build_llm_provider(agent, settings)
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://agent-specific.local"


def test_build_llm_provider_falls_back_to_settings_ollama_base_url():
    settings = get_settings().model_copy(update={"OLLAMA_BASE_URL": "http://ollama.local"})
    agent = _make_agent_row(provider="ollama", base_url=None)
    provider = tasks.build_llm_provider(agent, settings)
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://ollama.local"


def test_build_llm_provider_returns_openai_compat_provider():
    settings = get_settings().model_copy(
        update={"OPENAI_BASE_URL": "http://settings-default.local/v1", "OPENAI_API_KEY": "sk-settings"}
    )
    agent = _make_agent_row(provider="openai", base_url="http://openai.local/v1", api_key="sk-test")
    provider = tasks.build_llm_provider(agent, settings)
    assert isinstance(provider, OpenAICompatProvider)
    assert provider.base_url == "http://openai.local/v1"
    assert provider.api_key == "sk-test"


def test_build_llm_provider_openai_falls_back_to_settings_credentials():
    settings = get_settings().model_copy(
        update={"OPENAI_BASE_URL": "http://settings-default.local/v1", "OPENAI_API_KEY": "sk-settings"}
    )
    agent = _make_agent_row(provider="openai", base_url=None, api_key=None)
    provider = tasks.build_llm_provider(agent, settings)
    assert isinstance(provider, OpenAICompatProvider)
    assert provider.base_url == "http://settings-default.local/v1"
    assert provider.api_key == "sk-settings"


def test_build_llm_provider_raises_on_unknown_provider():
    settings = get_settings()
    agent = _make_agent_row(provider="bogus")
    with pytest.raises(ValueError):
        tasks.build_llm_provider(agent, settings)
