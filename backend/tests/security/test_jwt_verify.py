"""Tests for JWT verification and JWKS handling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from app.core.config import Settings
from app.core.security import JWKSVerifier


class TestJWKSVerifier:
    """Test JWKS verification and caching."""

    @pytest.mark.asyncio
    async def test_verify_valid_token(
        self,
        make_token: Any,
        jwks_dict: dict[str, Any],
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Valid token with correct claims decodes successfully."""
        claims = {
            "sub": "user-123",
            "email": "user@example.com",
            "iss": test_issuer,
            "aud": test_audience,
        }
        token = make_token(claims)

        # Create verifier with static JWKS
        verifier = JWKSVerifier(jwks_dict=jwks_dict)

        # Verify should succeed
        decoded = verifier.verify(
            token,
            issuer=test_issuer,
            audience=test_audience,
        )
        assert decoded["sub"] == "user-123"
        assert decoded["email"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_verify_expired_token(
        self,
        make_token: Any,
        jwks_dict: dict[str, Any],
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Expired token raises jwt.ExpiredSignatureError."""
        claims = {
            "sub": "user-123",
            "iss": test_issuer,
            "aud": test_audience,
        }
        token = make_token(claims, expired=True)

        verifier = JWKSVerifier(jwks_dict=jwks_dict)

        with pytest.raises(jwt.ExpiredSignatureError):
            verifier.verify(
                token,
                issuer=test_issuer,
                audience=test_audience,
            )

    @pytest.mark.asyncio
    async def test_verify_wrong_signature(
        self,
        make_token: Any,
        jwks_dict: dict[str, Any],
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Token signed with wrong key raises jwt.InvalidSignatureError."""
        claims = {
            "sub": "user-123",
            "iss": test_issuer,
            "aud": test_audience,
        }
        token = make_token(claims, wrong_key=True)

        verifier = JWKSVerifier(jwks_dict=jwks_dict)

        with pytest.raises(jwt.InvalidSignatureError):
            verifier.verify(
                token,
                issuer=test_issuer,
                audience=test_audience,
            )

    @pytest.mark.asyncio
    async def test_verify_wrong_audience(
        self,
        make_token: Any,
        jwks_dict: dict[str, Any],
        test_issuer: str,
    ) -> None:
        """Token with wrong audience raises jwt.InvalidAudienceError."""
        claims = {
            "sub": "user-123",
            "iss": test_issuer,
            "aud": "wrong-audience",
        }
        token = make_token(claims)

        verifier = JWKSVerifier(jwks_dict=jwks_dict)

        with pytest.raises(jwt.InvalidAudienceError):
            verifier.verify(
                token,
                issuer=test_issuer,
                audience="backend",
            )

    @pytest.mark.asyncio
    async def test_verify_wrong_issuer(
        self,
        make_token: Any,
        jwks_dict: dict[str, Any],
        test_audience: str,
    ) -> None:
        """Token with wrong issuer raises jwt.InvalidIssuerError."""
        claims = {
            "sub": "user-123",
            "iss": "http://wrong-issuer.com/realms/harness",
            "aud": test_audience,
        }
        token = make_token(claims)

        verifier = JWKSVerifier(jwks_dict=jwks_dict)

        with pytest.raises(jwt.InvalidIssuerError):
            verifier.verify(
                token,
                issuer="http://localhost:8080/realms/harness",
                audience=test_audience,
            )

    @pytest.mark.asyncio
    async def test_verify_unknown_kid_triggers_refresh(
        self,
        make_token: Any,
        rsa_keypair: tuple[bytes, bytes],
        test_issuer: str,
        test_audience: str,
    ) -> None:
        """Unknown kid triggers JWKS refresh (mock httpx)."""
        import base64

        # Generate a second keypair
        new_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )
        new_private_pem = new_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        new_public_pem = new_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # Build JWKS for the new key
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        public_key_obj = load_pem_public_key(new_public_pem, backend=default_backend())
        public_numbers = public_key_obj.public_numbers()

        def to_bytes(n: int, length: int) -> bytes:
            return n.to_bytes(length, byteorder="big")

        e_bytes = to_bytes(public_numbers.e, 3)
        n_bytes = to_bytes(public_numbers.n, 256)

        e_b64 = base64.urlsafe_b64encode(e_bytes).rstrip(b"=").decode()
        n_b64 = base64.urlsafe_b64encode(n_bytes).rstrip(b"=").decode()

        # Create initial JWKS with empty keys (simulating no knowledge of new key)
        initial_jwks = {"keys": []}

        # Create updated JWKS with new key
        updated_jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "new-key",
                    "n": n_b64,
                    "e": e_b64,
                    "alg": "RS256",
                }
            ]
        }

        # Create token signed with new key
        claims = {
            "sub": "user-123",
            "iss": test_issuer,
            "aud": test_audience,
        }

        token = jwt.encode(claims, new_private_pem, algorithm="RS256", headers={"kid": "new-key"})

        # Mock async fetch
        async def mock_fetch_jwks() -> dict[str, Any]:
            return updated_jwks

        verifier = JWKSVerifier(jwks_dict=initial_jwks)

        # Patch the fetch method
        with patch.object(verifier, "fetch_jwks", new_callable=AsyncMock, side_effect=mock_fetch_jwks):
            # Should trigger refresh
            decoded = await verifier.verify_async(
                token,
                issuer=test_issuer,
                audience=test_audience,
                jwks_url="http://localhost:8080/realms/harness/protocol/openid-connect/certs",
            )
            assert decoded["sub"] == "user-123"
