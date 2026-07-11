"""arq job implementations.

Each task delegates all real work to plain, injectable functions so tests
never have to spin up arq/Redis or hit a real LLM/Ollama endpoint. Provider
construction (network clients) is factored into small functions so tests
can monkeypatch them.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent import AgentBuilder, KnowledgeSearchTool
from app.agent.providers.base import EmbeddingProvider, LLMProvider
from app.agent.providers.ollama import OllamaEmbeddingProvider, OllamaProvider
from app.agent.tools.knowledge_search import KnowledgeSearcher
from app.channels.base import OutgoingMessage
from app.channels.registry import ChannelNotRegisteredError, get_channel_registry
from app.core.config import Settings, get_settings
from app.modules.conversation.service import append_turn, load_history
from app.modules.document.pipeline.ingest import ingest_document
from app.modules.domain.models import Domain
from app.modules.domain.service import get_domain
from app.modules.knowledge.searcher import PgVectorKnowledgeSearcher


def build_llm_provider(settings: Settings) -> LLMProvider:
    return OllamaProvider(settings.OLLAMA_BASE_URL)


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    return OllamaEmbeddingProvider(settings.OLLAMA_BASE_URL)


def build_domain_agent(
    domain: Domain,
    *,
    settings: Settings | None = None,
    searcher: KnowledgeSearcher,
    llm: LLMProvider | None = None,
):
    """Assemble the domain-scoped agent. Injectable for tests: pass ``llm``
    (and ``searcher``) to avoid constructing a real network client."""
    settings = settings or get_settings()
    llm = llm or build_llm_provider(settings)

    tool = KnowledgeSearchTool(searcher, domain_id=str(domain.id))

    return (
        AgentBuilder()
        .with_llm(llm)
        .with_model(settings.CHAT_MODEL)
        .with_prompt_template(
            settings.AGENT_SYSTEM_PROMPT_TEMPLATE,
            domain_name=domain.name,
            domain_description=domain.description or "",
        )
        .with_tools([tool])
        .with_max_iterations(settings.AGENT_MAX_ITERATIONS)
        .build()
    )


async def ingest_document_task(ctx: dict[str, Any], document_id: str) -> None:
    session_maker: async_sessionmaker[AsyncSession] = ctx["session_maker"]
    embedding_provider: EmbeddingProvider = ctx["embedding_provider"]
    settings: Settings = ctx["settings"]

    async with session_maker() as session:
        await ingest_document(
            uuid.UUID(document_id),
            session,
            embedding_provider,
            embedding_model=settings.EMBEDDING_MODEL,
        )


async def process_chat_job(
    ctx: dict[str, Any],
    *,
    domain_id: str,
    session_id: str,
    text: str,
    metadata: dict[str, Any],
    platform: str,
) -> dict[str, Any]:
    session_maker: async_sessionmaker[AsyncSession] = ctx["session_maker"]
    embedding_provider: EmbeddingProvider = ctx["embedding_provider"]
    settings: Settings = ctx["settings"]

    domain_uuid = uuid.UUID(domain_id)

    async with session_maker() as session:
        domain = await get_domain(session, domain_uuid)
        history = await load_history(session, domain_uuid, session_id, settings.CHAT_HISTORY_LIMIT)

    searcher = PgVectorKnowledgeSearcher(session_maker, embedding_provider, settings.EMBEDDING_MODEL)
    agent = build_domain_agent(domain, settings=settings, searcher=searcher)

    response = await agent.run(text, history=history)

    async with session_maker() as session:
        await append_turn(session, domain_uuid, session_id, text, response.content)

    registry = get_channel_registry()
    try:
        adapter = registry.get(platform)
    except ChannelNotRegisteredError:
        adapter = None
    if adapter is not None:
        await adapter.send_response(OutgoingMessage(session_id=session_id, text=response.content, metadata=metadata))

    return {
        "reply": response.content,
        "session_id": session_id,
        "iterations": response.iterations,
        "stopped_on": response.stopped_on,
    }
