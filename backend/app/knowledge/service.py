"""Business logic for knowledge bases and documents."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.tenancy import OrgScopedRepo, org_query
from app.knowledge.models import KnowledgeBase, Document, DocumentStatus
from app.knowledge.schemas import KnowledgeBaseCreate, KnowledgeBaseUpdate
from app.knowledge.storage import storage_path_for, validate_file_type, UnsupportedFileTypeError


class KnowledgeBaseNotFoundError(Exception):
    """Raised when a knowledge base is not found."""

    pass


class KnowledgeBaseConflictError(Exception):
    """Raised when a knowledge base conflicts (duplicate name/slug in org)."""

    pass


class DocumentNotFoundError(Exception):
    """Raised when a document is not found."""

    pass


def slugify(value: str) -> str:
    """Generate a URL-friendly slug from a name.

    Args:
        value: Human-readable name.

    Returns:
        Lowercase, hyphen-separated slug.
    """
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "knowledge-base"


async def _check_kb_conflict(
    session: AsyncSession, org_id: uuid.UUID, name: str, slug: str, exclude_id: uuid.UUID | None = None
) -> None:
    """Check if KB with same name/slug already exists in this org.

    Args:
        session: Async SQLAlchemy session.
        org_id: Organization UUID.
        name: KB name.
        slug: KB slug.
        exclude_id: ID to exclude from check (for updates).

    Raises:
        KnowledgeBaseConflictError: If conflict detected.
    """
    stmt = org_query(KnowledgeBase, org_id).where(
        (KnowledgeBase.name == name) | (KnowledgeBase.slug == slug)
    )
    # Exclude the specified ID in the query itself; when multiple rows match,
    # .first() order is undefined, so post-filter would silently miss conflicts.
    if exclude_id is not None:
        stmt = stmt.where(KnowledgeBase.id != exclude_id)
    result = await session.execute(stmt)
    existing = result.scalars().first()
    if existing is not None:
        raise KnowledgeBaseConflictError(
            f"Knowledge base with name '{name}' or slug '{slug}' already exists in this organization"
        )


async def list_knowledge_bases(session: AsyncSession, org_id: uuid.UUID) -> list[KnowledgeBase]:
    """List all knowledge bases for an org.

    Args:
        session: Async SQLAlchemy session.
        org_id: Organization UUID.

    Returns:
        List of KnowledgeBases.
    """
    stmt = org_query(KnowledgeBase, org_id).order_by(KnowledgeBase.created_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_knowledge_base(
    session: AsyncSession, org_id: uuid.UUID, kb_id: uuid.UUID
) -> KnowledgeBase:
    """Get a knowledge base by ID within org scope.

    Args:
        session: Async SQLAlchemy session.
        org_id: Organization UUID.
        kb_id: Knowledge base UUID.

    Returns:
        KnowledgeBase.

    Raises:
        KnowledgeBaseNotFoundError: If KB not found or doesn't belong to org.
    """
    kb = await OrgScopedRepo(session, org_id).get(KnowledgeBase, kb_id)
    if kb is None:
        raise KnowledgeBaseNotFoundError(str(kb_id))
    return kb


async def create_knowledge_base(
    session: AsyncSession, org_id: uuid.UUID, data: KnowledgeBaseCreate
) -> KnowledgeBase:
    """Create a new knowledge base.

    Args:
        session: Async SQLAlchemy session.
        org_id: Organization UUID.
        data: KB creation data.

    Returns:
        Created KnowledgeBase.

    Raises:
        KnowledgeBaseConflictError: If name/slug conflict in org.
    """
    slug = data.slug or slugify(data.name)
    await _check_kb_conflict(session, org_id, data.name, slug)

    kb = KnowledgeBase(
        id=uuid.uuid4(),
        org_id=org_id,
        name=data.name,
        slug=slug,
        description=data.description,
    )
    session.add(kb)
    await session.commit()
    return await get_knowledge_base(session, org_id, kb.id)


async def update_knowledge_base(
    session: AsyncSession, org_id: uuid.UUID, kb_id: uuid.UUID, data: KnowledgeBaseUpdate
) -> KnowledgeBase:
    """Update a knowledge base.

    Args:
        session: Async SQLAlchemy session.
        org_id: Organization UUID.
        kb_id: Knowledge base UUID.
        data: KB update data.

    Returns:
        Updated KnowledgeBase.

    Raises:
        KnowledgeBaseNotFoundError: If KB not found.
        KnowledgeBaseConflictError: If update causes name/slug conflict in org.
    """
    kb = await get_knowledge_base(session, org_id, kb_id)
    new_name = data.name if data.name is not None else kb.name
    new_slug = data.slug if data.slug is not None else kb.slug
    await _check_kb_conflict(session, org_id, new_name, new_slug, exclude_id=kb.id)

    kb.name = new_name
    kb.slug = new_slug
    if data.description is not None:
        kb.description = data.description
    await session.commit()
    return await get_knowledge_base(session, org_id, kb.id)


async def delete_knowledge_base(
    session: AsyncSession, org_id: uuid.UUID, kb_id: uuid.UUID
) -> None:
    """Delete a knowledge base (cascades to documents).

    Args:
        session: Async SQLAlchemy session.
        org_id: Organization UUID.
        kb_id: Knowledge base UUID.

    Raises:
        KnowledgeBaseNotFoundError: If KB not found.
    """
    kb = await get_knowledge_base(session, org_id, kb_id)
    await session.delete(kb)
    await session.commit()


async def list_documents(
    session: AsyncSession, org_id: uuid.UUID, kb_id: uuid.UUID
) -> list[Document]:
    """List all documents in a knowledge base.

    Args:
        session: Async SQLAlchemy session.
        org_id: Organization UUID.
        kb_id: Knowledge base UUID.

    Returns:
        List of Documents.
    """
    stmt = (
        org_query(Document, org_id)
        .where(Document.knowledge_base_id == kb_id)
        .order_by(Document.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_document(
    session: AsyncSession, org_id: uuid.UUID, doc_id: uuid.UUID
) -> Document:
    """Get a document by ID within org scope.

    Args:
        session: Async SQLAlchemy session.
        org_id: Organization UUID.
        doc_id: Document UUID.

    Returns:
        Document.

    Raises:
        DocumentNotFoundError: If document not found or doesn't belong to org.
    """
    doc = await OrgScopedRepo(session, org_id).get(Document, doc_id)
    if doc is None:
        raise DocumentNotFoundError(str(doc_id))
    return doc


async def create_document(
    session: AsyncSession,
    org_id: uuid.UUID,
    kb_id: uuid.UUID,
    filename: str,
    content: bytes,
    mime_type: str = "application/octet-stream",
) -> Document:
    """Create and store a document (file upload).

    Creates a Document row with status=pending (no ingestion in M0; TODO: M1).
    Stores the file at backend/data/uploads/{org_id}/{doc_id}{ext}.

    Args:
        session: Async SQLAlchemy session.
        org_id: Organization UUID.
        kb_id: Knowledge base UUID.
        filename: Original filename.
        content: File bytes.
        mime_type: MIME type from HTTP Content-Type.

    Returns:
        Created Document.

    Raises:
        KnowledgeBaseNotFoundError: If KB doesn't exist in org.
        UnsupportedFileTypeError: If file type not allowed.
    """
    # Verify KB exists and belongs to org
    await get_knowledge_base(session, org_id, kb_id)

    # Validate file type
    try:
        canonical_mime_type = validate_file_type(filename, mime_type)
    except UnsupportedFileTypeError:
        raise

    # Create document row with status=pending
    doc = Document(
        id=uuid.uuid4(),
        knowledge_base_id=kb_id,
        org_id=org_id,
        filename=filename,
        mime_type=canonical_mime_type,
        status=DocumentStatus.PENDING.value,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    # Store file on disk
    import os

    extension = os.path.splitext(filename)[1].lower()
    path = storage_path_for(org_id, doc.id, extension)
    path.write_bytes(content)

    # TODO: M1 — Enqueue ingest job (currently no queue; M1 adds arq task)

    return doc


async def delete_document(session: AsyncSession, org_id: uuid.UUID, doc_id: uuid.UUID) -> None:
    """Delete a document and its file (best-effort file deletion).

    Args:
        session: Async SQLAlchemy session.
        org_id: Organization UUID.
        doc_id: Document UUID.

    Raises:
        DocumentNotFoundError: If document not found.
    """
    doc = await get_document(session, org_id, doc_id)

    # Try to delete file (best-effort)
    import os

    extension = os.path.splitext(doc.filename)[1].lower()
    path = storage_path_for(org_id, doc.id, extension)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            # Log and continue; file deletion is best-effort
            pass

    # Delete document row
    await session.delete(doc)
    await session.commit()
