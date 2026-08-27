"""Security core: JWT verification, JWKS caching, principal extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx
import jwt

from app.core.config import Settings


# Principal models


@dataclass
class OperatorPrincipal:
    """Platform operator principal (from Keycloak realm role)."""

    user_id: str
    """Subject (sub) from token."""
    email: str | None = None
    """Email from token, if present."""


@dataclass
class TenantPrincipal:
    """Tenant admin/member principal (from Keycloak Organization membership)."""

    user_id: str
    """Subject (sub) from token."""
    org_alias: str
    """Organization alias/name from token."""
    role: Literal["owner", "admin"]
    """Role within organization: owner or admin."""
    email: str | None = None
    """Email from token, if present."""


# Exceptions


class MultipleOrgsError(Exception):
    """User belongs to multiple organizations (unsupported in v2)."""

    pass


class UnauthorizedPrincipalError(Exception):
    """Principal is not authorized (no operator role and no org membership)."""

    pass


# JWKS Verification


class JWKSVerifier:
    """Verify RS256 JWT tokens via JWKS with caching and refresh."""

    def __init__(
        self,
        jwks_dict: dict[str, Any] | None = None,
    ) -> None:
        """Initialize verifier with optional static JWKS dict.

        Args:
            jwks_dict: Static JWKS dictionary for testing. If provided,
                      fetch_jwks() is not called.
        """
        self._jwks_dict = jwks_dict
        self._keys_cache: dict[str, Any] = {}
        self._jwks_url: str | None = None

    def set_jwks_url(self, jwks_url: str) -> None:
        """Set JWKS URL for async fetching."""
        self._jwks_url = jwks_url

    def verify(
        self,
        token: str,
        issuer: str,
        audience: str,
    ) -> dict[str, Any]:
        """Verify RS256 JWT token synchronously.

        Uses cached JWKS dict only. For async JWKS fetching, use verify_async().

        Args:
            token: JWT token to verify.
            issuer: Expected token issuer.
            audience: Expected token audience.

        Returns:
            Decoded token claims.

        Raises:
            jwt.DecodeError: Token is malformed.
            jwt.ExpiredSignatureError: Token has expired.
            jwt.InvalidSignatureError: Signature verification failed.
            jwt.InvalidIssuerError: Issuer does not match.
            jwt.InvalidAudienceError: Audience does not match.
        """
        if self._jwks_dict is None:
            raise RuntimeError("JWKS dict not set. Use set_jwks_url() for async mode or pass jwks_dict to __init__.")

        # Get signing key from cached JWKS
        # First decode without verification to get the kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        # Find key in JWKS
        key = None
        for k in self._jwks_dict.get("keys", []):
            if k.get("kid") == kid:
                key = k
                break

        if key is None:
            raise jwt.InvalidKeyError(f"Unable to find kid {kid} in JWKS")

        # Reconstruct public key from JWK
        from jwt.algorithms import RSAAlgorithm

        public_key = RSAAlgorithm.from_jwk(key)

        # Verify and decode
        return jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
        )

    async def verify_async(
        self,
        token: str,
        issuer: str,
        audience: str,
        jwks_url: str | None = None,
    ) -> dict[str, Any]:
        """Verify RS256 JWT token with async JWKS fetching.

        Args:
            token: JWT token to verify.
            issuer: Expected token issuer.
            audience: Expected token audience.
            jwks_url: JWKS endpoint URL for fetching keys. If None, uses static JWKS.

        Returns:
            Decoded token claims.

        Raises:
            jwt.DecodeError: Token is malformed.
            jwt.ExpiredSignatureError: Token has expired.
            jwt.InvalidSignatureError: Signature verification failed.
            jwt.InvalidIssuerError: Issuer does not match.
            jwt.InvalidAudienceError: Audience does not match.
        """
        if jwks_url is not None and self._jwks_url is None:
            self.set_jwks_url(jwks_url)

        # Get unverified header to check kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        # Resolution order: refresh cache → static dict (initial cache) → fetch by URL.
        key = self._keys_cache.get(kid)
        if key is None and self._jwks_dict is not None:
            for k in self._jwks_dict.get("keys", []):
                if k.get("kid") == kid:
                    key = k
                    break
        if key is None:
            if self._jwks_url is None:
                raise jwt.InvalidKeyError(f"Unable to find kid {kid} in JWKS (no URL to refresh)")
            # Unknown kid → fetch JWKS (handles key rotation)
            jwks = await self.fetch_jwks()
            for k in jwks.get("keys", []):
                if k.get("kid") == kid:
                    key = k
                    self._keys_cache[kid] = key
                    break
            if key is None:
                raise jwt.InvalidKeyError(f"Unable to find kid {kid} in fetched JWKS")

        # Reconstruct public key from JWK
        from jwt.algorithms import RSAAlgorithm

        public_key = RSAAlgorithm.from_jwk(key)

        # Verify and decode
        return jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
        )

    async def fetch_jwks(self) -> dict[str, Any]:
        """Fetch JWKS from configured URL (for testing/mocking)."""
        if self._jwks_url is None:
            raise RuntimeError("JWKS URL not set")

        async with httpx.AsyncClient() as client:
            response = await client.get(self._jwks_url)
            response.raise_for_status()
            return response.json()


# Principal Extraction


def _get_value_by_path(obj: dict[str, Any], path: str) -> Any:
    """Get value from dict using dot-notation path.

    Args:
        obj: Dictionary to traverse.
        path: Dot-separated path (e.g., "realm_access.roles").

    Returns:
        Value at path, or None if not found.
    """
    keys = path.split(".")
    current = obj
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
            if current is None:
                return None
        else:
            return None
    return current


def extract_principal(
    claims: dict[str, Any],
    settings: Settings,
) -> OperatorPrincipal | TenantPrincipal:
    """Extract principal (operator or tenant) from JWT claims.

    Args:
        claims: JWT token claims.
        settings: Application settings with claim paths and role names.

    Returns:
        OperatorPrincipal or TenantPrincipal.

    Raises:
        MultipleOrgsError: User belongs to multiple organizations.
        UnauthorizedPrincipalError: User is not authorized (no operator role and no org).
    """
    user_id = claims.get("sub")
    email = claims.get("email")

    # Check for operator role
    roles = _get_value_by_path(claims, settings.keycloak_role_claim_path) or []
    if isinstance(roles, list) and settings.keycloak_operator_role in roles:
        return OperatorPrincipal(user_id=user_id, email=email)

    # Check for organization membership
    org_claim = claims.get(settings.keycloak_org_claim)

    if org_claim:
        # org_claim can be dict {alias: {...}} or list [alias, ...]
        if isinstance(org_claim, dict):
            org_aliases = list(org_claim.keys())
        elif isinstance(org_claim, list):
            org_aliases = org_claim
        else:
            org_aliases = []

        if len(org_aliases) > 1:
            raise MultipleOrgsError(f"User {user_id} belongs to multiple organizations")

        if len(org_aliases) == 1:
            org_alias = org_aliases[0]

            # Determine role within organization
            # TODO: Wait for T1 to clarify KC Organizations role claim shape
            # For now: org_owner → owner, anything else → admin (member is default)
            role = "admin"  # Default
            if "org_owner" in roles:
                role = "owner"

            return TenantPrincipal(
                user_id=user_id,
                email=email,
                org_alias=org_alias,
                role=role,
            )

    # No operator role and no org membership
    raise UnauthorizedPrincipalError(f"User {user_id} is not authorized")
