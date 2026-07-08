"""Orchestrates the full ingestion pipeline for one document.

This function is what the arq worker task calls; it has no dependency on
arq/redis itself so it stays easy to unit test.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.providers.base import EmbeddingProvider
from app.core.config import get_settings
from app.modules.document import service
from app.modules.document.models import Document, DocumentChunk, DocumentStatus
from app.modules.document.pipeline.chunk import chunk_text
from app.modules.document.pipeline.embed import embed_chunks
from app.modules.document.pipeline.extract import extract_text


async def ingest_document(
    document_id: uuid.UUID,
    session: AsyncSession,
    embedding_provider: EmbeddingProvider,
    *,
    embedding_model: str | None = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    batch_size: int = 16,
) -> Document:
    """Extract, chunk, embed and persist chunks for ``document_id``.

    Transitions status: pending -> processing -> completed, or -> failed
    with ``error`` populated if any step raises.
    """
    document = await session.get(Document, document_id)
    if document is None:
        raise service.DocumentNotFoundError(str(document_id))

    settings = get_settings()
    model = embedding_model or settings.EMBEDDING_MODEL

    document.status = DocumentStatus.PROCESSING.value
    document.error = None
    await session.commit()

    try:
        extension = _extension(document.filename)
        path = service.file_path_for(document.id, extension)
        text = extract_text(str(path), document.mime_type)
        chunks = chunk_text(text, size=chunk_size, overlap=chunk_overlap)
        vectors = await embed_chunks(chunks, embedding_provider, model, batch_size=batch_size)

        for index, (content, vector) in enumerate(zip(chunks, vectors)):
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=content,
                    embedding=vector,
                )
            )

        document.status = DocumentStatus.COMPLETED.value
        await session.commit()
    except Exception as exc:  # noqa: BLE001 - persist failure state then re-raise
        await session.rollback()
        document = await session.get(Document, document_id)
        document.status = DocumentStatus.FAILED.value
        document.error = str(exc)
        await session.commit()

    await session.refresh(document)
    return document


def _extension(filename: str) -> str:
    import os

    return os.path.splitext(filename)[1].lower()
