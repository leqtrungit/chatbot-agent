"""Security tests configuration with RSA keypair and JWKS fixtures."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)


@pytest.fixture(scope="session")
def rsa_keypair() -> tuple[bytes, bytes]:
    """Generate RSA keypair for signing and verifying tokens."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    return private_pem, public_pem


@pytest.fixture
def rsa_private_key(rsa_keypair: tuple[bytes, bytes]) -> bytes:
    """Return private key from keypair."""
    return rsa_keypair[0]


@pytest.fixture
def rsa_public_key(rsa_keypair: tuple[bytes, bytes]) -> bytes:
    """Return public key from keypair."""
    return rsa_keypair[1]


@pytest.fixture
def jwks_dict(rsa_public_key: bytes) -> dict[str, Any]:
    """Build JWKS dict from public key."""
    public_key_obj = load_pem_public_key(rsa_public_key, backend=default_backend())
    public_numbers = public_key_obj.public_numbers()

    # Convert to URL-safe base64
    import base64

    def to_bytes(n: int, length: int) -> bytes:
        return n.to_bytes(length, byteorder="big")

    e_bytes = to_bytes(public_numbers.e, 3)
    n_bytes = to_bytes(public_numbers.n, 256)

    e_b64 = base64.urlsafe_b64encode(e_bytes).rstrip(b"=").decode()
    n_b64 = base64.urlsafe_b64encode(n_bytes).rstrip(b"=").decode()

    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "kid": "test-key-1",
                "n": n_b64,
                "e": e_b64,
                "alg": "RS256",
            }
        ]
    }


@pytest.fixture
def make_token(rsa_private_key: bytes) -> Any:
    """Factory to create signed JWT tokens for testing."""

    def _make_token(
        claims: dict[str, Any],
        kid: str = "test-key-1",
        expired: bool = False,
        wrong_key: bool = False,
    ) -> str:
        """Create a signed JWT token."""
        if expired:
            claims["exp"] = datetime.now(timezone.utc) - timedelta(hours=1)
        else:
            claims["exp"] = datetime.now(timezone.utc) + timedelta(hours=1)

        # Use wrong key if specified
        if wrong_key:
            wrong_private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend(),
            ).private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            key = wrong_private_key
        else:
            key = rsa_private_key

        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})

    return _make_token


@pytest.fixture
def test_issuer() -> str:
    """Test Keycloak issuer URL."""
    return "http://localhost:8080/realms/harness"


@pytest.fixture
def test_audience() -> str:
    """Test Keycloak audience."""
    return "backend"
