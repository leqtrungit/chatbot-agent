"""Dependencies for API key validation (NFR-SEC2)."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.apikeys import service
from app.apikeys.models import ApiKey
from app.core.db import get_session
from app.orgs.models import Organization


async def require_api_key(
    x_api_key: str | None = Header(None),
    session: AsyncSession = Depends(get_session),
) -> tuple[ApiKey, Organization]:
    """Validate an API key from X-API-Key header and return the key + org.

    This dependency:
    1. Reads X-API-Key header
    2. Computes SHA-256 hash
    3. Looks up the key in the database (global, unscoped)
    4. Returns 401 if missing, invalid, or revoked
    5. Loads the organization and checks its status
    6. Returns 403 if the org is suspended
    7. Returns (ApiKey, Organization) on success

    The global lookup is an exception to tenancy rule (NFR-SEC1): we don't know
    which org owns the key until we retrieve it, so we can't use OrgScopedRepo.
    The caller (this dependency) validates the org is active.

    Args:
        x_api_key: The X-API-Key header value.
        session: Async SQLAlchemy session.

    Returns:
        Tuple of (ApiKey, Organization).

    Raises:
        HTTPException: 401 if key is missing/invalid/revoked, 403 if org suspended.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    # Hash the provided key
    key_hash = service.hash_key(x_api_key)

    # Look up by hash (global, exception to tenancy)
    api_key = await service.get_active_key_by_hash(session, key_hash)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )

    # Load the organization and check status
    org = await session.get(Organization, api_key.org_id)
    if org is None or org.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is suspended or deleted",
        )

    return api_key, org
