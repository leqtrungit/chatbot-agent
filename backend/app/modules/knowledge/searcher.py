"""pgvector-backed implementation of the agent's ``KnowledgeSearcher`` protocol."""

from __future__ import annotations

import uuid
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent import KnowledgeHit
from app.agent.providers.base import EmbeddingProvider
from app.modules.document.models import Document, DocumentChunk, DocumentStatus


class PgVectorKnowledgeSearcher:
    """Embeds the query, then nearest-neighbor searches chunks scoped to a domain."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession],
        embedding_provider: EmbeddingProvider,
        embedding_model: str,
    ):
        self._session_factory = session_factory
        self._embedding_provider = embedding_provider
        self._embedding_model = embedding_model

    async def search(self, query: str, domain_id: str, limit: int = 5) -> list[KnowledgeHit]:
        vectors = await self._embedding_provider.embed([query], model=self._embedding_model)
        vector = vectors[0]

        distance = DocumentChunk.embedding.cosine_distance(vector)
        stmt = (
            select(
                DocumentChunk.content,
                distance.label("distance"),
                DocumentChunk.document_id,
                DocumentChunk.chunk_index,
                Document.filename,
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.domain_id == uuid.UUID(domain_id),
                Document.status == DocumentStatus.COMPLETED.value,
            )
            .order_by(distance)
            .limit(limit)
        )

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            rows = result.all()

        hits: list[KnowledgeHit] = []
        for content, dist, document_id, chunk_index, filename in rows:
            hits.append(
                KnowledgeHit(
                    content=content,
                    score=1.0 - float(dist),
                    metadata={
                        "document_id": str(document_id),
                        "chunk_index": chunk_index,
                        "filename": filename,
                    },
                )
            )
        return hits
