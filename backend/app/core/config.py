"""Application settings loaded from environment / .env files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT_ENV = Path(__file__).resolve().parents[2].parent / ".env"
_BACKEND_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT_ENV), str(_BACKEND_ENV)),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot"
    REDIS_URL: str = "redis://localhost:6379/0"

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    # Ollama host: serves embeddings (which have no agent row to configure) and
    # is the fallback for ollama agents that leave base_url blank. Chat
    # provider/model/credentials otherwise come from the Agent row.
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Embeddings are deployment-wide, not per-agent: ingestion and knowledge
    # search share the one `document_chunks.embedding` vector space, so the
    # provider/model/dimension must be identical for both.
    EMBEDDING_PROVIDER: str = "ollama"  # ollama | openai
    EMBEDDING_BASE_URL: str = ""  # blank -> OLLAMA_BASE_URL, or public OpenAI
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "nomic-embed-text"
    # Fixed by the Vector() column + HNSW index. This is an assertion, not a
    # knob: changing it needs a migration and a re-ingest of every document.
    EMBEDDING_DIM: int = 768

    CHAT_HISTORY_LIMIT: int = 20
    MAX_CLIENT_HISTORY_MESSAGES: int = 200

    UPLOAD_DIR: str = str(Path(__file__).resolve().parents[2] / "data" / "uploads")

    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_SESSION_PER_MINUTE: int = 20

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
