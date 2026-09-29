from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = Field(default="dev", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    postgres_host: str = Field(default="postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="support_copilot", alias="POSTGRES_DB")
    postgres_user: str = Field(default="support_user", alias="POSTGRES_USER")
    postgres_password: str = Field(default="support_password", alias="POSTGRES_PASSWORD")
    postgres_connect_timeout_seconds: float = Field(default=5.0, alias="POSTGRES_CONNECT_TIMEOUT_SECONDS")

    ollama_base_url: str = Field(default="http://ollama:11434", alias="OLLAMA_BASE_URL")
    router_model: str = Field(default="qwen3:4b", alias="ROUTER_MODEL")
    main_model: str = Field(default="qwen3:14b", alias="MAIN_MODEL")
    escalation_model: str = Field(default="qwen3:20b", alias="ESCALATION_MODEL")

    retrieval_confidence_threshold: float = Field(default=0.55, alias="RETRIEVAL_CONFIDENCE_THRESHOLD")
    answer_confidence_threshold: float = Field(default=0.65, alias="ANSWER_CONFIDENCE_THRESHOLD")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    llm_provider: Literal["ollama", "stub"] = Field(default="ollama", alias="LLM_PROVIDER")
    ollama_timeout_seconds: float = Field(default=480.0, alias="OLLAMA_TIMEOUT_SECONDS")

    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")
    redis_password: str | None = Field(default=None, alias="REDIS_PASSWORD")
    redis_idempotency_ttl_seconds: int = Field(default=900, alias="REDIS_IDEMPOTENCY_TTL_SECONDS")

    @property
    def postgres_dsn(self) -> str:
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return f"postgresql://{user}:{password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
