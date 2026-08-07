"""arq job implementations.

Each task delegates all real work to plain, injectable functions so tests
never have to spin up arq/Redis or hit a real LLM/Ollama endpoint. Provider
construction (network clients) is factored into small functions so tests
can monkeypatch them.
"""

from __future__ import annotations

import json
import uuid
from contextlib import AsyncExitStack
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent import AgentBuilder, KnowledgeSearchTool
from app.agent.providers.base import EmbeddingProvider, LLMProvider
from app.agent.providers.ollama import OllamaEmbeddingProvider, OllamaProvider
from app.agent.providers.openai_compat import OpenAICompatProvider
from app.agent.tools.knowledge_search import KnowledgeSearcher
from app.channels.base import OutgoingMessage
from app.channels.registry import ChannelNotRegisteredError, get_channel_registry
from app.core.config import Settings, get_settings
from app.modules.agent.models import Agent as AgentModel
from app.modules.agent.service import get_agent
from app.modules.conversation.service import append_turn, load_history
from app.modules.document.pipeline.ingest import ingest_document
from app.modules.knowledge.searcher import PgVectorKnowledgeSearcher
from app.modules.mcp.client import build_mcp_tools


def build_llm_provider(agent: AgentModel, settings: Settings) -> LLMProvider:
    if agent.provider == "ollama":
        return OllamaProvider(agent.base_url or settings.OLLAMA_BASE_URL)
    if agent.provider == "openai":
        return OpenAICompatProvider(
            agent.base_url or settings.OPENAI_BASE_URL, agent.api_key or settings.OPENAI_API_KEY
        )
    raise ValueError(f"Unknown provider: {agent.provider!r}")


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    return OllamaEmbeddingProvider(settings.OLLAMA_BASE_URL)


async def build_agent(
    agent: AgentModel,
    *,
    settings: Settings | None = None,
    searcher: KnowledgeSearcher,
    llm: LLMProvider | None = None,
    stack: AsyncExitStack,
):
    """Assemble the agent from a user-managed ``Agent`` config.

    Injectable for tests: pass ``llm`` (and ``searcher``) to avoid
    constructing real network clients. ``stack`` owns the lifetime of any
    MCP server connections opened for ``agent.mcp_servers``; the caller
    closes it once done running the returned agent.
    """
    settings = settings or get_settings()
    llm = llm or build_llm_provider(agent, settings)

    tools = []
    if agent.enable_knowledge_search and agent.domains:
        tools.append(KnowledgeSearchTool(
            searcher,
            domains=[{"id": str(d.id), "slug": d.slug, "name": d.name} for d in agent.domains],
        ))
    tools.extend(await build_mcp_tools(agent.mcp_servers, stack=stack))

    builder = (
        AgentBuilder()
        .with_llm(llm)
        .with_model(agent.model_name)
        .with_tools(tools)
        .with_params(temperature=agent.temperature, top_p=agent.top_p)
        .with_max_iterations(agent.max_iterations)
    )
    if agent.system_prompt:
        builder = builder.with_system_prompt(agent.system_prompt)
    return builder.build()


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
    agent_id: str,
    session_id: str,
    text: str,
    metadata: dict[str, Any],
    platform: str,
) -> dict[str, Any]:
    session_maker: async_sessionmaker[AsyncSession] = ctx["session_maker"]
    embedding_provider: EmbeddingProvider = ctx["embedding_provider"]
    settings: Settings = ctx["settings"]

    async with session_maker() as session:
        agent_row = await get_agent(session, uuid.UUID(agent_id))
        history = await load_history(session, agent_row.id, session_id, settings.CHAT_HISTORY_LIMIT)

    searcher = PgVectorKnowledgeSearcher(session_maker, embedding_provider, settings.EMBEDDING_MODEL)
    async with AsyncExitStack() as stack:
        agent = await build_agent(agent_row, settings=settings, searcher=searcher, stack=stack)
        response = await agent.run(text, history=history)

    async with session_maker() as session:
        await append_turn(session, agent_row.id, session_id, text, response.content)

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


async def process_chat_job_stream(
    ctx: dict[str, Any],
    *,
    agent_id: str,
    session_id: str,
    text: str,
    metadata: dict[str, Any],
    platform: str,
) -> dict[str, Any]:
    """Streaming version of process_chat_job: publishes token deltas to Redis pubsub."""
    session_maker: async_sessionmaker[AsyncSession] = ctx["session_maker"]
    embedding_provider: EmbeddingProvider = ctx["embedding_provider"]
    settings: Settings = ctx["settings"]
    redis = ctx["redis"]
    job_id = ctx["job_id"]

    channel = f"chat:job:{job_id}"

    async with session_maker() as session:
        agent_row = await get_agent(session, uuid.UUID(agent_id))
        history = await load_history(session, agent_row.id, session_id, settings.CHAT_HISTORY_LIMIT)

    searcher = PgVectorKnowledgeSearcher(session_maker, embedding_provider, settings.EMBEDDING_MODEL)

    try:
        async with AsyncExitStack() as stack:
            agent = await build_agent(
                agent_row, settings=settings, searcher=searcher, stack=stack
            )
            response = None
            async for event in agent.run_stream(text, history=history):
                if event.type == "thinking":
                    await redis.publish(channel, json.dumps({"type": "thinking", "delta": event.thinking}))
                elif event.type == "delta":
                    await redis.publish(channel, json.dumps({"type": "token", "delta": event.delta}))
                elif event.type == "final":
                    response = event.response

        # Persist the turn
        async with session_maker() as session:
            await append_turn(session, agent_row.id, session_id, text, response.content)

        # Send response via adapter if registered
        registry = get_channel_registry()
        try:
            adapter = registry.get(platform)
        except ChannelNotRegisteredError:
            adapter = None
        if adapter is not None:
            await adapter.send_response(OutgoingMessage(session_id=session_id, text=response.content, metadata=metadata))

        # Publish done message
        await redis.publish(
            channel,
            json.dumps({
                "type": "done",
                "reply": response.content,
                "session_id": session_id,
                "iterations": response.iterations,
                "stopped_on": response.stopped_on,
            }),
        )

        return {
            "reply": response.content,
            "session_id": session_id,
            "iterations": response.iterations,
            "stopped_on": response.stopped_on,
        }
    except Exception as exc:
        await redis.publish(channel, json.dumps({"type": "error", "message": str(exc)}))
        raise
