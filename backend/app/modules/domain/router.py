"""REST endpoints for domains."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import require_admin
from app.modules.domain import service
from app.modules.domain.schemas import DomainCreate, DomainRead, DomainUpdate

router = APIRouter(
    prefix="/api/domains", tags=["domains"], dependencies=[Depends(require_admin)]
)


@router.get("", response_model=list[DomainRead])
async def list_domains(session: AsyncSession = Depends(get_session)) -> list[DomainRead]:
    domains = await service.list_domains(session)
    return [DomainRead.model_validate(d) for d in domains]


@router.post("", response_model=DomainRead, status_code=status.HTTP_201_CREATED)
async def create_domain(
    data: DomainCreate, session: AsyncSession = Depends(get_session)
) -> DomainRead:
    try:
        domain = await service.create_domain(session, data)
    except service.DomainConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return DomainRead.model_validate(domain)


@router.get("/{domain_id}", response_model=DomainRead)
async def get_domain(
    domain_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> DomainRead:
    try:
        domain = await service.get_domain(session, domain_id)
    except service.DomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found") from exc
    return DomainRead.model_validate(domain)


@router.put("/{domain_id}", response_model=DomainRead)
async def update_domain(
    domain_id: uuid.UUID,
    data: DomainUpdate,
    session: AsyncSession = Depends(get_session),
) -> DomainRead:
    try:
        domain = await service.update_domain(session, domain_id, data)
    except service.DomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found") from exc
    except service.DomainConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return DomainRead.model_validate(domain)


@router.delete("/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_domain(
    domain_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> None:
    try:
        await service.delete_domain(session, domain_id)
    except service.DomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found") from exc
