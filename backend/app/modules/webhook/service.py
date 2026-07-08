"""Domain resolution for inbound webhook payloads.

Webhook payloads carry a ``domain_id`` string that may be either a real
domain UUID or a human-friendly slug; this resolves either to a domain.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.domain.models import Domain


class DomainNotFoundError(Exception):
    pass


async def resolve_domain(session: AsyncSession, domain_id_or_slug: str) -> Domain:
    try:
        domain_uuid = uuid.UUID(domain_id_or_slug)
    except ValueError:
        domain_uuid = None

    if domain_uuid is not None:
        domain = await session.get(Domain, domain_uuid)
        if domain is not None:
            return domain

    result = await session.execute(select(Domain).where(Domain.slug == domain_id_or_slug))
    domain = result.scalars().first()
    if domain is None:
        raise DomainNotFoundError(domain_id_or_slug)
    return domain
