from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://meetingos:meetingos@localhost:5432/meetingos"
    redis_url: str = "redis://localhost:6379/0"
    app_env: str = "development"
    log_level: str = "info"

    anthropic_api_key: str = ""
    openai_api_key: str = ""

    langchain_tracing_v2: bool = False
    langchain_project: str = "meeting-os-dev"
    langchain_api_key: str = ""

    meeting_os_encryption_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
