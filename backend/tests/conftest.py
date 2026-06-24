"""Configura env mínimo ANTES de importar `app.*` (Settings tem campos
obrigatórios). Estes defaults valem para os testes unitários, que não tocam
o banco. Testes de integração com RLS usarão um Postgres real (testcontainers)
e entram junto da Fase 3."""
import os

os.environ.setdefault(
    "NEXOS_DATABASE_URL",
    "postgresql+asyncpg://nexos_app:nexos_app@localhost:5432/nexos",
)
os.environ.setdefault(
    "NEXOS_DATABASE_PRIVILEGED_URL",
    "postgresql+asyncpg://nexos:nexos@localhost:5432/nexos",
)
os.environ.setdefault("NEXOS_JWT_SECRET", "test-secret-please-change")
os.environ.setdefault("NEXOS_ENVIRONMENT", "test")

# Registra TODOS os models em Base.metadata para que os testes de integração
# (SQLite) consigam resolver as FKs no create_all. Mesmo padrão do env.py/celery.
import app.core.celery_app  # noqa: E402, F401
