"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.modules.agent.router import router as agent_router
from app.modules.apikey.router import router as apikey_router
from app.modules.chat.router import chat_router
from app.modules.conversation.router import conversation_router
from app.modules.document.router import router as document_router
from app.modules.domain.router import router as domain_router
from app.modules.mcp.router import router as mcp_router
from app.modules.webhook.router import jobs_router, webhook_router


def create_app() -> FastAPI:
    app = FastAPI(title="Chatbot Agent Backend")
    settings = get_settings()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(domain_router)
    app.include_router(document_router)
    app.include_router(apikey_router)
    app.include_router(agent_router)
    app.include_router(mcp_router)
    app.include_router(webhook_router)
    app.include_router(jobs_router)
    app.include_router(chat_router)
    app.include_router(conversation_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
