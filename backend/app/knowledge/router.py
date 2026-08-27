"""REST endpoints for knowledge bases and documents (FR-A2, M0-T7)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.identity.org_access import OrgContext, require_org_access
from app.knowledge import service
from app.knowledge.schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
    DocumentRead,
)
from app.knowledge.storage import UnsupportedFileTypeError


def get_knowledge_router() -> APIRouter:
    """Create the knowledge bases router with org-scoped endpoints."""
    router = APIRouter(
        prefix="/v2/orgs/{org_id}/knowledge-bases",
        tags=["knowledge-bases"],
        dependencies=[Depends(require_org_access)],
    )

    # ========================================================================
    # Knowledge Base CRUD
    # ========================================================================

    @router.get("", response_model=list[KnowledgeBaseRead])
    async def list_knowledge_bases(
        org_context: OrgContext = Depends(require_org_access),
        session: AsyncSession = Depends(get_session),
    ) -> list[KnowledgeBaseRead]:
        """List all knowledge bases for the org.

        GET /v2/orgs/{org_id}/knowledge-bases
        """
        kbs = await service.list_knowledge_bases(session, org_context.org.id)
        return [KnowledgeBaseRead.model_validate(kb) for kb in kbs]

    @router.post("", response_model=KnowledgeBaseRead, status_code=status.HTTP_201_CREATED)
    async def create_knowledge_base(
        org_context: OrgContext = Depends(require_org_access),
        data: KnowledgeBaseCreate = ...,
        session: AsyncSession = Depends(get_session),
    ) -> KnowledgeBaseRead:
        """Create a new knowledge base.

        POST /v2/orgs/{org_id}/knowledge-bases
        """
        try:
            kb = await service.create_knowledge_base(session, org_context.org.id, data)
        except service.KnowledgeBaseConflictError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return KnowledgeBaseRead.model_validate(kb)

    @router.get("/{kb_id}", response_model=KnowledgeBaseRead)
    async def get_knowledge_base(
        kb_id: uuid.UUID,
        org_context: OrgContext = Depends(require_org_access),
        session: AsyncSession = Depends(get_session),
    ) -> KnowledgeBaseRead:
        """Get a specific knowledge base by ID.

        GET /v2/orgs/{org_id}/knowledge-bases/{kb_id}
        """
        try:
            kb = await service.get_knowledge_base(session, org_context.org.id, kb_id)
        except service.KnowledgeBaseNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
            ) from None
        return KnowledgeBaseRead.model_validate(kb)

    @router.put("/{kb_id}", response_model=KnowledgeBaseRead)
    async def update_knowledge_base(
        kb_id: uuid.UUID,
        org_context: OrgContext = Depends(require_org_access),
        data: KnowledgeBaseUpdate = ...,
        session: AsyncSession = Depends(get_session),
    ) -> KnowledgeBaseRead:
        """Update a knowledge base.

        PUT /v2/orgs/{org_id}/knowledge-bases/{kb_id}
        """
        try:
            kb = await service.update_knowledge_base(session, org_context.org.id, kb_id, data)
        except service.KnowledgeBaseNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
            ) from None
        except service.KnowledgeBaseConflictError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return KnowledgeBaseRead.model_validate(kb)

    @router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_knowledge_base(
        kb_id: uuid.UUID,
        org_context: OrgContext = Depends(require_org_access),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        """Delete a knowledge base (cascades to documents).

        DELETE /v2/orgs/{org_id}/knowledge-bases/{kb_id}
        """
        try:
            await service.delete_knowledge_base(session, org_context.org.id, kb_id)
        except service.KnowledgeBaseNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
            ) from None

    # ========================================================================
    # Document upload/list/detail/delete
    # ========================================================================

    @router.post(
        "/{kb_id}/documents",
        response_model=DocumentRead,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def upload_document(
        kb_id: uuid.UUID,
        file: UploadFile,
        org_context: OrgContext = Depends(require_org_access),
        session: AsyncSession = Depends(get_session),
    ) -> DocumentRead:
        """Upload a document to a knowledge base.

        POST /v2/orgs/{org_id}/knowledge-bases/{kb_id}/documents
        Multipart form: file (PDF, DOCX, TXT, MD)
        Response: 202 ACCEPTED with Document (status=pending, no ingestion yet)
        """
        content = await file.read()
        mime_type = file.content_type or "application/octet-stream"

        try:
            doc = await service.create_document(
                session,
                org_context.org.id,
                kb_id,
                file.filename or "upload",
                content,
                mime_type,
            )
        except service.KnowledgeBaseNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
            ) from None
        except UnsupportedFileTypeError as exc:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
            ) from exc

        return DocumentRead.model_validate(doc)

    @router.get("/{kb_id}/documents", response_model=list[DocumentRead])
    async def list_documents(
        kb_id: uuid.UUID,
        org_context: OrgContext = Depends(require_org_access),
        session: AsyncSession = Depends(get_session),
    ) -> list[DocumentRead]:
        """List documents in a knowledge base.

        GET /v2/orgs/{org_id}/knowledge-bases/{kb_id}/documents
        """
        # Note: We don't validate KB existence here; empty list is valid
        docs = await service.list_documents(session, org_context.org.id, kb_id)
        return [DocumentRead.model_validate(doc) for doc in docs]

    # NOTE: document detail/delete are nested under /{kb_id}/documents/... —
    # a flat "/documents/{doc_id}" would be shadowed by the earlier
    # "/{kb_id}" route ("documents" parses as kb_id → 422, unreachable).
    @router.get("/{kb_id}/documents/{doc_id}", response_model=DocumentRead)
    async def get_document(
        kb_id: uuid.UUID,
        doc_id: uuid.UUID,
        org_context: OrgContext = Depends(require_org_access),
        session: AsyncSession = Depends(get_session),
    ) -> DocumentRead:
        """Get a specific document by ID.

        GET /v2/orgs/{org_id}/knowledge-bases/{kb_id}/documents/{doc_id}
        """
        try:
            doc = await service.get_document(session, org_context.org.id, doc_id)
        except service.DocumentNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            ) from None
        if doc.knowledge_base_id != kb_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )
        return DocumentRead.model_validate(doc)

    @router.delete("/{kb_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_document(
        kb_id: uuid.UUID,
        doc_id: uuid.UUID,
        org_context: OrgContext = Depends(require_org_access),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        """Delete a document and its file.

        DELETE /v2/orgs/{org_id}/knowledge-bases/{kb_id}/documents/{doc_id}
        """
        try:
            doc = await service.get_document(session, org_context.org.id, doc_id)
            if doc.knowledge_base_id != kb_id:
                raise service.DocumentNotFoundError(str(doc_id))
            await service.delete_document(session, org_context.org.id, doc_id)
        except service.DocumentNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            ) from None

    return router


# Module-level router for backwards compatibility if needed
router = get_knowledge_router()
