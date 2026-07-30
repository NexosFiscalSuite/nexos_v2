"""Tarefa Celery: atualização de cadastro em lote pela Receita (OpenCNPJ).

Roda fora do request (centenas de consultas com pausa entre cada uma levam
minutos); o frontend acompanha pelo processing_job.
"""
import asyncio
from uuid import UUID

from app.core.alerts import alertar_falha
from app.core.celery_app import celery_app
from app.core.worker_db import worker_tenant_session
from app.modules.companies.application.atualiza_cadastro import atualizar_cadastros_lote
from app.modules.jobs.infrastructure.models import STATUS_FAILED
from app.modules.jobs.infrastructure.repositories import JobRepository


@celery_app.task(name="companies.atualizar_cadastros", bind=True)
def atualizar_cadastros(self, job_id: str, tenant_id: str):
    return asyncio.run(_run(UUID(job_id), UUID(tenant_id)))


async def _run(job_id: UUID, tenant_id: UUID) -> dict:
    try:
        return await atualizar_cadastros_lote(
            tenant_id, job_id,
            sessao_factory=lambda: worker_tenant_session(tenant_id),
        )
    except Exception as e:  # noqa: BLE001
        async with worker_tenant_session(tenant_id) as s:
            job = await JobRepository(s).by_id(job_id)
            if job:
                job.status = STATUS_FAILED
                job.error = str(e)[:1000]
        alertar_falha("companies.atualizar_cadastros", str(e)[:500], {"job_id": str(job_id)})
        raise
