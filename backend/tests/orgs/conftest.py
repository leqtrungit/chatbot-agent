"""Fixtures for organization tests."""

from __future__ import annotations

from typing import Any

import pytest


class FakeKeycloakAdmin:
    """Mock Keycloak Admin client for testing."""

    def __init__(self):
        """Initialize fake Keycloak Admin."""
        self.created_orgs: dict[str, dict[str, str]] = {}
        self.deleted_orgs: list[str] = []
        self.call_log: list[dict[str, Any]] = []

    async def create_organization(self, name: str, alias: str) -> str:
        """Mock organization creation."""
        kc_org_id = f"kc-{alias}-id"
        self.created_orgs[kc_org_id] = {"name": name, "alias": alias}
        self.call_log.append(
            {"method": "create_organization", "name": name, "alias": alias, "result": kc_org_id}
        )
        return kc_org_id

    async def delete_organization(self, kc_org_id: str) -> None:
        """Mock organization deletion."""
        if kc_org_id in self.created_orgs:
            del self.created_orgs[kc_org_id]
        self.deleted_orgs.append(kc_org_id)
        self.call_log.append({"method": "delete_organization", "kc_org_id": kc_org_id})

    def reset(self) -> None:
        """Reset call log for next test."""
        self.created_orgs.clear()
        self.deleted_orgs.clear()
        self.call_log.clear()


@pytest.fixture
def fake_kc() -> FakeKeycloakAdmin:
    """Provide a fake Keycloak Admin client."""
    return FakeKeycloakAdmin()
