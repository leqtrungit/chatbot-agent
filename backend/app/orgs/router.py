"""REST API endpoints for organization management (operator API, FR-T1)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.db import get_session
from app.identity.deps import require_operator
from app.identity.org_access import OrgContext, require_org_access
from app.core.security import OperatorPrincipal
from app.orgs.kc_admin import KeycloakAdmin, KeycloakAdminError, HttpKeycloakAdmin
from app.orgs.schemas import OrgCreate, OrgRead
from app.orgs.service import create_org, suspend_org, reactivate_org, list_orgs
from app.core.config import get_settings


def get_kc_admin() -> KeycloakAdmin:
    """Get Keycloak Admin client instance."""
    settings = get_settings()
    return HttpKeycloakAdmin(settings)


router = APIRouter(prefix="/v2/operator/orgs", tags=["orgs"])


@router.post("", response_model=OrgRead, status_code=201)
async def create_organization(
    req: OrgCreate,
    principal: OperatorPrincipal = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
    kc: KeycloakAdmin = Depends(get_kc_admin),
) -> OrgRead:
    """Create a new organization.

    Endpoint: POST /v2/operator/orgs

    Creates a Keycloak Organization, then registers it in the database.
    Operator-only access.

    Args:
        req: Organization creation request (name, slug).
        principal: Verified operator principal.
        session: Database session.
        kc: Keycloak Admin client.

    Returns:
        201 Created with organization details.

    Raises:
        HTTPException:
            - 409: Organization name or slug already exists.
            - 500: Keycloak Admin API error.
    """
    try:
        org = await create_org(session, kc, name=req.name, slug=req.slug)
        await session.commit()
        return OrgRead.model_validate(org)
    except IntegrityError as e:
        await session.rollback()
        # Check which constraint failed
        if "uq_organizations_name" in str(e) or "organizations_name_key" in str(e):
            raise HTTPException(status_code=409, detail="Organization name already exists")
        if "uq_organizations_slug" in str(e) or "organizations_slug_key" in str(e):
            raise HTTPException(status_code=409, detail="Organization slug already exists")
        raise HTTPException(status_code=409, detail="Organization already exists")
    except KeycloakAdminError as e:
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Keycloak Admin API error: {str(e)}",
        )


@router.post("/{org_id}/suspend", response_model=OrgRead)
async def suspend_organization(
    org_id: uuid.UUID,
    principal: OperatorPrincipal = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> OrgRead:
    """Suspend an organization.

    Endpoint: POST /v2/operator/orgs/{org_id}/suspend

    Suspends an organization, which causes all tenant requests to be rejected
    (checked in require_org_member -> require_org_access).
    Operator-only access.

    Args:
        org_id: Organization ID to suspend.
        principal: Verified operator principal.
        session: Database session.

    Returns:
        200 OK with updated organization details.

    Raises:
        HTTPException:
            - 404: Organization not found.
    """
    try:
        org = await suspend_org(session, org_id)
        await session.commit()
        return OrgRead.model_validate(org)
    except ValueError:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Organization not found")


@router.post("/{org_id}/reactivate", response_model=OrgRead)
async def reactivate_organization(
    org_id: uuid.UUID,
    principal: OperatorPrincipal = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> OrgRead:
    """Reactivate a suspended organization.

    Endpoint: POST /v2/operator/orgs/{org_id}/reactivate

    Reactivates a suspended organization by setting status='active'.
    Operator-only access.

    Args:
        org_id: Organization ID to reactivate.
        principal: Verified operator principal.
        session: Database session.

    Returns:
        200 OK with updated organization details.

    Raises:
        HTTPException:
            - 404: Organization not found.
    """
    try:
        org = await reactivate_org(session, org_id)
        await session.commit()
        return OrgRead.model_validate(org)
    except ValueError:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Organization not found")


@router.get("", response_model=list[OrgRead])
async def list_organizations(
    principal: OperatorPrincipal = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> list[OrgRead]:
    """List all organizations.

    Endpoint: GET /v2/operator/orgs

    Lists all organizations in the platform. Operator-only access.

    Args:
        principal: Verified operator principal.
        session: Database session.

    Returns:
        200 OK with list of organizations.
    """
    orgs = await list_orgs(session)
    return [OrgRead.model_validate(org) for org in orgs]
