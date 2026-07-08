"""HTTP Basic auth dependency protecting admin endpoints."""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import Settings, get_settings

_security = HTTPBasic()


def require_admin(
    credentials: HTTPBasicCredentials = Depends(_security),
    settings: Settings = Depends(get_settings),
) -> str:
    valid_username = secrets.compare_digest(credentials.username, settings.ADMIN_USERNAME)
    valid_password = secrets.compare_digest(credentials.password, settings.ADMIN_PASSWORD)
    if not (valid_username and valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
