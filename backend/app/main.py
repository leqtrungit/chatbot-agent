"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.router import get_agent_router
from app.apikeys.router import router as apikeys_router
from app.core.config import get_settings
from app.knowledge.router import router as knowledge_router
from app.orgs.router import router as orgs_router


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(title="Agent Harness")
    settings = get_settings()

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    # Mount routers — the single mounting point for every module
    app.include_router(orgs_router)
    app.include_router(apikeys_router)
    app.include_router(get_agent_router())
    app.include_router(knowledge_router)

    return app


app = create_app()
