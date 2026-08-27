"""Service functions for organization management (FR-T1)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.orgs.kc_admin import KeycloakAdmin, KeycloakAdminError
from app.orgs.models import Organization


async def create_org(
    session: AsyncSession,
    kc: KeycloakAdmin,
    *,
    name: str,
    slug: str,
) -> Organization:
    """Create a new organization.

    Creates a Keycloak Organization first (with alias=slug), then creates
    the database record with the mapping. If database insertion fails,
    the Keycloak organization is deleted (best-effort rollback) to avoid
    leaving orphan organizations (FR-T1, NFR-SEC1).

    Args:
        session: Database session.
        kc: Keycloak Admin client.
        name: Organization name.
        slug: Organization slug (URL-friendly, will be KC alias).

    Returns:
        The created Organization record.

    Raises:
        KeycloakAdminError: If Keycloak organization creation fails.
        IntegrityError: If organization name/slug is not unique.
    """
    # Create Keycloak organization first (alias = slug)
    kc_org_id = await kc.create_organization(name=name, alias=slug)

    # Create database record
    org = Organization(
        name=name,
        slug=slug,
        keycloak_org_id=kc_org_id,
        status="active",
    )

    try:
        session.add(org)
        await session.flush()  # Flush to check unique constraints
    except IntegrityError:
        # Best-effort rollback: delete the Keycloak organization
        try:
            await kc.delete_organization(kc_org_id)
        except KeycloakAdminError:
            # Log but don't raise — database error takes precedence
            pass
        raise

    return org


async def suspend_org(session: AsyncSession, org_id: uuid.UUID) -> Organization:
    """Suspend an organization.

    Suspends an organization by setting status='suspended'. Suspended
    organizations reject all tenant requests (checked in require_org_member).

    Args:
        session: Database session.
        org_id: Organization ID to suspend.

    Returns:
        The updated Organization record.

    Raises:
        ValueError: If organization not found.
    """
    org = await session.get(Organization, org_id)
    if org is None:
        raise ValueError(f"Organization {org_id} not found")

    org.status = "suspended"
    await session.flush()
    return org


async def reactivate_org(session: AsyncSession, org_id: uuid.UUID) -> Organization:
    """Reactivate a suspended organization.

    Reactivates an organization by setting status='active'.

    Args:
        session: Database session.
        org_id: Organization ID to reactivate.

    Returns:
        The updated Organization record.

    Raises:
        ValueError: If organization not found.
    """
    org = await session.get(Organization, org_id)
    if org is None:
        raise ValueError(f"Organization {org_id} not found")

    org.status = "active"
    await session.flush()
    return org


async def list_orgs(session: AsyncSession) -> list[Organization]:
    """List all organizations.

    This is an operator-only function that queries across all orgs.
    Per architectural decision: module service.py IS ALLOWED to use
    select(Organization) directly since Organization is a root table
    with no org_id column (NFR-SEC1).

    Args:
        session: Database session.

    Returns:
        List of all organizations.
    """
    stmt = select(Organization).order_by(Organization.created_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()
