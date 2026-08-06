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
    app_name: str = "Sol Contabilidade"
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

    # Crawlers de auto-alimentação (CONFAZ/SEFAZ) -----------------------------
    # UFs com clientes do escritório, alvo do upsert das matrizes (job
    # agendado). Separadas por vírgula; a env NEXOS_CRAWLER_UF_ALVO sobrepõe.
    crawler_uf_alvo: str = "MG,PR,SP,DF,RS,RJ,GO"
    # Vigência-piso das linhas auto-alimentadas: as competências auditadas
    # começam em jun/2026, então o enquadramento precisa valer desde lá. Data
    # FIXA também mantém o upsert mensal idempotente (atualiza a mesma família
    # de vigência) em vez de abrir família nova — e sobreposta — a cada mês.
    crawler_vigencia_inicio: str = "2026-06-01"

    # Curadoria das matrizes fiscais: vazio = todo usuário autenticado escreve;
    # preenchido (e-mails por vírgula) = freio de emergência só para a lista. --
    # E-mails (separados por vírgula) autorizados a ESCREVER nas matrizes
    # globais. Vazio = qualquer ADMIN (comportamento histórico).
    matriz_curadores: str = ""

    # Motor de ST --------------------------------------------------------------
    # Fail-closed da MVA: quando LIGADO, item enquadrado em ST sem NENHUMA linha
    # de MVA na matriz (NCM/CEST/origem→destino, na data) vira NAO_AUDITAVEL com
    # ERRO_MVA_NAO_ENCONTRADA, qualquer que seja o modBCST — em vez de calcular
    # a base pelo valor da operação assumindo MVA 0% em silêncio.
    # DESLIGADO por padrão: só faz sentido depois que a base de MVA por par de
    # UFs estiver carregada, senão a maioria das notas vira pendência de uma vez.
    # A trava histórica do modBCST=4 (XML declarou base por MVA e a matriz não
    # tem a linha) continua SEMPRE ativa, independente desta chave.
    st_mva_fail_closed: bool = False

    # Alertas operacionais ------------------------------------------------------
    # Webhook (POST JSON) notificado quando um job assíncrono falha — ntfy.sh,
    # Slack/Teams incoming webhook etc. Vazio = só log CRITICAL.
    alert_webhook_url: str = ""
    # DSN do Sentry (erros da API e do worker). Vazio = desabilitado.
    sentry_dsn: str = ""

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
    def matriz_curadores_list(self) -> list[str]:
        return [e.strip().lower() for e in self.matriz_curadores.split(",") if e.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
