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

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    CHAT_MODEL: str = "qwen2.5"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIM: int = 768

    AGENT_SYSTEM_PROMPT_TEMPLATE: str = "domain_qa"
    AGENT_MAX_ITERATIONS: int = 10

    UPLOAD_DIR: str = str(Path(__file__).resolve().parents[2] / "data" / "uploads")


@lru_cache
def get_settings() -> Settings:
    return Settings()
