"""Business logic for documents."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.document.jobs import enqueue_ingest_job
from app.modules.document.models import Document, DocumentChunk, DocumentStatus
from app.modules.domain.models import Domain

ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


class DocumentNotFoundError(Exception):
    pass


class DomainNotFoundError(Exception):
    pass


class UnsupportedFileTypeError(Exception):
    pass


def upload_dir() -> Path:
    settings = get_settings()
    path = Path(settings.UPLOAD_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_path_for(document_id: uuid.UUID, extension: str) -> Path:
    return upload_dir() / f"{document_id}{extension}"


async def list_documents(session: AsyncSession, domain_id: uuid.UUID) -> list[Document]:
    stmt = select(Document).where(Document.domain_id == domain_id).order_by(Document.created_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_document(session: AsyncSession, document_id: uuid.UUID) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError(str(document_id))
    return document


async def create_document(
    session: AsyncSession,
    domain_id: uuid.UUID,
    filename: str,
    content: bytes,
) -> Document:
    domain = await session.get(Domain, domain_id)
    if domain is None:
        raise DomainNotFoundError(str(domain_id))

    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(f"Unsupported file type: {extension}")
    mime_type = ALLOWED_EXTENSIONS[extension]

    document = Document(
        domain_id=domain_id,
        filename=filename,
        mime_type=mime_type,
        status=DocumentStatus.PENDING.value,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)

    path = file_path_for(document.id, extension)
    path.write_bytes(content)

    await enqueue_ingest_job(document.id)

    return document


async def delete_document(session: AsyncSession, document_id: uuid.UUID) -> None:
    document = await get_document(session, document_id)
    extension = os.path.splitext(document.filename)[1].lower()
    path = file_path_for(document.id, extension)
    if path.exists():
        path.unlink()

    await session.execute(
        DocumentChunk.__table__.delete().where(DocumentChunk.document_id == document.id)
    )
    await session.delete(document)
    await session.commit()
