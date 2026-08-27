"""Tenancy layer: org-scoped data access helpers (NFR-SEC1)."""

from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

ModelT = TypeVar("ModelT", bound=DeclarativeBase)


class TenancyViolationError(Exception):
    """Raised when data-access operation violates org scoping."""

    pass


def org_query(model: type[ModelT], org_id: uuid.UUID) -> Any:
    """Create a scoped query for a model filtered by org_id.

    This is a helper to ensure all queries across business modules
    enforce multi-tenant isolation at the data-access layer (NFR-SEC1).

    Args:
        model: SQLAlchemy ORM model class with org_id column.
        org_id: The organization UUID to scope to.

    Returns:
        A SQLAlchemy select statement filtered by org_id.
    """
    return select(model).where(model.org_id == org_id)


class OrgScopedRepo(Generic[ModelT]):
    """Generic org-scoped repository for data access (NFR-SEC1).

    This class enforces that all CRUD operations on business entities
    are scoped to a single organization. Services must use this repo
    instead of raw select() statements.

    Attributes:
        session: Async SQLAlchemy session.
        org_id: The organization UUID this repo is scoped to.
    """

    def __init__(self, session: AsyncSession, org_id: uuid.UUID) -> None:
        """Initialize a scoped repo for a given org.

        Args:
            session: Async SQLAlchemy session.
            org_id: The organization UUID to scope all operations to.
        """
        self.session = session
        self.org_id = org_id

    async def get(self, model: type[ModelT], entity_id: uuid.UUID) -> ModelT | None:
        """Get a single entity by ID within this org's scope.

        Args:
            model: SQLAlchemy ORM model class.
            entity_id: The entity's ID.

        Returns:
            The entity if found and belongs to this org, else None.
        """
        stmt = org_query(model, self.org_id).where(model.id == entity_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self, model: type[ModelT]) -> list[ModelT]:
        """List all entities for this org.

        Args:
            model: SQLAlchemy ORM model class.

        Returns:
            List of entities belonging to this org.
        """
        stmt = org_query(model, self.org_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add(self, instance: ModelT) -> None:
        """Add an entity to this org's scope.

        Args:
            instance: The entity to add.

        Raises:
            TenancyViolationError: If instance.org_id != self.org_id.
        """
        if instance.org_id != self.org_id:
            raise TenancyViolationError(
                f"Cannot add entity with org_id={instance.org_id} to repo scoped to {self.org_id}"
            )
        self.session.add(instance)

    async def delete(self, instance: ModelT) -> None:
        """Delete an entity from this org's scope.

        Args:
            instance: The entity to delete.

        Raises:
            TenancyViolationError: If instance.org_id != self.org_id.
        """
        if instance.org_id != self.org_id:
            raise TenancyViolationError(
                f"Cannot delete entity with org_id={instance.org_id} from repo scoped to {self.org_id}"
            )
        await self.session.delete(instance)
