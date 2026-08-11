from __future__ import annotations

from app.agent.core.types import Role
from app.modules.conversation.schemas import HistoryItemIn
from app.modules.conversation.service import messages_from_history_items


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
