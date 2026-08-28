"""Fixtures for identity tests."""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

# Import security test fixtures (rsa_keypair, rsa_private_key, rsa_public_key, jwks_dict, make_token, etc.)
from tests.security.conftest import (
    rsa_keypair,
    rsa_private_key,
    rsa_public_key,
    jwks_dict,
    make_token,
    test_issuer,
    test_audience,
)


@pytest_asyncio.fixture
async def session(db_session: AsyncSession) -> AsyncSession:
    """Alias for db_session for convenience in identity tests."""
    return db_session
