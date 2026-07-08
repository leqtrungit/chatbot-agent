"""CORS is configurable via Settings.CORS_ORIGINS and defaults to local frontend dev URLs."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings


async def test_cors_allows_default_frontend_origin(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_cors_allows_127_0_0_1_by_default():
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"


def test_cors_origins_configurable_via_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://admin.example.com,https://foo.example.com")
    settings = Settings()

    assert settings.cors_origins_list == [
        "https://admin.example.com",
        "https://foo.example.com",
    ]
