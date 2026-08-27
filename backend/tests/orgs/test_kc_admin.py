"""Unit tests for Keycloak Admin client (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.orgs.kc_admin import HttpKeycloakAdmin, KeycloakAdminError
from app.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Provide test settings."""
    return Settings(
        keycloak_base_url="http://localhost:8080",
        keycloak_admin_username="admin",
        keycloak_admin_password="admin",
    )


@pytest.mark.asyncio
async def test_create_organization_success(settings: Settings) -> None:
    """Test successful organization creation."""
    admin = HttpKeycloakAdmin(settings)

    # Mock the token endpoint
    token_response = MagicMock()
    token_response.json.return_value = {"access_token": "test-token"}
    token_response.raise_for_status = MagicMock()

    # Mock the create organization endpoint
    create_response = MagicMock()
    create_response.headers = {"Location": "http://localhost:8080/admin/realms/harness/organizations/kc-org-id"}
    create_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        # First call: token
        # Second call: create org
        mock_client.post = AsyncMock(side_effect=[token_response, create_response])

        mock_client_class.return_value = mock_client

        kc_org_id = await admin.create_organization("ACME Corp", "acme")

        assert kc_org_id == "kc-org-id"
        assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_create_organization_token_fail(settings: Settings) -> None:
    """Test organization creation when token acquisition fails."""
    admin = HttpKeycloakAdmin(settings)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post.side_effect = Exception("Network error")

        mock_client_class.return_value = mock_client

        with pytest.raises(KeycloakAdminError, match="Failed to acquire admin token"):
            await admin.create_organization("ACME Corp", "acme")


@pytest.mark.asyncio
async def test_create_organization_no_location_header(settings: Settings) -> None:
    """Test organization creation when Location header is missing."""
    admin = HttpKeycloakAdmin(settings)

    # Mock the token endpoint
    token_response = MagicMock()
    token_response.json.return_value = {"access_token": "test-token"}
    token_response.raise_for_status = MagicMock()

    # Mock the create organization endpoint without Location header
    create_response = MagicMock()
    create_response.headers = {}
    create_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(side_effect=[token_response, create_response])

        mock_client_class.return_value = mock_client

        with pytest.raises(KeycloakAdminError, match="No Location header"):
            await admin.create_organization("ACME Corp", "acme")


@pytest.mark.asyncio
async def test_delete_organization_success(settings: Settings) -> None:
    """Test successful organization deletion."""
    admin = HttpKeycloakAdmin(settings)

    # Mock the token endpoint
    token_response = MagicMock()
    token_response.json.return_value = {"access_token": "test-token"}
    token_response.raise_for_status = MagicMock()

    # Mock the delete endpoint
    delete_response = MagicMock()
    delete_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client.post = AsyncMock(side_effect=[token_response])
        mock_client.delete = AsyncMock(return_value=delete_response)

        mock_client_class.return_value = mock_client

        await admin.delete_organization("kc-org-id")

        mock_client.delete.assert_called_once()
        call_args = mock_client.delete.call_args
        assert "kc-org-id" in call_args[0][0]


@pytest.mark.asyncio
async def test_delete_organization_fail(settings: Settings) -> None:
    """Test organization deletion when API fails."""
    admin = HttpKeycloakAdmin(settings)

    # Mock the token endpoint
    token_response = MagicMock()
    token_response.json.return_value = {"access_token": "test-token"}
    token_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client.post = AsyncMock(return_value=token_response)

        # Mock delete to raise HTTPStatusError
        import httpx
        error_response = MagicMock(spec=httpx.Response)
        error_response.status_code = 404
        error_response.text = "Organization not found"
        mock_client.delete = AsyncMock(side_effect=httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=error_response
        ))

        mock_client_class.return_value = mock_client

        with pytest.raises(KeycloakAdminError, match="Failed to delete organization"):
            await admin.delete_organization("kc-org-id")
