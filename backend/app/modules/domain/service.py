"""Business logic for domains."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.domain.models import Domain
from app.modules.domain.schemas import DomainCreate, DomainUpdate


class DomainNotFoundError(Exception):
    pass


class DomainConflictError(Exception):
    pass


def slugify(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "domain"


async def _check_conflict(
    session: AsyncSession, name: str, slug: str, exclude_id: uuid.UUID | None = None
) -> None:
    stmt = select(Domain).where((Domain.name == name) | (Domain.slug == slug))
    result = await session.execute(stmt)
    existing = result.scalars().first()
    if existing is not None and existing.id != exclude_id:
        raise DomainConflictError(f"Domain with name '{name}' or slug '{slug}' already exists")


async def list_domains(session: AsyncSession) -> list[Domain]:
    result = await session.execute(select(Domain).order_by(Domain.created_at))
    return list(result.scalars().all())


async def get_domain(session: AsyncSession, domain_id: uuid.UUID) -> Domain:
    domain = await session.get(Domain, domain_id)
    if domain is None:
        raise DomainNotFoundError(str(domain_id))
    return domain


async def create_domain(session: AsyncSession, data: DomainCreate) -> Domain:
    slug = data.slug or slugify(data.name)
    await _check_conflict(session, data.name, slug)
    domain = Domain(name=data.name, slug=slug, description=data.description)
    session.add(domain)
    await session.commit()
    await session.refresh(domain)
    return domain


async def update_domain(
    session: AsyncSession, domain_id: uuid.UUID, data: DomainUpdate
) -> Domain:
    domain = await get_domain(session, domain_id)
    new_name = data.name if data.name is not None else domain.name
    new_slug = data.slug if data.slug is not None else domain.slug
    await _check_conflict(session, new_name, new_slug, exclude_id=domain.id)

    domain.name = new_name
    domain.slug = new_slug
    if data.description is not None:
        domain.description = data.description
    await session.commit()
    await session.refresh(domain)
    return domain


async def delete_domain(session: AsyncSession, domain_id: uuid.UUID) -> None:
    domain = await get_domain(session, domain_id)
    await session.delete(domain)
    await session.commit()
