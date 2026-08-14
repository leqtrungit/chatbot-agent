from __future__ import annotations

import uuid

import pytest

from sqlalchemy import select

from app.agent.core.types import Role
from app.modules.agent.models import Agent
from app.modules.conversation.models import ChatMessage
from app.modules.conversation.schemas import HistoryItemIn
from app.modules.conversation.service import append_turn, messages_from_history_items


def test_messages_from_history_items_maps_roles() -> None:
    items = [
        HistoryItemIn(role="user", content="First question"),
        HistoryItemIn(role="assistant", content="First answer"),
    ]

    messages = messages_from_history_items(items)

    assert [m.role for m in messages] == [Role.USER, Role.ASSISTANT]
    assert [m.content for m in messages] == ["First question", "First answer"]


def test_messages_from_history_items_empty_list() -> None:
    assert messages_from_history_items([]) == []


async def _seed_agent(db_session) -> uuid.UUID:
    agent = Agent(name=f"Test Agent {uuid.uuid4()}", provider="ollama", model_name="qwen2.5")
    db_session.add(agent)
    await db_session.commit()
    return agent.id


@pytest.mark.usefixtures("db_session")
async def test_append_turn_stores_citations_on_assistant_row_only(db_session) -> None:
    agent_id = await _seed_agent(db_session)
    citations = [
        {"marker": 1, "source_id": "doc-1:0", "title": "handbook.pdf", "snippet": "...", "score": 0.9, "metadata": {}}
    ]

    await append_turn(
        db_session, agent_id, "sess-cit", "What are your hours?", "We are open 9-5. [1]", citations=citations
    )

    result = await db_session.execute(
        select(ChatMessage)
        .where(ChatMessage.agent_id == agent_id, ChatMessage.session_id == "sess-cit")
        .order_by(ChatMessage.created_at, ChatMessage.id)
    )
    rows = list(result.scalars().all())
    assert [r.role for r in rows] == ["user", "assistant"]
    assert rows[0].citations is None
    assert rows[1].citations == citations


@pytest.mark.usefixtures("db_session")
async def test_append_turn_omitting_citations_leaves_both_rows_none(db_session) -> None:
    agent_id = await _seed_agent(db_session)

    await append_turn(db_session, agent_id, "sess-no-cit", "hello", "hi there")

    result = await db_session.execute(
        select(ChatMessage)
        .where(ChatMessage.agent_id == agent_id, ChatMessage.session_id == "sess-no-cit")
        .order_by(ChatMessage.created_at, ChatMessage.id)
    )
    rows = list(result.scalars().all())
    assert [r.citations for r in rows] == [None, None]
