"""
Centralized application configuration.

All configuration is sourced from environment variables (optionally loaded
from a local `.env` file via python-dotenv / pydantic-settings). Nothing in
this module should ever contain a hardcoded secret - see `.env.example` for
the full list of supported variables.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly typed application settings loaded from the environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- OpenAI / LangChain ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    langchain_temperature: float = 0.0

    # --- PostgreSQL ---
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "incident_db"
    postgres_user: str = "incident_user"
    postgres_password: str = "change_me"
    database_url: str = ""

    # --- Redis ---
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_log_queue: str = "server_log_events"

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    environment: str = "development"

    # --- Alerting ---
    alert_webhook_url: str = ""
    alert_min_severity: str = "CRITICAL"

    # --- Sample data ---
    sample_log_count: int = 200
    sample_log_dir: str = "data/sample_logs"

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return an explicit DATABASE_URL if set, otherwise build one from parts."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def has_openai_key(self) -> bool:
        """True when a (non-empty) OpenAI API key has been configured."""
        return bool(self.openai_api_key and self.openai_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (loaded once per process)."""
    return Settings()
