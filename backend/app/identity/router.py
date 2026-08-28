"""Identity and authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import OperatorPrincipal, TenantPrincipal
from app.identity.deps import require_any_principal
from app.orgs.models import Organization


router = APIRouter(prefix="/v2", tags=["identity"])


def _build_me_response(
    principal: OperatorPrincipal | TenantPrincipal,
    org: Organization | None = None,
) -> dict:
    """Build response dict for the /v2/me endpoint."""
    if isinstance(principal, OperatorPrincipal):
        return {
            "kind": "operator",
            "user_id": principal.user_id,
            "email": principal.email,
            "org": None,
        }
    elif isinstance(principal, TenantPrincipal):
        return {
            "kind": "tenant",
            "user_id": principal.user_id,
            "email": principal.email,
            "role": principal.role,
            "org": {
                "id": str(org.id),
                "name": org.name,
                "slug": org.slug,
                "status": org.status,
            }
            if org
            else None,
        }
    else:
        raise ValueError(f"Unknown principal type: {type(principal)}")


@router.get("/me")
async def get_me(
    principal: OperatorPrincipal | TenantPrincipal = Depends(require_any_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get authenticated user's identity and organization information.

    For operators: returns operator info with org=null.
    For tenants: resolves their org from the database and returns tenant info with org details.

    Returns:
        - Operator: {"kind": "operator", "user_id": "...", "email": "...", "org": null}
        - Tenant: {"kind": "tenant", "user_id": "...", "email": "...", "role": "admin|owner",
                   "org": {"id": "<uuid>", "name": "...", "slug": "...", "status": "active"}}

    Raises:
        HTTPException: 404 if tenant's org alias doesn't match any organization in DB.
        HTTPException: 403 if tenant's organization is suspended.
        HTTPException: 401 if token is missing or invalid.
    """
    if isinstance(principal, OperatorPrincipal):
        return _build_me_response(principal)

    # Tenant principal - need to resolve org from database
    if isinstance(principal, TenantPrincipal):
        stmt = select(Organization).where(Organization.slug == principal.org_alias)
        result = await session.execute(stmt)
        org = result.scalar_one_or_none()

        if org is None:
            raise HTTPException(
                status_code=404,
                detail=f"Organization with alias '{principal.org_alias}' not found",
            )

        if org.status != "active":
            raise HTTPException(
                status_code=403,
                detail="Organization is suspended or inactive",
            )

        return _build_me_response(principal, org)

    raise HTTPException(status_code=500, detail="Internal server error")
