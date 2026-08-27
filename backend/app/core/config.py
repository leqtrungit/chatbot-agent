"""Settings: configuration from environment variables and .env files."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration from environment and .env files."""

    model_config = SettingsConfigDict(
        env_file=[".env", "backend/.env"],
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Keycloak
    keycloak_issuer: str = "http://localhost:8080/realms/harness"
    keycloak_jwks_url: str = "http://localhost:8080/realms/harness/protocol/openid-connect/certs"
    keycloak_audience: str = "backend"
    keycloak_org_claim: str = "organization"  # claim written by oidc-organization-membership-mapper (see infra/keycloak)
    keycloak_role_claim_path: str = "realm_access.roles"
    keycloak_operator_role: str = "operator"

    # CORS
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


def get_settings() -> Settings:
    """Get singleton settings instance."""
    return Settings()
