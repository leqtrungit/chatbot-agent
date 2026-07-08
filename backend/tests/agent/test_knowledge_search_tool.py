from __future__ import annotations

from typing import Any

from app.agent.tools.knowledge_search import KnowledgeHit, KnowledgeSearchTool


class FakeSearcher:
    def __init__(self, hits: list[KnowledgeHit]):
        self.hits = hits
        self.calls: list[dict[str, Any]] = []

    async def search(self, query: str, domain_id: str, limit: int) -> list[KnowledgeHit]:
        self.calls.append({"query": query, "domain_id": domain_id, "limit": limit})
        return self.hits


async def test_returns_formatted_hits_scoped_to_domain():
    hits = [
        KnowledgeHit(content="Vacation policy is 20 days.", score=0.9, metadata={"source": "hr.md"}),
        KnowledgeHit(content="Sick leave is 10 days.", score=0.8, metadata={"source": "hr.md"}),
    ]
    searcher = FakeSearcher(hits)
    tool = KnowledgeSearchTool(searcher=searcher, domain_id="domain-123", limit=5)

    assert tool.name == "knowledge_search"
    assert tool.input_schema["required"] == ["query"]

    result = await tool.execute(query="vacation days")

    assert "Vacation policy is 20 days." in result
    assert "Sick leave is 10 days." in result
    assert searcher.calls == [{"query": "vacation days", "domain_id": "domain-123", "limit": 5}]


async def test_empty_results_returns_no_results_message():
    searcher = FakeSearcher([])
    tool = KnowledgeSearchTool(searcher=searcher, domain_id="domain-123", limit=5)

    result = await tool.execute(query="unknown topic")

    assert "NO_RESULTS" in result or "no results" in result.lower()
    assert searcher.calls[0]["domain_id"] == "domain-123"


async def test_default_limit_is_five():
    searcher = FakeSearcher([])
    tool = KnowledgeSearchTool(searcher=searcher, domain_id="d1")
    await tool.execute(query="x")
    assert searcher.calls[0]["limit"] == 5


def test_to_definition_shape():
    searcher = FakeSearcher([])
    tool = KnowledgeSearchTool(searcher=searcher, domain_id="d1")
    definition = tool.to_definition()
    assert definition["name"] == "knowledge_search"
    assert "description" in definition
    assert definition["input_schema"]["properties"]["query"]["type"] == "string"
