"""Domain-scoped knowledge search tool.

The concrete vector-search implementation (pgvector, etc.) lives outside
this package; it only needs to satisfy the :class:`KnowledgeSearcher`
protocol and gets injected by the caller.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.agent.core.types import Citation
from app.agent.prompts.loader import PromptLoader
from app.agent.tools.base import Tool, ToolOutput

NO_RESULTS_MESSAGE = (
    "NO_RESULTS: The knowledge base returned no relevant results for this query."
)

SNIPPET_MAX_CHARS = 300


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

    One tool instance corresponds to one agent run: it holds a per-run
    citation registry (``[n]`` markers minted across every ``execute()``
    call on this instance), so callers must build a fresh instance per
    request rather than reusing one across runs.
    """

    def __init__(
        self,
        searcher: KnowledgeSearcher,
        domains: list[dict[str, str]],
        limit: int = 5,
        prompt_loader: PromptLoader | None = None,
    ):
        self._searcher = searcher
        self._domains = domains
        self._limit = limit
        self._by_source: dict[str, Citation] = {}
        self._next_marker = 1
        self._prompt_fragment = (prompt_loader or PromptLoader()).render("citations")

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

    @property
    def prompt_fragment(self) -> str:
        return self._prompt_fragment

    async def execute(self, **kwargs: Any) -> ToolOutput:
        query = kwargs["query"]

        if len(self._domains) == 1:
            domain_id = self._domains[0]["id"]
        else:
            slug = kwargs.get("domain")
            match = next((d for d in self._domains if d["slug"] == slug), None)
            if match is None:
                valid = ", ".join(sorted(d["slug"] for d in self._domains))
                return ToolOutput(content=f"Error: 'domain' must be one of: {valid}.", citations=[])
            domain_id = match["id"]

        hits = await self._searcher.search(query, domain_id, self._limit)
        if not hits:
            return ToolOutput(content=NO_RESULTS_MESSAGE, citations=[])

        call_citations: list[Citation] = []
        seen_in_call: set[str] = set()
        blocks: list[str] = []
        for hit in hits:
            document_id = hit.metadata.get("document_id")
            if document_id is not None:
                source_id = f"{document_id}:{hit.metadata.get('chunk_index', 0)}"
            else:
                source_id = hit.content

            citation = self._by_source.get(source_id)
            if citation is None:
                citation = Citation(
                    marker=self._next_marker,
                    source_id=source_id,
                    title=hit.metadata.get("filename", ""),
                    snippet=hit.content[:SNIPPET_MAX_CHARS],
                    score=hit.score,
                    metadata=dict(hit.metadata),
                )
                self._next_marker += 1
                self._by_source[source_id] = citation

            if source_id not in seen_in_call:
                seen_in_call.add(source_id)
                call_citations.append(citation)

            if citation.title:
                header = f"[{citation.marker}] {citation.title} (score: {hit.score:.3f})"
            else:
                header = f"[{citation.marker}] (score: {hit.score:.3f})"
            blocks.append(f"{header}\n{hit.content}")

        return ToolOutput(content="\n\n".join(blocks), citations=call_citations)
