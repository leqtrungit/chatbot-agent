"""Keycloak Admin API client for organization management.

This module provides protocol and implementation for interacting with Keycloak's
Admin REST API to create and delete organizations (FR-T1).

The Protocol interface allows for mocking in tests without making real HTTP requests
to Keycloak. The HttpKeycloakAdmin implementation handles token management and API calls.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from app.core.config import Settings


class KeycloakAdmin(Protocol):
    """Protocol for Keycloak Admin API operations."""

    async def create_organization(self, name: str, alias: str) -> str:
        """Create a Keycloak Organization.

        Args:
            name: Organization display name.
            alias: Organization alias (will be used as slug in platform).

        Returns:
            The Keycloak organization ID (UUID as string).

        Raises:
            KeycloakAdminError: If organization creation fails.
        """
        ...

    async def delete_organization(self, kc_org_id: str) -> None:
        """Delete a Keycloak Organization.

        Used for rollback when database insertion fails after KC organization
        creation, to avoid leaving orphan organizations (FR-T1).

        Args:
            kc_org_id: The Keycloak organization ID to delete.

        Raises:
            KeycloakAdminError: If organization deletion fails.
        """
        ...


class KeycloakAdminError(Exception):
    """Raised when Keycloak Admin API operation fails."""

    pass


class HttpKeycloakAdmin:
    """HTTP implementation of Keycloak Admin API client.

    Handles:
    - Token acquisition via password grant (admin-cli client)
    - Organization creation via Admin REST API
    - Organization deletion for rollback

    Note:
        This implementation is not unit-tested with real Keycloak — unit tests
        mock this at the Protocol level. Real validation happens via smoke test
        in CI with actual Keycloak container (deferred to M1).
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize Keycloak Admin client.

        Args:
            settings: Application settings with Keycloak configuration.
        """
        self.settings = settings
        self._token: str | None = None

    async def _get_token(self) -> str:
        """Get access token via password grant (admin-cli client).

        Returns:
            Access token for subsequent API calls.

        Raises:
            KeycloakAdminError: If token acquisition fails.
        """
        if self._token is not None:
            return self._token

        url = f"{self.settings.keycloak_base_url}/realms/master/protocol/openid-connect/token"
        payload = {
            "client_id": "admin-cli",
            "grant_type": "password",
            "username": self.settings.keycloak_admin_username,
            "password": self.settings.keycloak_admin_password,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, data=payload)
                response.raise_for_status()
                data = response.json()
                self._token = data["access_token"]
                return self._token
        except Exception as e:
            raise KeycloakAdminError(f"Failed to acquire admin token: {str(e)}")

    async def create_organization(self, name: str, alias: str) -> str:
        """Create a Keycloak Organization.

        Calls POST /admin/realms/harness/organizations with the organization
        data. Keycloak Organizations require at least one domain; we use a
        placeholder `<alias>.local`.

        Args:
            name: Organization display name.
            alias: Organization alias (will be slug in platform).

        Returns:
            The Keycloak organization ID extracted from Location header.

        Raises:
            KeycloakAdminError: If creation fails.
        """
        token = await self._get_token()
        url = f"{self.settings.keycloak_base_url}/admin/realms/harness/organizations"

        payload = {
            "name": name,
            "alias": alias,
            "enabled": True,
            "domains": [{"name": f"{alias}.local"}],
        }

        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()

                # Extract organization ID from Location header
                # Format: .../organizations/{id}
                location = response.headers.get("Location", "")
                if not location:
                    raise KeycloakAdminError("No Location header in response")

                kc_org_id = location.rstrip("/").split("/")[-1]
                return kc_org_id
        except httpx.HTTPStatusError as e:
            raise KeycloakAdminError(
                f"Failed to create organization in Keycloak: {e.response.status_code} {e.response.text}"
            )
        except Exception as e:
            raise KeycloakAdminError(f"Failed to create organization: {str(e)}")

    async def delete_organization(self, kc_org_id: str) -> None:
        """Delete a Keycloak Organization.

        Args:
            kc_org_id: The Keycloak organization ID.

        Raises:
            KeycloakAdminError: If deletion fails.
        """
        token = await self._get_token()
        url = (
            f"{self.settings.keycloak_base_url}/admin/realms/harness/organizations/{kc_org_id}"
        )
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(url, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise KeycloakAdminError(
                f"Failed to delete organization from Keycloak: {e.response.status_code} {e.response.text}"
            )
        except Exception as e:
            raise KeycloakAdminError(f"Failed to delete organization: {str(e)}")
