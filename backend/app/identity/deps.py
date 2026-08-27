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


async def require_operator(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> OperatorPrincipal:
    """FastAPI dependency to verify operator access.

    Validates JWT token from Authorization header and extracts OperatorPrincipal.

    Args:
        request: FastAPI request object.
        authorization: Authorization header (Bearer token).

    Returns:
        OperatorPrincipal if token is valid and user is operator.

    Raises:
        HTTPException: 401 if token is missing or invalid; 403 if not operator.
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

    # Ensure it's an operator
    if not isinstance(principal, OperatorPrincipal):
        raise HTTPException(status_code=403, detail="Operator role required")

    return principal


async def require_org_member(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> TenantPrincipal:
    """FastAPI dependency to verify tenant/org member access.

    Validates JWT token from Authorization header and extracts TenantPrincipal.

    Note:
        Organization ID path parameter matching is deferred to T4.
        Suspended org check is deferred to T4 (FR-T1 will populate org.status).

    Args:
        request: FastAPI request object.
        authorization: Authorization header (Bearer token).

    Returns:
        TenantPrincipal if token is valid and user belongs to an organization.

    Raises:
        HTTPException: 401 if token is missing or invalid; 403 if not org member or is operator only.
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

    # Ensure it's a tenant principal (not operator)
    if isinstance(principal, OperatorPrincipal):
        raise HTTPException(status_code=403, detail="Organization member access required")

    if not isinstance(principal, TenantPrincipal):
        raise HTTPException(status_code=403, detail="Invalid principal type")

    # TODO: T4 will add:
    # - Match org_alias to org_id from path parameter
    # - Check if organization is suspended (org.status != 'active')
    # - Return 403 if org is suspended or org_id doesn't match

    return principal
