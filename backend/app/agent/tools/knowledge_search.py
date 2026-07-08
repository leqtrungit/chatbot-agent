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
    """Searches a knowledge base scoped to a single domain."""

    def __init__(self, searcher: KnowledgeSearcher, domain_id: str, limit: int = 5):
        self._searcher = searcher
        self._domain_id = domain_id
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
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                }
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs["query"]
        hits = await self._searcher.search(query, self._domain_id, self._limit)
        if not hits:
            return NO_RESULTS_MESSAGE
        lines = [
            f"{i}. {hit.content} (score: {hit.score:.3f})"
            for i, hit in enumerate(hits, start=1)
        ]
        return "\n".join(lines)
