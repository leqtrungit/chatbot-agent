"""Fixtures specific to the app.worker test suite."""

from __future__ import annotations

from typing import Any

import pytest

from app.agent import KnowledgeHit
from app.agent.tools.knowledge_search import KnowledgeSearcher

# Reuse the real-Postgres test database fixtures from tests/modules/conftest.py
# (test_engine, session_maker, db_session) instead of duplicating DB setup.
from tests.modules.conftest import (  # noqa: F401
    db_session,
    session_maker,
    test_engine,
)


class FakeSearcher(KnowledgeSearcher):
    """Records calls and returns a scripted list of hits."""

    def __init__(self, hits: list[KnowledgeHit] | None = None):
        self.hits = hits if hits is not None else []
        self.calls: list[dict[str, Any]] = []

    async def search(self, query: str, domain_id: str, limit: int) -> list[KnowledgeHit]:
        self.calls.append({"query": query, "domain_id": domain_id, "limit": limit})
        return self.hits


@pytest.fixture
def fake_searcher() -> FakeSearcher:
    return FakeSearcher()
