"""Business logic for API keys (FR-T4, NFR-SEC2).

Raw keys have the shape ``cba_<32 hex chars>`` and are only ever returned
to the caller once, at creation time. Only the SHA-256 hash is persisted.

Revocation takes effect within 60 seconds via cache TTL (NFR-SEC2).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.apikeys.models import ApiKey
from app.apikeys.schemas import ApiKeyCreate
from app.core.tenancy import OrgScopedRepo

KEY_PREFIX = "cba_"
KEY_SUFFIX_BYTES = 16  # 16 bytes = 32 hex chars


class ApiKeyNotFoundError(Exception):
    """Raised when an API key is not found."""

    pass


def generate_raw_key() -> str:
    """Generate a new raw API key.

    Format: cba_ + 32 hex chars (16 random bytes)
    """
    suffix = secrets.token_hex(KEY_SUFFIX_BYTES)
    return f"{KEY_PREFIX}{suffix}"


def hash_key(raw_key: str) -> str:
    """Hash a raw key using SHA-256 for storage.

    Args:
        raw_key: The raw key to hash (e.g., cba_abc123...)

    Returns:
        SHA-256 hexdigest.
    """
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def create_api_key(
    session: AsyncSession, org_id: uuid.UUID, data: ApiKeyCreate
) -> tuple[ApiKey, str]:
    """Create a new API key for an organization.

    The raw key is generated and returned once; only the hash is stored.

    Args:
        session: Async SQLAlchemy session.
        org_id: The organization UUID.
        data: ApiKeyCreate schema with name and optional rate_limit_per_minute.

    Returns:
        Tuple of (ApiKey, raw_key) where raw_key is shown only once.
    """
    repo = OrgScopedRepo(session, org_id)
    raw_key = generate_raw_key()
    api_key = ApiKey(
        id=uuid.uuid4(),
        org_id=org_id,
        name=data.name,
        key_hash=hash_key(raw_key),
        rate_limit_per_minute=data.rate_limit_per_minute,
        revoked_at=None,
        created_at=datetime.now(timezone.utc),
    )
    await repo.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return api_key, raw_key


async def list_api_keys(
    session: AsyncSession, org_id: uuid.UUID
) -> list[ApiKey]:
    """List all API keys for an organization.

    The list never includes raw keys or key hashes.

    Args:
        session: Async SQLAlchemy session.
        org_id: The organization UUID.

    Returns:
        List of ApiKey objects (org-scoped).
    """
    repo = OrgScopedRepo(session, org_id)
    return await repo.list(ApiKey)


async def revoke_api_key(
    session: AsyncSession, org_id: uuid.UUID, api_key_id: uuid.UUID
) -> ApiKey:
    """Revoke an API key (idempotent).

    Sets revoked_at timestamp. If already revoked, this is a no-op
    (returns the same object).

    Args:
        session: Async SQLAlchemy session.
        org_id: The organization UUID (for tenancy validation).
        api_key_id: The API key UUID to revoke.

    Returns:
        The updated ApiKey.

    Raises:
        ApiKeyNotFoundError: If key not found in this org.
    """
    repo = OrgScopedRepo(session, org_id)
    api_key = await repo.get(ApiKey, api_key_id)
    if api_key is None:
        raise ApiKeyNotFoundError(str(api_key_id))

    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(api_key)

    return api_key


async def get_active_key_by_hash(
    session: AsyncSession, key_hash: str
) -> ApiKey | None:
    """Get an active (not revoked) API key by its hash.

    This is a **global lookup**, not scoped to an org, because the
    ``require_api_key`` dependency needs to resolve which org owns the key
    before checking the org's status (identity bootstrap, not yet authenticated).

    Exception to tenancy rule (NFR-SEC1): lookup by key_hash is unscoped.
    The caller must verify the org is active after retrieving the key.

    Args:
        session: Async SQLAlchemy session.
        key_hash: The SHA-256 hash of the raw key.

    Returns:
        The ApiKey if found and not revoked, else None.
    """
    from sqlalchemy import select

    stmt = (
        select(ApiKey)
        .where(ApiKey.key_hash == key_hash)
        .where(ApiKey.revoked_at.is_(None))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
