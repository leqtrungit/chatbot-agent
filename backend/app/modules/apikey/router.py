"""Admin REST endpoints for managing API keys."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import require_admin
from app.modules.apikey import service
from app.modules.apikey.schemas import ApiKeyCreate, ApiKeyCreateResponse, ApiKeyRead

router = APIRouter(
    prefix="/api/api-keys", tags=["api-keys"], dependencies=[Depends(require_admin)]
)


@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: ApiKeyCreate, session: AsyncSession = Depends(get_session)
) -> ApiKeyCreateResponse:
    api_key, raw_key = await service.create_api_key(session, data)
    return ApiKeyCreateResponse(id=api_key.id, name=api_key.name, key=raw_key)


@router.get("", response_model=list[ApiKeyRead])
async def list_api_keys(session: AsyncSession = Depends(get_session)) -> list[ApiKeyRead]:
    api_keys = await service.list_api_keys(session)
    return [ApiKeyRead.model_validate(k) for k in api_keys]


@router.post("/{api_key_id}/revoke", response_model=ApiKeyRead)
async def revoke_api_key(
    api_key_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> ApiKeyRead:
    try:
        api_key = await service.revoke_api_key(session, api_key_id)
    except service.ApiKeyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found") from exc
    return ApiKeyRead.model_validate(api_key)
