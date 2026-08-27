"""Tests for FastAPI security dependencies."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse
from httpx import AsyncClient, ASGITransport

from app.core.config import Settings
from app.core.security import (
    JWKSVerifier,
    OperatorPrincipal,
    TenantPrincipal,
)
from app.identity.deps import require_operator, require_org_member


@pytest.fixture
def app_with_deps(jwks_dict: dict[str, Any]) -> FastAPI:
    """Create app with security dependencies."""
    app = FastAPI()

    # Store JWKSVerifier in app state
    app.state.jwks_verifier = JWKSVerifier(jwks_dict=jwks_dict)

    @app.get("/operator-only")
    async def operator_endpoint(principal: OperatorPrincipal = Depends(require_operator)) -> dict:
        return {"user_id": principal.user_id, "email": principal.email}

    @app.get("/org-member-only")
    async def org_member_endpoint(
        principal: TenantPrincipal = Depends(require_org_member),
    ) -> dict:
        return {"user_id": principal.user_id, "org_alias": principal.org_alias, "role": principal.role}

    return app


@pytest.mark.asyncio
class TestRequireOperator:
    """Test require_operator dependency."""

    async def test_valid_operator_token(
        self,
        app_with_deps: FastAPI,
        make_token: Any,
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Valid operator token returns 200."""
        claims = {
            "sub": "user-123",
            "email": "operator@example.com",
            "iss": test_issuer,
            "aud": test_audience,
            "realm_access": {"roles": ["operator"]},
        }
        token = make_token(claims)

        # Patch settings in dependency
        with patch("app.identity.deps.get_settings") as mock_settings:
            settings = Settings(
                keycloak_issuer=test_issuer,
                keycloak_audience=test_audience,
            )
            mock_settings.return_value = settings

            async with AsyncClient(
                transport=ASGITransport(app=app_with_deps),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    "/operator-only",
                    headers={"Authorization": f"Bearer {token}"},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["user_id"] == "user-123"
                assert data["email"] == "operator@example.com"

    async def test_missing_auth_header(self, app_with_deps: FastAPI) -> None:
        """Missing Authorization header returns 401."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_deps),
            base_url="http://test",
        ) as client:
            response = await client.get("/operator-only")

            assert response.status_code == 401

    async def test_invalid_token_format(self, app_with_deps: FastAPI) -> None:
        """Invalid token format returns 401."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_deps),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/operator-only",
                headers={"Authorization": "Bearer invalid.token"},
            )

            assert response.status_code == 401

    async def test_tenant_token_returns_403(
        self,
        app_with_deps: FastAPI,
        make_token: Any,
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Tenant token (not operator) returns 403."""
        claims = {
            "sub": "user-123",
            "iss": test_issuer,
            "aud": test_audience,
            "organizations": {"org-alias": {}},
            "realm_access": {"roles": []},
        }
        token = make_token(claims)

        with patch("app.identity.deps.get_settings") as mock_settings:
            settings = Settings(
                keycloak_issuer=test_issuer,
                keycloak_audience=test_audience,
            )
            mock_settings.return_value = settings

            async with AsyncClient(
                transport=ASGITransport(app=app_with_deps),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    "/operator-only",
                    headers={"Authorization": f"Bearer {token}"},
                )

                assert response.status_code == 403


@pytest.mark.asyncio
class TestRequireOrgMember:
    """Test require_org_member dependency."""

    async def test_valid_tenant_token(
        self,
        app_with_deps: FastAPI,
        make_token: Any,
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Valid tenant token returns 200."""
        claims = {
            "sub": "user-123",
            "email": "admin@example.com",
            "iss": test_issuer,
            "aud": test_audience,
            "organizations": {"org-alias": {}},
            "realm_access": {"roles": ["org_owner"]},
        }
        token = make_token(claims)

        with patch("app.identity.deps.get_settings") as mock_settings:
            settings = Settings(
                keycloak_issuer=test_issuer,
                keycloak_audience=test_audience,
            )
            mock_settings.return_value = settings

            async with AsyncClient(
                transport=ASGITransport(app=app_with_deps),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    "/org-member-only",
                    headers={"Authorization": f"Bearer {token}"},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["user_id"] == "user-123"
                assert data["org_alias"] == "org-alias"
                assert data["role"] == "owner"

    async def test_operator_token_returns_403(
        self,
        app_with_deps: FastAPI,
        make_token: Any,
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Operator token (no org) returns 403."""
        claims = {
            "sub": "user-123",
            "iss": test_issuer,
            "aud": test_audience,
            "realm_access": {"roles": ["operator"]},
        }
        token = make_token(claims)

        with patch("app.identity.deps.get_settings") as mock_settings:
            settings = Settings(
                keycloak_issuer=test_issuer,
                keycloak_audience=test_audience,
            )
            mock_settings.return_value = settings

            async with AsyncClient(
                transport=ASGITransport(app=app_with_deps),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    "/org-member-only",
                    headers={"Authorization": f"Bearer {token}"},
                )

                assert response.status_code == 403

    async def test_missing_auth_header(self, app_with_deps: FastAPI) -> None:
        """Missing Authorization header returns 401."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_deps),
            base_url="http://test",
        ) as client:
            response = await client.get("/org-member-only")

            assert response.status_code == 401
