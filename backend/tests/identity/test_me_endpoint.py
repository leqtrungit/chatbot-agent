"""Tests for GET /v2/me endpoint."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import jwt
from fastapi import FastAPI, Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import JWKSVerifier, TenantPrincipal, OperatorPrincipal
from app.identity.deps import get_jwks_verifier
from app.identity.router import router as identity_router
from app.orgs.models import Organization


class _FakeSession:
    """Fake session for testing without real database."""

    def __init__(self, orgs: dict[str, Organization]):
        self._orgs = orgs  # keyed by slug

    async def get(self, model, key):
        """Mock get method - not used in /v2/me logic."""
        if model is Organization:
            for org in self._orgs.values():
                if org.id == key:
                    return org
        return None

    async def execute(self, stmt):
        """Mock execute for query statements."""
        # This would be used for actual queries, but for /v2/me we'll use a simpler approach
        class FakeResult:
            def scalar_one_or_none(self):
                return None

        return FakeResult()


def _make_app(
    organizations: dict[str, Organization],
    verifier: JWKSVerifier,
) -> FastAPI:
    """Create test FastAPI app with mocked dependencies."""
    app = FastAPI()

    # Include the identity router
    app.include_router(identity_router)

    # Override dependencies
    app.dependency_overrides[get_session] = lambda: _FakeSession(organizations)
    app.dependency_overrides[get_jwks_verifier] = lambda request: verifier

    return app


def _make_org(org_id: uuid.UUID, name: str, slug: str, status: str = "active") -> Organization:
    """Create an Organization model for testing."""
    return Organization(
        id=org_id,
        name=name,
        slug=slug,
        keycloak_org_id=None,
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


async def _get_with_token(app: FastAPI, token: str) -> Any:
    """Make GET request to /v2/me with token."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get("/v2/me", headers={"Authorization": f"Bearer {token}"})


class TestMeEndpointNoDatabase:
    """Tests for /v2/me endpoint that don't require database."""

    def test_missing_authorization_header_returns_401(
        self,
        jwks_dict: dict[str, Any],
    ) -> None:
        """Missing Authorization header returns 401."""
        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        app = _make_app({}, verifier)

        with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = client.get("/v2/me")
            assert response.status_code == 401
            assert "Authorization header" in response.json()["detail"]

    def test_invalid_bearer_format_returns_401(
        self,
        jwks_dict: dict[str, Any],
    ) -> None:
        """Invalid Authorization format returns 401."""
        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        app = _make_app({}, verifier)

        with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = client.get("/v2/me", headers={"Authorization": "InvalidFormat"})
            assert response.status_code == 401
            assert "Invalid Authorization header format" in response.json()["detail"]

    def test_invalid_token_signature_returns_401(
        self,
        jwks_dict: dict[str, Any],
        make_token,
    ) -> None:
        """Invalid token signature returns 401."""
        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        app = _make_app({}, verifier)

        # Create token with wrong key
        invalid_token = make_token(
            {
                "sub": "user1",
                "email": "user@example.com",
                "organization": "acme",
                "iss": "http://localhost:8080/realms/harness",
                "aud": "backend",
            },
            wrong_key=True,
        )

        with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = client.get(
                "/v2/me",
                headers={"Authorization": f"Bearer {invalid_token}"},
            )
            assert response.status_code == 401

    def test_expired_token_returns_401(
        self,
        jwks_dict: dict[str, Any],
        make_token,
    ) -> None:
        """Expired token returns 401."""
        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        app = _make_app({}, verifier)

        # Create expired token
        expired_token = make_token(
            {
                "sub": "user1",
                "email": "user@example.com",
                "organization": "acme",
                "iss": "http://localhost:8080/realms/harness",
                "aud": "backend",
            },
            expired=True,
        )

        with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = client.get(
                "/v2/me",
                headers={"Authorization": f"Bearer {expired_token}"},
            )
            assert response.status_code == 401

    def test_operator_principal_returns_200_with_correct_shape(
        self,
        jwks_dict: dict[str, Any],
        make_token,
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Operator principal returns 200 with correct response shape."""
        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        app = _make_app({}, verifier)

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

        response = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ).get(
            "/v2/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "operator"
        assert data["user_id"] == "operator-user-1"
        assert data["email"] == "operator@example.com"
        assert data["org"] is None

    def test_tenant_without_org_in_db_returns_404(
        self,
        jwks_dict: dict[str, Any],
        make_token,
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Tenant with org alias not in database returns 404."""
        verifier = JWKSVerifier(jwks_dict=jwks_dict)
        # Empty organizations dict
        app = _make_app({}, verifier)

        # Create tenant token with org alias "acme" that doesn't exist in DB
        token = make_token(
            {
                "sub": "tenant-user-1",
                "email": "tenant@example.com",
                "organization": "acme",
                "iss": test_issuer,
                "aud": test_audience,
            }
        )

        response = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ).get(
            "/v2/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


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
        org = _make_org(org_id, "Acme Corp", "acme", status="active")
        session.add(org)
        await session.commit()

        verifier = JWKSVerifier(jwks_dict=jwks_dict)

        # Create app with real database session
        app = FastAPI()
        app.include_router(identity_router)
        app.dependency_overrides[get_jwks_verifier] = lambda request: verifier
        # Don't override get_session, use the real one

        # Create tenant token
        token = make_token(
            {
                "sub": "tenant-user-1",
                "email": "tenant@example.com",
                "organization": "acme",
                "iss": test_issuer,
                "aud": test_audience,
            }
        )

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
        org = _make_org(org_id, "Suspended Corp", "suspended-org", status="suspended")
        session.add(org)
        await session.commit()

        verifier = JWKSVerifier(jwks_dict=jwks_dict)

        # Create app with real database
        app = FastAPI()
        app.include_router(identity_router)
        app.dependency_overrides[get_jwks_verifier] = lambda request: verifier

        # Create tenant token for suspended org
        token = make_token(
            {
                "sub": "tenant-user-1",
                "email": "tenant@example.com",
                "organization": "suspended-org",
                "iss": test_issuer,
                "aud": test_audience,
            }
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/v2/me",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 403
        assert "suspended" in response.json()["detail"].lower()

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
        org = _make_org(org_id, "Acme Corp", "acme", status="active")
        session.add(org)
        await session.commit()

        verifier = JWKSVerifier(jwks_dict=jwks_dict)

        app = FastAPI()
        app.include_router(identity_router)
        app.dependency_overrides[get_jwks_verifier] = lambda request: verifier

        # Create token with different org alias
        token = make_token(
            {
                "sub": "tenant-user-1",
                "email": "tenant@example.com",
                "organization": "globex",  # Different from "acme"
                "iss": test_issuer,
                "aud": test_audience,
            }
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/v2/me",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 404
