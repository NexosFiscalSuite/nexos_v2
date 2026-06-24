"""Configuração central (Pydantic Settings). Lê variáveis com prefixo NEXOS_."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="NEXOS_",
        extra="ignore",
        case_sensitive=False,
    )

    # App ----------------------------------------------------------------------
    app_name: str = "Nexos Fiscal Suite V2"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Banco -------------------------------------------------------------------
    # URL do app (role nexos_app, SUJEITA a RLS).
    database_url: str
    # URL privilegiada (BYPASSRLS) — migrações + autenticação (login/signup).
    database_privileged_url: str
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # JWT ---------------------------------------------------------------------
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 7

    # Redis / rate limit ------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_default: str = "300/minute"

    # Celery (broker + backend; default = redis_url) --------------------------
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # Storage de XML ----------------------------------------------------------
    # backend: "local" (dev, grava em disco) | "s3" (MinIO/S3)
    storage_backend: str = "local"
    storage_local_dir: str = "./data/xml_storage"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "nexos-xml"
    s3_access_key: str = "nexos"
    s3_secret_key: str = "nexos12345"
    s3_region: str = "us-east-1"

    # CORS --------------------------------------------------------------------
    cors_origins: str = ""

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
