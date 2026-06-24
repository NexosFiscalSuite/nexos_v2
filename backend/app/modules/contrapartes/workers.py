"""Tarefa Celery: enriquecimento de regime (consulta optante) pós-importação.

Roda fora do import para não acoplar a velocidade da importação à API pública
de CNPJ. Enfileirada pelo worker de import ao final do lote.
"""
import asyncio
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.worker_db import worker_tenant_session
from app.modules.contrapartes.application.service import ContraparteService


@celery_app.task(name="contrapartes.enriquecer_optante", bind=True)
def enriquecer_optante(self, tenant_id: str, empresa_id: str):
    return asyncio.run(_run(UUID(tenant_id), UUID(empresa_id)))


async def _run(tenant_id: UUID, empresa_id: UUID) -> dict:
    async with worker_tenant_session(tenant_id) as s:
        return await ContraparteService(s).enriquecer_optante(empresa_id)
