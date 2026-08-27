"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.main import create_app


@pytest.fixture
def app() -> FastAPI:
    """Create a FastAPI app instance for testing."""
    return create_app()


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncClient:
    """Create an async HTTP client for testing."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
