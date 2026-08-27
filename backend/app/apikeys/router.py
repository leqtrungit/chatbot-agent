"""REST endpoints for API keys management (FR-T4, NFR-SEC2)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.apikeys import service
from app.apikeys.schemas import ApiKeyCreate, ApiKeyCreateResponse, ApiKeyRead
from app.core.db import get_session
from app.identity.org_access import OrgContext, require_org_access

router = APIRouter(
    prefix="/v2/orgs/{org_id}/api-keys",
    tags=["api-keys"],
)


@router.post(
    "",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    org_id: uuid.UUID,
    data: ApiKeyCreate,
    ctx: OrgContext = Depends(require_org_access),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyCreateResponse:
    """Create a new API key for the organization.

    The raw key (cba_ + 32 hex chars) is returned once in the response.
    Only the SHA-256 hash is stored in the database.

    **Parameters:**
    - `org_id`: Organization UUID (from path)
    - `name`: Key name (required)
    - `rate_limit_per_minute`: Optional rate limit

    **Returns (201):**
    - `id`: Key UUID
    - `name`: Key name
    - `key`: Raw key (shown ONCE only)
    - `rate_limit_per_minute`: Rate limit if set
    - `created_at`: Creation timestamp

    **Security:** Requires tenant admin in the specified org.
    """
    api_key, raw_key = await service.create_api_key(session, org_id, data)
    return ApiKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        rate_limit_per_minute=api_key.rate_limit_per_minute,
        created_at=api_key.created_at,
    )


@router.get(
    "",
    response_model=list[ApiKeyRead],
)
async def list_api_keys(
    org_id: uuid.UUID,
    ctx: OrgContext = Depends(require_org_access),
    session: AsyncSession = Depends(get_session),
) -> list[ApiKeyRead]:
    """List all API keys for the organization.

    The list never includes raw keys or key hashes (only IDs, names, timestamps).

    **Returns (200):**
    - List of API keys without sensitive data

    **Security:** Requires tenant admin in the specified org (org_id path param).
    """
    api_keys = await service.list_api_keys(session, org_id)
    return [ApiKeyRead.model_validate(k) for k in api_keys]


@router.post(
    "/{key_id}/revoke",
    response_model=ApiKeyRead,
)
async def revoke_api_key(
    org_id: uuid.UUID,
    key_id: uuid.UUID,
    ctx: OrgContext = Depends(require_org_access),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyRead:
    """Revoke an API key (idempotent).

    Sets the `revoked_at` timestamp. If already revoked, this is a no-op.
    Revocation takes effect within 60 seconds via cache TTL (NFR-SEC2).

    **Parameters:**
    - `org_id`: Organization UUID (from path)
    - `key_id`: API key UUID to revoke

    **Returns (200):**
    - Updated key with `revoked_at` set

    **Errors:**
    - 404: Key not found in this org
    - 403: Org suspended

    **Security:** Requires tenant admin in the specified org (org_id path param).
    """
    try:
        api_key = await service.revoke_api_key(session, org_id, key_id)
    except service.ApiKeyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    return ApiKeyRead.model_validate(api_key)
