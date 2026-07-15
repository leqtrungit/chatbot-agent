"""Load/append chat history for a (domain, session) pair.

Bridges the persisted ``ChatMessage`` rows to the plain ``app.agent`` message
type (``app.agent.core.types.Message``) so the worker can pass history
straight into ``Agent.run(text, history=...)`` without ``app.agent`` ever
knowing about SQLAlchemy.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.core.types import Message, Role
from app.modules.conversation.models import ChatMessage

_ROLE_MAP = {"user": Role.USER, "assistant": Role.ASSISTANT}


async def load_history(
    session: AsyncSession,
    domain_id: uuid.UUID,
    session_id: str,
    limit: int,
) -> list[Message]:
    """Return the last ``limit`` messages for (domain_id, session_id) in
    chronological order, mapped to agent ``Message`` objects."""
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.domain_id == domain_id, ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    rows.reverse()
    return [Message(role=_ROLE_MAP[row.role], content=row.content) for row in rows]


async def append_turn(
    session: AsyncSession,
    domain_id: uuid.UUID,
    session_id: str,
    user_text: str,
    assistant_text: str,
) -> None:
    """Persist the user turn and the agent's final reply as two rows.

    Both rows are inserted in the same transaction, so Postgres' ``now()``
    (stable for the duration of a transaction) would give them an identical
    ``created_at`` and leave ordering to tie-break on the random UUID id.
    Set strictly increasing timestamps client-side instead so
    ``load_history`` reconstructs turns in the right order.
    """
    user_ts = datetime.now(timezone.utc)
    assistant_ts = user_ts + timedelta(microseconds=1)
    session.add_all(
        [
            ChatMessage(
                domain_id=domain_id,
                session_id=session_id,
                role="user",
                content=user_text,
                created_at=user_ts,
            ),
            ChatMessage(
                domain_id=domain_id,
                session_id=session_id,
                role="assistant",
                content=assistant_text,
                created_at=assistant_ts,
            ),
        ]
    )
    await session.commit()
