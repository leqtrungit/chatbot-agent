"""FastAPI dependency: authenticate the caller of the public webhook via
``X-API-Key``. Kept separate from ``router.py`` so the webhook module can
import just this dependency without pulling in the admin router."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.modules.apikey import service
from app.modules.apikey.models import ApiKey


async def require_api_key(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ApiKey:
    raw_key = request.headers.get("X-API-Key")
    if not raw_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    api_key = await service.get_active_key_by_raw(session, raw_key)
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key")

    return api_key
