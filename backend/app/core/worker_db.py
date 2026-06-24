"""Sessão tenant-aware para o WORKER Celery.

Diferenças vs. core/rls.py (que é dependency do FastAPI):
* O tenant vem dos argumentos da tarefa (não de um JWT).
* Usa NullPool: cada tarefa roda em seu próprio `asyncio.run` (novo event loop);
  sem pool, nenhuma conexão é reaproveitada entre loops (evita o erro clássico
  "attached to a different loop").
* Continua usando a role do app (nexos_app) -> SUJEITA a RLS. O isolamento vale
  igual no worker.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import NullPool, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import json_serializer

settings = get_settings()

_worker_engine = create_async_engine(
    settings.database_url, poolclass=NullPool, json_serializer=json_serializer
)
_WorkerSession = async_sessionmaker(_worker_engine, class_=AsyncSession, expire_on_commit=False)
_SET_TENANT = text("SELECT set_config('app.current_tenant', :tid, true)")


@asynccontextmanager
async def worker_tenant_session(tenant_id: UUID) -> AsyncIterator[AsyncSession]:
    async with _WorkerSession() as session:
        async with session.begin():
            await session.execute(_SET_TENANT, {"tid": str(tenant_id)})
            yield session
