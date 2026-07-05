"""Tarefa Celery de importação de XML.

A API só faz o upload bruto para o staging e enfileira; o trabalho pesado
(parse + persistência) acontece aqui, fora do request. Cada tarefa roda seu
próprio event loop (asyncio.run) e sua própria sessão tenant-aware.
"""
import asyncio
from uuid import UUID

from app.core.alerts import alertar_falha
from app.core.celery_app import celery_app
from app.core.storage import get_storage
from app.core.worker_db import worker_tenant_session
from app.modules.companies.infrastructure.repositories import EmpresaRepository
from app.modules.fiscal.application.import_service import ImportService
from app.modules.fiscal.application.st_audit_service import StAuditService
from app.modules.jobs.infrastructure.models import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_RUNNING,
)
from app.modules.jobs.infrastructure.repositories import JobRepository


@celery_app.task(name="fiscal.import_xmls", bind=True)
def import_xmls(self, job_id: str, tenant_id: str, empresa_id: str, user_id: str, staging: list[dict]):
    return asyncio.run(
        _run(UUID(job_id), UUID(tenant_id), UUID(empresa_id), UUID(user_id), staging)
    )


async def _run(job_id, tenant_id, empresa_id, user_id, staging):
    storage = get_storage()

    # txn 1: marca running (visível ao polling enquanto processa)
    async with worker_tenant_session(tenant_id) as s:
        job = await JobRepository(s).by_id(job_id)
        if job:
            job.status = STATUS_RUNNING

    # txn 2: processa
    try:
        async with worker_tenant_session(tenant_id) as s:
            empresa = await EmpresaRepository(s).by_id(empresa_id)
            jobrepo = JobRepository(s)
            if empresa is None:
                job = await jobrepo.by_id(job_id)
                if job:
                    job.status = STATUS_FAILED
                    job.error = "Empresa não encontrada."
                alertar_falha("fiscal.import_xmls", "Empresa não encontrada.",
                              {"job_id": str(job_id), "empresa_id": str(empresa_id)})
                return {"error": "empresa_not_found"}

            service = ImportService(s, storage)
            resumo = await service.import_staged(
                tenant_id=tenant_id, empresa=empresa, user_id=user_id, staging=staging
            )
            auditaveis = list(service.notas_auditaveis)

            job = await jobrepo.by_id(job_id)
            if job:
                job.status = STATUS_DONE
                job.total = resumo["total_arquivos"]
                job.processed = resumo["total_arquivos"]
                job.result = resumo

        # txn 3: auditoria de ICMS-ST das NF-e do lote (separada — o frete dos
        # CT-e do mesmo lote já está persistido; falha aqui NÃO desfaz o import).
        if auditaveis:
            try:
                async with worker_tenant_session(tenant_id) as s:
                    auditor = StAuditService(s)
                    for nota_id in auditaveis:
                        await auditor.auditar_nota(empresa_id, nota_id)
            except Exception as e:  # noqa: BLE001 — auditoria não derruba o import
                # Degradação silenciosa é o pior modo de falha: o import "deu
                # certo" mas as notas ficaram sem auditoria — alerta sempre.
                alertar_falha("fiscal.auditoria_st", f"Auditoria de ST falhou: {e}",
                              {"job_id": str(job_id), "notas": len(auditaveis)})

        # Etapa separada: enriquece o regime (consulta optante) das contrapartes
        # recém-criadas, sem acoplar a velocidade do import à API externa.
        celery_app.send_task(
            "contrapartes.enriquecer_optante", args=[str(tenant_id), str(empresa_id)]
        )
        return resumo
    except Exception as e:  # noqa: BLE001
        async with worker_tenant_session(tenant_id) as s:
            job = await JobRepository(s).by_id(job_id)
            if job:
                job.status = STATUS_FAILED
                job.error = str(e)[:1000]
        alertar_falha("fiscal.import_xmls", str(e)[:500], {"job_id": str(job_id)})
        raise
