"""Read-only conversation history endpoint.

Lets an integrating client render past turns in its own UI without ever
touching agent config, prompts, or provider details — same ``X-API-Key``
auth as the webhook/chat-stream endpoints that write to this history.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.modules.apikey.deps import require_api_key, resolve_agent_or_404
from app.modules.apikey.models import ApiKey
from app.modules.conversation import service as conversation_service
from app.modules.conversation.schemas import ChatMessageRead, ConversationMessagesRead

conversation_router = APIRouter(tags=["conversations"])

_MAX_LIMIT = 200


@conversation_router.get(
    "/api/conversations/{agent_id}/{session_id}/messages",
    response_model=ConversationMessagesRead,
)
async def list_conversation_messages(
    agent_id: str,
    session_id: str,
    limit: int | None = Query(default=None, ge=1, le=_MAX_LIMIT),
    session: AsyncSession = Depends(get_session),
    api_key: ApiKey = Depends(require_api_key),
) -> ConversationMessagesRead:
    settings = get_settings()
    agent = await resolve_agent_or_404(session, agent_id)

    effective_limit = min(limit or settings.CHAT_HISTORY_LIMIT, _MAX_LIMIT)
    rows = await conversation_service.list_messages(session, agent.id, session_id, effective_limit)

    return ConversationMessagesRead(
        messages=[
            ChatMessageRead(
                role=row.role, content=row.content, created_at=row.created_at, citations=row.citations
            )
            for row in rows
        ]
    )
