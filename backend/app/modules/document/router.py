"""REST endpoints for documents."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import require_admin
from app.modules.document import service
from app.modules.document.schemas import DocumentRead

router = APIRouter(tags=["documents"], dependencies=[Depends(require_admin)])


@router.post(
    "/api/domains/{domain_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    domain_id: uuid.UUID,
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> DocumentRead:
    content = await file.read()
    try:
        document = await service.create_document(
            session, domain_id, file.filename or "upload", content
        )
    except service.DomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found") from exc
    except service.UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    return DocumentRead.model_validate(document)


@router.get("/api/domains/{domain_id}/documents", response_model=list[DocumentRead])
async def list_documents(
    domain_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[DocumentRead]:
    documents = await service.list_documents(session, domain_id)
    return [DocumentRead.model_validate(d) for d in documents]


@router.get("/api/documents/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> DocumentRead:
    try:
        document = await service.get_document(session, document_id)
    except service.DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found") from exc
    return DocumentRead.model_validate(document)


@router.delete("/api/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> None:
    try:
        await service.delete_document(session, document_id)
    except service.DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found") from exc
