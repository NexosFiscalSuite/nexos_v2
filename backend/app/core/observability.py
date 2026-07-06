"""Sentry opcional (NEXOS_SENTRY_DSN): erros da API e do worker num painel.

Sem DSN configurado é no-op — dev e testes não dependem do serviço. Com DSN,
o SDK auto-habilita as integrações de FastAPI/Starlette, Celery e SQLAlchemy
(pacotes presentes = integração ligada), então um único init cobre API e worker.
"""
from __future__ import annotations

import logging

from app.core.config import get_settings

logger = logging.getLogger("nexos")


def init_sentry() -> None:
    settings = get_settings()
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        send_default_pii=False,      # dados fiscais: nunca enviar PII por padrão
        traces_sample_rate=0.0,      # só erros; tracing/performance fica para depois
    )
    logger.info("Sentry habilitado (environment=%s).", settings.environment)
