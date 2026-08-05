"""Instância do Celery. Broker e backend = Redis (configuráveis)."""
from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings
from app.core.observability import init_sentry

settings = get_settings()
init_sentry()   # no-op sem NEXOS_SENTRY_DSN; captura erros de task no worker

celery_app = Celery(
    "nexos",
    broker=settings.broker_url,
    backend=settings.result_backend,
    # Módulos com @celery_app.task — importados no boot do worker.
    include=[
        "app.modules.fiscal.workers",
        "app.modules.fiscal.crawlers.workers",
        "app.modules.reporting.workers",
        "app.modules.contrapartes.workers",
        "app.modules.companies.workers",
    ],
)

# Agenda (Celery beat). Roda no worker com -B (ver docker-compose).
celery_app.conf.beat_schedule = {
    # Auto-alimentação das matrizes: relação NCM×CEST do CONFAZ, todo dia 1º 04h UTC.
    "sync-cest-confaz-mensal": {
        "task": "fiscal.sync_cest_confaz",
        "schedule": crontab(day_of_month=1, hour=4, minute=0),
        "args": (settings.crawler_uf_alvo,),
    },
    # Radar de Protocolos ICMS (Fase 3): detecta mudança no índice do CONFAZ
    # e avisa a curadoria — toda segunda 05h UTC.
    "monitor-protocolos-confaz-semanal": {
        "task": "fiscal.monitor_protocolos_confaz",
        "schedule": crontab(day_of_week=1, hour=5, minute=0),
    },
}

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,            # re-enfileira se o worker morrer no meio
    worker_prefetch_multiplier=1,   # tarefas pesadas: 1 por vez por worker
    timezone="UTC",
    task_default_queue="nexos",
)

# Registra TODOS os modelos no Base.metadata ao subir o worker. Sem isto, o
# worker (que só importa os módulos de task) não tem a tabela `tenants` e o
# SQLAlchemy falha ao resolver as FKs entre módulos (NoReferencedTableError).
from app.modules.audit.infrastructure import models as _m_audit  # noqa: E402,F401
from app.modules.cfop_rules.infrastructure import models as _m_cfop_rules  # noqa: E402,F401
from app.modules.companies.infrastructure import models as _m_companies  # noqa: E402,F401
from app.modules.compliance.infrastructure import models as _m_compliance  # noqa: E402,F401
from app.modules.contrapartes.infrastructure import models as _m_contrapartes  # noqa: E402,F401
from app.modules.fiscal.infrastructure import matrizes_models as _m_matrizes  # noqa: E402,F401
from app.modules.fiscal.infrastructure import models as _m_fiscal  # noqa: E402,F401
from app.modules.fiscal.infrastructure import propostas_models as _m_propostas  # noqa: E402,F401
from app.modules.grupos.infrastructure import models as _m_grupos  # noqa: E402,F401
from app.modules.identity.infrastructure import models as _m_identity  # noqa: E402,F401
from app.modules.jobs.infrastructure import models as _m_jobs  # noqa: E402,F401
from app.modules.reporting.infrastructure import models as _m_reporting  # noqa: E402,F401
