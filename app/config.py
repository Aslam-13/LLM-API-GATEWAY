from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = "dev"
    app_debug: bool = True
    app_secret_key: str = "change-me"

    # Database
    postgres_user: str = "gateway"
    postgres_password: str = "gateway"
    postgres_db: str = "gateway"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str = "postgresql+asyncpg://gateway:gateway@localhost:5432/gateway"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # RabbitMQ / Celery
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672//"
    celery_broker_url: str = "amqp://guest:guest@localhost:5672//"
    celery_result_backend: str = "redis://localhost:6379/1"

    # LLM providers
    openai_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    enable_anthropic: bool = False

    # Cache
    cache_ttl_seconds: int = 3600
    semantic_cache_enabled: bool = True
    semantic_cache_threshold: float = 0.97
    embedding_model: str = "text-embedding-3-small"

    # Rate limiting
    rate_limit_requests_per_minute: int = 60
    rate_limit_requests_per_day: int = 10000

    # Fallback
    provider_fallback_order: str = "openai,gemini"
    provider_retry_attempts: int = 2
    provider_retry_delay_seconds: int = 1

    @property
    def fallback_providers(self) -> list[str]:
        return [p.strip() for p in self.provider_fallback_order.split(",") if p.strip()]

    @property
    def is_dev(self) -> bool:
        return self.app_env == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
