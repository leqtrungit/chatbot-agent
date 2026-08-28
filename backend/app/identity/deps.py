"""FastAPI dependencies for security verification."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from jwt import PyJWTError

from app.core.config import get_settings, Settings
from app.core.security import (
    JWKSVerifier,
    OperatorPrincipal,
    TenantPrincipal,
    extract_principal,
    MultipleOrgsError,
    UnauthorizedPrincipalError,
)


async def get_jwks_verifier(request: Request) -> JWKSVerifier:
    """Get JWKSVerifier instance from app state.

    Falls back to creating one if not in state (useful for testing).
    """
    if not hasattr(request.app.state, "jwks_verifier"):
        # Create verifier on demand (for testing)
        settings = get_settings()
        verifier = JWKSVerifier()
        verifier.set_jwks_url(settings.keycloak_jwks_url)
        request.app.state.jwks_verifier = verifier

    return request.app.state.jwks_verifier


async def authenticated_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> OperatorPrincipal | TenantPrincipal:
    """FastAPI dependency to verify authentication (operator or tenant).

    Validates JWT token from Authorization header and extracts either
    OperatorPrincipal or TenantPrincipal. This is the single seam shared by
    every role-checking dependency below (`require_operator`,
    `require_org_member`); they differ only in the role check applied to
    the principal this returns.

    Args:
        request: FastAPI request object.
        authorization: Authorization header (Bearer token).

    Returns:
        OperatorPrincipal or TenantPrincipal if token is valid.

    Raises:
        HTTPException: 401 if token is missing or invalid; 403 if unauthorized.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    # Extract Bearer token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")

    token = parts[1]
    settings = get_settings()
    verifier = await get_jwks_verifier(request)

    try:
        claims = await verifier.verify_async(
            token,
            issuer=settings.keycloak_issuer,
            audience=settings.keycloak_audience,
            jwks_url=settings.keycloak_jwks_url,
        )
    except PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    try:
        principal = extract_principal(claims, settings)
    except (MultipleOrgsError, UnauthorizedPrincipalError) as e:
        raise HTTPException(status_code=403, detail=str(e))

    return principal


async def require_operator(
    principal: OperatorPrincipal | TenantPrincipal = Depends(authenticated_principal),
) -> OperatorPrincipal:
    """FastAPI dependency to verify operator access.

    Args:
        principal: Authenticated principal (from `authenticated_principal`).

    Returns:
        OperatorPrincipal if the caller is an operator.

    Raises:
        HTTPException: 401 if token is missing or invalid (raised by
            `authenticated_principal`); 403 if not operator.
    """
    if not isinstance(principal, OperatorPrincipal):
        raise HTTPException(status_code=403, detail="Operator role required")

    return principal


async def require_org_member(
    principal: OperatorPrincipal | TenantPrincipal = Depends(authenticated_principal),
) -> TenantPrincipal:
    """FastAPI dependency to verify tenant/org member access.

    Note:
        Organization ID path parameter matching, and the suspended-org
        check, live in `require_org_access` (app/identity/org_access.py).

    Args:
        principal: Authenticated principal (from `authenticated_principal`).

    Returns:
        TenantPrincipal if the caller belongs to an organization.

    Raises:
        HTTPException: 401 if token is missing or invalid (raised by
            `authenticated_principal`); 403 if not org member or is operator only.
    """
    # Ensure it's a tenant principal (not operator)
    if isinstance(principal, OperatorPrincipal):
        raise HTTPException(status_code=403, detail="Organization member access required")

    if not isinstance(principal, TenantPrincipal):
        raise HTTPException(status_code=403, detail="Invalid principal type")

    return principal


# Alias: GET /v2/me accepts either principal type, so it depends directly on
# `authenticated_principal` with no additional role check of its own. Kept as
# a separate name for readability at the call site.
require_any_principal = authenticated_principal
