"""Domain-scoped knowledge search tool.

The concrete vector-search implementation (pgvector, etc.) lives outside
this package; it only needs to satisfy the :class:`KnowledgeSearcher`
protocol and gets injected by the caller.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.agent.tools.base import Tool

NO_RESULTS_MESSAGE = (
    "NO_RESULTS: The knowledge base returned no relevant results for this query."
)


class KnowledgeHit(BaseModel):
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class KnowledgeSearcher(Protocol):
    async def search(self, query: str, domain_id: str, limit: int) -> list[KnowledgeHit]: ...


class KnowledgeSearchTool(Tool):
    """Searches a knowledge base scoped to one or more domains.

    When a single domain is configured, the tool behaves exactly as a
    domain-scoped search (no domain selection surfaced to the LLM). When
    multiple domains are configured, the LLM must pick which domain to
    search via the ``domain`` parameter (identified by slug).
    """

    def __init__(self, searcher: KnowledgeSearcher, domains: list[dict[str, str]], limit: int = 5):
        self._searcher = searcher
        self._domains = domains
        self._limit = limit

    @property
    def name(self) -> str:
        return "knowledge_search"

    @property
    def description(self) -> str:
        return (
            "Search the knowledge base for information relevant to a query. "
            "Always use this before answering domain-specific questions."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        properties: dict[str, Any] = {
            "query": {
                "type": "string",
                "description": "The search query.",
            }
        }
        required = ["query"]

        if len(self._domains) > 1:
            slugs = [d["slug"] for d in self._domains]
            mapping = ", ".join(f"{d['slug']} ({d['name']})" for d in self._domains)
            properties["domain"] = {
                "type": "string",
                "enum": slugs,
                "description": f"Which knowledge domain to search. Available: {mapping}.",
            }
            required = ["query", "domain"]

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs["query"]

        if len(self._domains) == 1:
            domain_id = self._domains[0]["id"]
        else:
            slug = kwargs.get("domain")
            match = next((d for d in self._domains if d["slug"] == slug), None)
            if match is None:
                valid = ", ".join(sorted(d["slug"] for d in self._domains))
                return f"Error: 'domain' must be one of: {valid}."
            domain_id = match["id"]

        hits = await self._searcher.search(query, domain_id, self._limit)
        if not hits:
            return NO_RESULTS_MESSAGE
        lines = [
            f"{i}. {hit.content} (score: {hit.score:.3f})"
            for i, hit in enumerate(hits, start=1)
        ]
        return "\n".join(lines)
