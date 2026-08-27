"""Org-scoped access: bind the token's org membership to the {org_id} path param.

`require_org_member` (deps.py) only proves the caller belongs to *some*
organization. This module closes the loop for `/v2/orgs/{org_id}/...`
routes: the path's org must exist, must be the principal's own org
(matched via the Keycloak organization alias == Organization.slug,
which FR-T1 guarantees at org creation), and must not be suspended.

Mismatches return 404 — never 403 — so the existence of other tenants'
org ids is not confirmable by probing (NFR-SEC1).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import TenantPrincipal
from app.identity.deps import require_org_member
from app.orgs.models import Organization


@dataclass
class OrgContext:
    """Resolved org + verified principal for one request."""

    org: Organization
    principal: TenantPrincipal


async def require_org_access(
    org_id: uuid.UUID,
    principal: TenantPrincipal = Depends(require_org_member),
    session: AsyncSession = Depends(get_session),
) -> OrgContext:
    org = await session.get(Organization, org_id)
    if org is None or org.slug != principal.org_alias:
        # Unknown org and someone else's org are indistinguishable on purpose.
        raise HTTPException(status_code=404, detail="Organization not found")
    if org.status != "active":
        raise HTTPException(status_code=403, detail="Organization is suspended")
    return OrgContext(org=org, principal=principal)
