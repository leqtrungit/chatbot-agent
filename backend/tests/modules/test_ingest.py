from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.modules.document import service
from app.modules.document.models import Document, DocumentChunk, DocumentStatus
from app.modules.document.pipeline.ingest import ingest_document
from app.modules.domain.models import Domain


async def _make_document(db_session, *, filename="notes.txt", content=b"hello world " * 200):
    domain = Domain(name="Ingest Domain", slug="ingest-domain")
    db_session.add(domain)
    await db_session.commit()
    await db_session.refresh(domain)

    document = Document(
        domain_id=domain.id,
        filename=filename,
        mime_type="text/plain",
        status=DocumentStatus.PENDING.value,
    )
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)

    path = service.file_path_for(document.id, ".txt")
    path.write_bytes(content)
    return document, path


async def test_ingest_document_success(db_session, mock_embedding):
    document, path = await _make_document(db_session)
    try:
        result = await ingest_document(
            document.id, db_session, mock_embedding, embedding_model="nomic-embed-text"
        )
        assert result.status == DocumentStatus.COMPLETED.value
        assert result.error is None

        chunks = (
            await db_session.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == document.id)
            )
        ).scalars().all()
        assert len(chunks) > 0
        assert all(len(c.embedding) == mock_embedding.dim for c in chunks)
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    finally:
        path.unlink(missing_ok=True)


async def test_ingest_document_failure_sets_status_failed(db_session, mock_embedding):
    document, path = await _make_document(db_session)
    # remove file so extraction fails
    path.unlink()

    result = await ingest_document(
        document.id, db_session, mock_embedding, embedding_model="nomic-embed-text"
    )
    assert result.status == DocumentStatus.FAILED.value
    assert result.error is not None


async def test_ingest_document_not_found_raises(db_session, mock_embedding):
    with pytest.raises(service.DocumentNotFoundError):
        await ingest_document(uuid.uuid4(), db_session, mock_embedding)
