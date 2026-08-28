"""Tests for GET /v2/me endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import get_session
from app.core.security import JWKSVerifier, TenantPrincipal, OperatorPrincipal
from app.identity.deps import get_jwks_verifier
from app.identity.router import router as identity_router
from app.orgs.models import Organization


class _FakeSession:
    """Fake session for testing without real database."""

    def __init__(self, orgs: dict[str, Organization]):
        self._orgs = orgs  # keyed by slug

    async def execute(self, stmt):
        """Mock execute for query statements."""
        # Handle SELECT Organization queries
        if hasattr(stmt, 'froms') and Organization in stmt.froms:
            # Very basic query simulation - check for slug filter
            if hasattr(stmt, 'whereclause') and stmt.whereclause is not None:
                # For now, return None - tests will override as needed
                pass

        class FakeResult:
            def __init__(self, org: Organization | None = None):
                self._org = org

            def scalar_one_or_none(self):
                return self._org

        return FakeResult()


def _make_app(
    verifier: JWKSVerifier,
    test_issuer: str = "http://localhost:8080/realms/harness",
    test_audience: str = "backend",
) -> FastAPI:
    """Create test FastAPI app with mocked dependencies."""
    app = FastAPI()

    # Include the identity router
    app.include_router(identity_router)

    # Store JWKSVerifier in app state
    app.state.jwks_verifier = verifier

    return app


@pytest.mark.asyncio
class TestMeEndpointNoDatabase:
    """Tests for /v2/me endpoint that don't require database."""

    async def test_missing_authorization_header_returns_401(
        self,
        jwks_dict: dict[str, Any],
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Missing Authorization header returns 401."""
        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        app = _make_app(verifier, test_issuer, test_audience)

        with patch("app.identity.deps.get_settings") as mock_settings:
            settings = Settings(
                keycloak_issuer=test_issuer,
                keycloak_audience=test_audience,
            )
            mock_settings.return_value = settings

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/v2/me")
                assert response.status_code == 401
                assert "Authorization header" in response.json()["detail"]

    async def test_invalid_bearer_format_returns_401(
        self,
        jwks_dict: dict[str, Any],
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Invalid Authorization format returns 401."""
        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        app = _make_app(verifier, test_issuer, test_audience)

        with patch("app.identity.deps.get_settings") as mock_settings:
            settings = Settings(
                keycloak_issuer=test_issuer,
                keycloak_audience=test_audience,
            )
            mock_settings.return_value = settings

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/v2/me", headers={"Authorization": "InvalidFormat"})
                assert response.status_code == 401
                assert "Invalid Authorization header format" in response.json()["detail"]

    async def test_invalid_token_signature_returns_401(
        self,
        jwks_dict: dict[str, Any],
        make_token,
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Invalid token signature returns 401."""
        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        app = _make_app(verifier, test_issuer, test_audience)

        # Create token with wrong key
        invalid_token = make_token(
            {
                "sub": "user1",
                "email": "user@example.com",
                "organization": "acme",
                "iss": test_issuer,
                "aud": test_audience,
            },
            wrong_key=True,
        )

        with patch("app.identity.deps.get_settings") as mock_settings:
            settings = Settings(
                keycloak_issuer=test_issuer,
                keycloak_audience=test_audience,
            )
            mock_settings.return_value = settings

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/v2/me",
                    headers={"Authorization": f"Bearer {invalid_token}"},
                )
                assert response.status_code == 401

    async def test_expired_token_returns_401(
        self,
        jwks_dict: dict[str, Any],
        make_token,
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Expired token returns 401."""
        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        app = _make_app(verifier, test_issuer, test_audience)

        # Create expired token
        expired_token = make_token(
            {
                "sub": "user1",
                "email": "user@example.com",
                "organization": "acme",
                "iss": test_issuer,
                "aud": test_audience,
            },
            expired=True,
        )

        with patch("app.identity.deps.get_settings") as mock_settings:
            settings = Settings(
                keycloak_issuer=test_issuer,
                keycloak_audience=test_audience,
            )
            mock_settings.return_value = settings

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/v2/me",
                    headers={"Authorization": f"Bearer {expired_token}"},
                )
                assert response.status_code == 401

    async def test_operator_principal_returns_200_with_correct_shape(
        self,
        jwks_dict: dict[str, Any],
        make_token,
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Operator principal returns 200 with correct response shape."""
        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        app = _make_app(verifier, test_issuer, test_audience)

        # Create token with operator role
        token = make_token(
            {
                "sub": "operator-user-1",
                "email": "operator@example.com",
                "realm_access": {"roles": ["operator"]},
                "iss": test_issuer,
                "aud": test_audience,
            }
        )

        with patch("app.identity.deps.get_settings") as mock_settings:
            settings = Settings(
                keycloak_issuer=test_issuer,
                keycloak_audience=test_audience,
            )
            mock_settings.return_value = settings

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    "/v2/me",
                    headers={"Authorization": f"Bearer {token}"},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["kind"] == "operator"
                assert data["user_id"] == "operator-user-1"
                assert data["email"] == "operator@example.com"
                assert data["org"] is None


@pytest.mark.asyncio
class TestMeEndpointWithDatabase:
    """Tests for /v2/me endpoint using real database."""

    async def test_tenant_with_active_org_returns_200_with_org_data(
        self,
        session: AsyncSession,
        jwks_dict: dict[str, Any],
        make_token,
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Tenant with org in DB returns 200 with org data."""
        # Create organization in database
        org_id = uuid.uuid4()
        org = Organization(
            id=org_id,
            name="Acme Corp",
            slug="acme",
            keycloak_org_id=None,
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(org)
        await session.commit()

        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        app = _make_app(verifier, test_issuer, test_audience)

        # Create tenant token
        token = make_token(
            {
                "sub": "tenant-user-1",
                "email": "tenant@example.com",
                "organization": {"acme": {}},
                "iss": test_issuer,
                "aud": test_audience,
            }
        )

        with patch("app.identity.deps.get_settings") as mock_settings:
            settings = Settings(
                keycloak_issuer=test_issuer,
                keycloak_audience=test_audience,
            )
            mock_settings.return_value = settings

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/v2/me",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["kind"] == "tenant"
            assert data["user_id"] == "tenant-user-1"
            assert data["email"] == "tenant@example.com"
            assert data["org"]["id"] == str(org_id)
            assert data["org"]["name"] == "Acme Corp"
            assert data["org"]["slug"] == "acme"
            assert data["org"]["status"] == "active"

    async def test_tenant_with_suspended_org_returns_403(
        self,
        session: AsyncSession,
        jwks_dict: dict[str, Any],
        make_token,
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Tenant with suspended org returns 403."""
        # Create suspended organization
        org_id = uuid.uuid4()
        org = Organization(
            id=org_id,
            name="Suspended Corp",
            slug="suspended-org",
            keycloak_org_id=None,
            status="suspended",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(org)
        await session.commit()

        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        app = _make_app(verifier, test_issuer, test_audience)

        # Create tenant token for suspended org
        token = make_token(
            {
                "sub": "tenant-user-1",
                "email": "tenant@example.com",
                "organization": {"suspended-org": {}},
                "iss": test_issuer,
                "aud": test_audience,
            }
        )

        with patch("app.identity.deps.get_settings") as mock_settings:
            settings = Settings(
                keycloak_issuer=test_issuer,
                keycloak_audience=test_audience,
            )
            mock_settings.return_value = settings

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/v2/me",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 403
            assert "suspended" in response.json()["detail"].lower()

    async def test_tenant_without_org_in_db_returns_404(
        self,
        session: AsyncSession,
        jwks_dict: dict[str, Any],
        make_token,
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Tenant with org alias not in database returns 404."""
        # Don't create any organizations - test empty DB
        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        app = _make_app(verifier, test_issuer, test_audience)

        # Create tenant token with org alias "acme" that doesn't exist in DB
        token = make_token(
            {
                "sub": "tenant-user-1",
                "email": "tenant@example.com",
                "organization": {"acme": {}},
                "iss": test_issuer,
                "aud": test_audience,
            }
        )

        with patch("app.identity.deps.get_settings") as mock_settings:
            settings = Settings(
                keycloak_issuer=test_issuer,
                keycloak_audience=test_audience,
            )
            mock_settings.return_value = settings

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/v2/me",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 404

    async def test_tenant_with_mismatched_org_alias_returns_404(
        self,
        session: AsyncSession,
        jwks_dict: dict[str, Any],
        make_token,
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Token org alias doesn't match any DB org returns 404."""
        # Create organization
        org_id = uuid.uuid4()
        org = Organization(
            id=org_id,
            name="Acme Corp",
            slug="acme",
            keycloak_org_id=None,
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(org)
        await session.commit()

        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        app = _make_app(verifier, test_issuer, test_audience)

        # Create token with different org alias
        token = make_token(
            {
                "sub": "tenant-user-1",
                "email": "tenant@example.com",
                "organization": {"globex": {}},  # Different from "acme"
                "iss": test_issuer,
                "aud": test_audience,
            }
        )

        with patch("app.identity.deps.get_settings") as mock_settings:
            settings = Settings(
                keycloak_issuer=test_issuer,
                keycloak_audience=test_audience,
            )
            mock_settings.return_value = settings

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/v2/me",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 404
