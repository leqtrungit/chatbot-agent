"""Business logic for API keys.

Raw keys have the shape ``cba_<32 hex chars>`` and are only ever returned to
the caller once, at creation time. Only the SHA-256 hash is persisted.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.apikey.models import ApiKey
from app.modules.apikey.schemas import ApiKeyCreate

KEY_PREFIX = "cba_"


class ApiKeyNotFoundError(Exception):
    pass


def generate_raw_key() -> str:
    return f"{KEY_PREFIX}{secrets.token_hex(16)}"


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def create_api_key(session: AsyncSession, data: ApiKeyCreate) -> tuple[ApiKey, str]:
    raw_key = generate_raw_key()
    api_key = ApiKey(
        name=data.name,
        key_hash=hash_key(raw_key),
        key_prefix=raw_key[: len(KEY_PREFIX) + 4],
        rate_limit_per_minute=data.rate_limit_per_minute,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return api_key, raw_key


async def list_api_keys(session: AsyncSession) -> list[ApiKey]:
    result = await session.execute(select(ApiKey).order_by(ApiKey.created_at))
    return list(result.scalars().all())


async def revoke_api_key(session: AsyncSession, api_key_id: uuid.UUID) -> ApiKey:
    api_key = await session.get(ApiKey, api_key_id)
    if api_key is None:
        raise ApiKeyNotFoundError(str(api_key_id))
    api_key.revoked_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(api_key)
    return api_key


async def get_active_key_by_raw(session: AsyncSession, raw_key: str) -> ApiKey | None:
    key_hash = hash_key(raw_key)
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
    result = await session.execute(stmt)
    return result.scalars().first()
