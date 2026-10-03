from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FamilyOS API"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+asyncpg://familyos:change-me-strong@postgres:5432/familyos"
    )
    redis_url: str = "redis://redis:6379/0"
    s3_endpoint: str = "http://object-storage:8333"
    s3_public_endpoint: str = "http://localhost:8333"
    s3_access_key: str = "familyos"
    s3_secret_key: str = "change-me-strong"
    s3_bucket: str = "familyos-media"
    jwt_secret: str = "local-development-secret-change-before-deploying"
    access_token_minutes: int = 15
    # Long-lived session cookie; rotated on every use (see services/sessions.py).
    refresh_token_days: int = 30
    service_token: str = ""

    # AI defaults. The authoritative values live in households.settings['ai']
    # and are editable from the admin page (app/services/ai_settings.py); these
    # are only the fallback when a household has no override.
    llm_base_url: str = "http://litellm_proxy:4000"
    llm_api_key: str = ""
    embedding_model: str = "gemini/text-embedding-004"
    embedding_dim: int = 768

    @model_validator(mode="after")
    def validate_jwt_secret(self) -> "Settings":
        if self.environment.lower() not in {"development", "test"}:
            if self.jwt_secret == "local-development-secret-change-before-deploying":
                raise ValueError("JWT_SECRET must be set outside development and test environments")
            if len(self.jwt_secret.encode("utf-8")) < 32:
                raise ValueError("JWT_SECRET must be at least 32 bytes")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()