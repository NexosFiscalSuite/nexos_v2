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
