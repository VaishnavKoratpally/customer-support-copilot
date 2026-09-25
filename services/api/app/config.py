from functools import lru_cache
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = Field(default="dev", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    ollama_base_url: str = Field(default="http://ollama:11434", alias="OLLAMA_BASE_URL")
    router_model: str = Field(default="qwen3:4b", alias="ROUTER_MODEL")
    main_model: str = Field(default="qwen3:14b", alias="MAIN_MODEL")
    escalation_model: str = Field(default="qwen3:20b", alias="ESCALATION_MODEL")

    retrieval_confidence_threshold: float = Field(default=0.55, alias="RETRIEVAL_CONFIDENCE_THRESHOLD")
    answer_confidence_threshold: float = Field(default=0.65, alias="ANSWER_CONFIDENCE_THRESHOLD")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    llm_provider: Literal["ollama", "stub"] = Field(default="ollama", alias="LLM_PROVIDER")
    ollama_timeout_seconds: float = Field(default=480.0, alias="OLLAMA_TIMEOUT_SECONDS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

