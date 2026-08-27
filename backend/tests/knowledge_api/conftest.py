"""Fixtures for knowledge API tests."""

from __future__ import annotations

import pytest


@pytest.fixture
async def client(app):
    """Provide async HTTP client (from conftest.py)."""
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
