"""Tarefa Celery de geração de relatório (Excel) — assíncrona, sob RLS."""
import asyncio
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.storage import get_storage
from app.core.worker_db import worker_tenant_session
from app.modules.companies.infrastructure.repositories import EmpresaRepository
from app.modules.jobs.infrastructure.models import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_RUNNING,
)
from app.modules.jobs.infrastructure.repositories import JobRepository
from app.modules.reporting.application.service import ReportingService
from app.modules.reporting.domain import report_gen
from app.modules.reporting.domain.excel import build_excel


@celery_app.task(name="reporting.generate", bind=True)
def generate_report(self, job_id, tenant_id, empresa_id, user_id, modelo_id, ano, mes):
    return asyncio.run(
        _run(UUID(job_id), UUID(tenant_id), UUID(empresa_id), UUID(modelo_id), ano, mes)
    )


async def _run(job_id, tenant_id, empresa_id, modelo_id, ano, mes):
    storage = get_storage()

    async with worker_tenant_session(tenant_id) as s:
        job = await JobRepository(s).by_id(job_id)
        if job:
            job.status = STATUS_RUNNING

    try:
        async with worker_tenant_session(tenant_id) as s:
            svc = ReportingService(s)
            jobrepo = JobRepository(s)
            modelo = await svc.get_modelo(modelo_id)
            if modelo is None:
                job = await jobrepo.by_id(job_id)
                if job:
                    job.status = STATUS_FAILED
                    job.error = "Modelo não encontrado."
                return {"error": "modelo_not_found"}

            empresa = await EmpresaRepository(s).by_id(empresa_id)
            regime = empresa.regime if empresa else ""
            pares = await svc.load_notas_com_tipos(empresa_id, modelo.fluxo, ano, mes)
            notas_dados = []
            for nota, tipos in pares:
                xml = None
                if nota.storage_key:
                    try:
                        xml = storage.get(nota.storage_key)
                    except Exception:  # noqa: BLE001
                        xml = None
                notas_dados.append({"nota": nota, "tipos": tipos, "xml": xml})
            report = report_gen.gerar(modelo.config_json, notas_dados, regime)
            xlsx = build_excel(report, modelo.nome)

            key = f"{tenant_id}/_reports/{job_id}.xlsx"
            storage.put(key, xlsx)
            periodo = f"_{ano}" + (f"-{mes}" if mes else "") if ano else ""
            filename = f"{modelo.nome}{periodo}.xlsx".replace(" ", "_")

            job = await jobrepo.by_id(job_id)
            if job:
                job.status = STATUS_DONE
                job.total = report["total_notas"]
                job.processed = report["total_notas"]
                job.result = {
                    "storage_key": key,
                    "filename": filename,
                    "total_notas": report["total_notas"],
                }
        return {"storage_key": key, "total_notas": report["total_notas"]}
    except Exception as e:  # noqa: BLE001
        async with worker_tenant_session(tenant_id) as s:
            job = await JobRepository(s).by_id(job_id)
            if job:
                job.status = STATUS_FAILED
                job.error = str(e)[:1000]
        raise
