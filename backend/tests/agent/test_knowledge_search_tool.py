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


HR_DOMAIN = {"id": "domain-123", "slug": "hr", "name": "HR Policies"}
SALES_DOMAIN = {"id": "domain-456", "slug": "sales", "name": "Sales Playbook"}


async def test_returns_formatted_hits_scoped_to_domain():
    hits = [
        KnowledgeHit(content="Vacation policy is 20 days.", score=0.9, metadata={"source": "hr.md"}),
        KnowledgeHit(content="Sick leave is 10 days.", score=0.8, metadata={"source": "hr.md"}),
    ]
    searcher = FakeSearcher(hits)
    tool = KnowledgeSearchTool(searcher=searcher, domains=[HR_DOMAIN], limit=5)

    assert tool.name == "knowledge_search"
    assert tool.input_schema["required"] == ["query"]

    result = await tool.execute(query="vacation days")

    assert "Vacation policy is 20 days." in result
    assert "Sick leave is 10 days." in result
    assert searcher.calls == [{"query": "vacation days", "domain_id": "domain-123", "limit": 5}]


async def test_empty_results_returns_no_results_message():
    searcher = FakeSearcher([])
    tool = KnowledgeSearchTool(searcher=searcher, domains=[HR_DOMAIN], limit=5)

    result = await tool.execute(query="unknown topic")

    assert "NO_RESULTS" in result or "no results" in result.lower()
    assert searcher.calls[0]["domain_id"] == "domain-123"


async def test_default_limit_is_five():
    searcher = FakeSearcher([])
    tool = KnowledgeSearchTool(searcher=searcher, domains=[HR_DOMAIN])
    await tool.execute(query="x")
    assert searcher.calls[0]["limit"] == 5


def test_to_definition_shape():
    searcher = FakeSearcher([])
    tool = KnowledgeSearchTool(searcher=searcher, domains=[HR_DOMAIN])
    definition = tool.to_definition()
    assert definition["name"] == "knowledge_search"
    assert "description" in definition
    assert definition["input_schema"]["properties"]["query"]["type"] == "string"


def test_single_domain_schema_has_no_domain_param():
    searcher = FakeSearcher([])
    tool = KnowledgeSearchTool(searcher=searcher, domains=[HR_DOMAIN])

    schema = tool.input_schema

    assert "domain" not in schema["properties"]
    assert schema["required"] == ["query"]


def test_multi_domain_schema_has_domain_enum():
    searcher = FakeSearcher([])
    tool = KnowledgeSearchTool(searcher=searcher, domains=[HR_DOMAIN, SALES_DOMAIN])

    schema = tool.input_schema

    assert set(schema["properties"]["domain"]["enum"]) == {"hr", "sales"}
    assert schema["required"] == ["query", "domain"]


async def test_multi_domain_execute_with_valid_domain_searches_correct_id():
    hits = [KnowledgeHit(content="Q3 targets.", score=0.7, metadata={})]
    searcher = FakeSearcher(hits)
    tool = KnowledgeSearchTool(searcher=searcher, domains=[HR_DOMAIN, SALES_DOMAIN])

    result = await tool.execute(query="targets", domain="sales")

    assert "Q3 targets." in result
    assert searcher.calls == [{"query": "targets", "domain_id": "domain-456", "limit": 5}]


async def test_multi_domain_execute_with_missing_domain_returns_helpful_string():
    searcher = FakeSearcher([])
    tool = KnowledgeSearchTool(searcher=searcher, domains=[HR_DOMAIN, SALES_DOMAIN])

    result = await tool.execute(query="targets")

    assert searcher.calls == []
    assert "domain" in result.lower()
    assert "hr" in result
    assert "sales" in result


async def test_multi_domain_execute_with_invalid_domain_returns_helpful_string():
    searcher = FakeSearcher([])
    tool = KnowledgeSearchTool(searcher=searcher, domains=[HR_DOMAIN, SALES_DOMAIN])

    result = await tool.execute(query="targets", domain="marketing")

    assert searcher.calls == []
    assert "domain" in result.lower()


async def test_multi_domain_execute_only_searches_relevant_single_domain():
    hits = [KnowledgeHit(content="Vacation policy is 20 days.", score=0.9, metadata={})]
    searcher = FakeSearcher(hits)
    tool = KnowledgeSearchTool(searcher=searcher, domains=[HR_DOMAIN, SALES_DOMAIN])

    result = await tool.execute(query="vacation days", domain="hr")

    assert "Vacation policy is 20 days." in result
    assert len(searcher.calls) == 1
    assert searcher.calls[0]["domain_id"] == "domain-123"
