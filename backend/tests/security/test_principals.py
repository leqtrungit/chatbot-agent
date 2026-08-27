"""Tests for principal extraction from JWT claims."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.security import (
    extract_principal,
    OperatorPrincipal,
    TenantPrincipal,
    MultipleOrgsError,
    UnauthorizedPrincipalError,
)


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        keycloak_org_claim="organizations",
        keycloak_role_claim_path="realm_access.roles",
        keycloak_operator_role="operator",
    )


class TestExtractPrincipal:
    """Test principal extraction from claims."""

    def test_extract_operator_principal(self, settings: Settings) -> None:
        """Claims with operator role → OperatorPrincipal."""
        claims = {
            "sub": "user-123",
            "email": "operator@example.com",
            "realm_access": {"roles": ["operator", "other"]},
        }

        principal = extract_principal(claims, settings)

        assert isinstance(principal, OperatorPrincipal)
        assert principal.user_id == "user-123"
        assert principal.email == "operator@example.com"

    def test_extract_operator_principal_no_email(self, settings: Settings) -> None:
        """Claims without email still work."""
        claims = {
            "sub": "user-123",
            "realm_access": {"roles": ["operator"]},
        }

        principal = extract_principal(claims, settings)

        assert isinstance(principal, OperatorPrincipal)
        assert principal.user_id == "user-123"
        assert principal.email is None

    def test_extract_tenant_principal_org_dict_owner(self, settings: Settings) -> None:
        """Claims with one org (dict shape) and owner role → TenantPrincipal owner."""
        claims = {
            "sub": "user-123",
            "email": "admin@example.com",
            "organizations": {
                "org-alias": {
                    "name": "My Org",
                }
            },
            "realm_access": {"roles": ["org_owner"]},
        }

        principal = extract_principal(claims, settings)

        assert isinstance(principal, TenantPrincipal)
        assert principal.user_id == "user-123"
        assert principal.email == "admin@example.com"
        assert principal.org_alias == "org-alias"
        assert principal.role == "owner"

    def test_extract_tenant_principal_org_dict_admin(self, settings: Settings) -> None:
        """Claims with one org (dict shape) and no specific role → TenantPrincipal admin."""
        claims = {
            "sub": "user-123",
            "email": "admin@example.com",
            "organizations": {
                "org-alias": {
                    "name": "My Org",
                }
            },
            "realm_access": {"roles": ["other"]},
        }

        principal = extract_principal(claims, settings)

        assert isinstance(principal, TenantPrincipal)
        assert principal.org_alias == "org-alias"
        assert principal.role == "admin"  # Default to admin

    def test_extract_tenant_principal_org_list(self, settings: Settings) -> None:
        """Claims with one org (list shape) → TenantPrincipal."""
        claims = {
            "sub": "user-123",
            "email": "admin@example.com",
            "organizations": ["org-alias"],
            "realm_access": {"roles": ["org_owner"]},
        }

        principal = extract_principal(claims, settings)

        assert isinstance(principal, TenantPrincipal)
        assert principal.org_alias == "org-alias"
        assert principal.role == "owner"

    def test_extract_tenant_principal_org_list_admin_role(self, settings: Settings) -> None:
        """Claims with one org (list) and admin role → TenantPrincipal admin."""
        claims = {
            "sub": "user-123",
            "organizations": ["org-alias"],
            "realm_access": {"roles": ["org_admin"]},
        }

        principal = extract_principal(claims, settings)

        assert isinstance(principal, TenantPrincipal)
        assert principal.role == "admin"  # org_admin → admin (TODO: verify with T1)

    def test_extract_multiple_orgs_raises_error(self, settings: Settings) -> None:
        """Claims with multiple orgs → MultipleOrgsError."""
        claims = {
            "sub": "user-123",
            "organizations": {
                "org-1": {"name": "Org 1"},
                "org-2": {"name": "Org 2"},
            },
        }

        with pytest.raises(MultipleOrgsError):
            extract_principal(claims, settings)

    def test_extract_multiple_orgs_list_raises_error(self, settings: Settings) -> None:
        """Claims with multiple orgs in list → MultipleOrgsError."""
        claims = {
            "sub": "user-123",
            "organizations": ["org-1", "org-2"],
        }

        with pytest.raises(MultipleOrgsError):
            extract_principal(claims, settings)

    def test_extract_no_operator_no_org_raises_error(
        self, settings: Settings
    ) -> None:
        """Claims without operator role and without org → UnauthorizedPrincipalError."""
        claims = {
            "sub": "user-123",
            "realm_access": {"roles": ["other"]},
        }

        with pytest.raises(UnauthorizedPrincipalError):
            extract_principal(claims, settings)

    def test_extract_no_claims_raises_error(self, settings: Settings) -> None:
        """Empty claims → UnauthorizedPrincipalError."""
        claims = {
            "sub": "user-123",
        }

        with pytest.raises(UnauthorizedPrincipalError):
            extract_principal(claims, settings)

    def test_extract_with_custom_claim_names(self) -> None:
        """Custom org and role claim names work."""
        custom_settings = Settings(
            keycloak_org_claim="custom_orgs",
            keycloak_role_claim_path="custom.roles",
            keycloak_operator_role="superuser",
        )

        claims = {
            "sub": "user-123",
            "custom": {"roles": ["superuser"]},
        }

        principal = extract_principal(claims, custom_settings)
        assert isinstance(principal, OperatorPrincipal)

    def test_extract_nested_role_path(self) -> None:
        """Deeply nested role claim path."""
        custom_settings = Settings(
            keycloak_org_claim="organizations",
            keycloak_role_claim_path="nested.deep.roles",
            keycloak_operator_role="operator",
        )

        claims = {
            "sub": "user-123",
            "nested": {"deep": {"roles": ["operator"]}},
        }

        principal = extract_principal(claims, custom_settings)
        assert isinstance(principal, OperatorPrincipal)

    def test_extract_role_path_missing(self, settings: Settings) -> None:
        """Missing role path treated as no roles."""
        claims = {
            "sub": "user-123",
            "other_field": {"roles": ["operator"]},
        }

        with pytest.raises(UnauthorizedPrincipalError):
            extract_principal(claims, settings)

    def test_extract_operator_takes_precedence(self, settings: Settings) -> None:
        """Operator role takes precedence over org membership."""
        claims = {
            "sub": "user-123",
            "organizations": {"org-alias": {}},
            "realm_access": {"roles": ["operator"]},
        }

        principal = extract_principal(claims, settings)

        # Operator should be returned, not tenant
        assert isinstance(principal, OperatorPrincipal)
