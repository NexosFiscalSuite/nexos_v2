"""Rotas de reporting: CRUD de modelos, geração assíncrona e download."""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.rbac import Role, require_role
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.core.storage import get_storage
from app.core.worker_db import worker_tenant_session
from app.modules.jobs.infrastructure.models import KIND_REPORT, STATUS_QUEUED, ProcessingJob
from app.modules.jobs.infrastructure.repositories import JobRepository
from app.modules.reporting.api.schemas import (
    GerarRequest,
    GerarResponse,
    ModeloCreate,
    ModeloResponse,
    ModeloUpdate,
    TagInfo,
)
from app.modules.reporting.application.service import ReportingService
from app.modules.reporting.domain.tags import TAGS
from app.modules.reporting.infrastructure.models import RelatorioModelo
from app.modules.reporting.workers import generate_report

router = APIRouter(prefix="/reporting", tags=["Relatórios"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _to_modelo_response(m: RelatorioModelo) -> ModeloResponse:
    return ModeloResponse(id=m.id, nome=m.nome, fluxo=m.fluxo, config=m.config_json or {}, created_at=m.created_at)


@router.get("/tags", response_model=list[TagInfo])
async def list_tags(claims: TokenClaims = Depends(get_current_claims)):
    return [TagInfo(**t) for t in TAGS.values()]


@router.get("/empresas/{empresa_id}/modelos", response_model=list[ModeloResponse])
async def list_modelos(
    empresa_id: UUID,
    fluxo: str | None = None,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    modelos = await ReportingService(session).list_modelos(empresa_id, fluxo)
    return [_to_modelo_response(m) for m in modelos]


@router.post(
    "/empresas/{empresa_id}/modelos",
    response_model=ModeloResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_modelo(
    empresa_id: UUID,
    body: ModeloCreate,
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    cfg = body.model_dump(exclude={"nome", "fluxo"})
    modelo = await ReportingService(session).create_modelo(
        tenant_id=claims.tid, empresa_id=empresa_id, nome=body.nome,
        fluxo=body.fluxo, config=cfg, created_by=claims.sub,
    )
    return _to_modelo_response(modelo)


@router.patch("/modelos/{modelo_id}", response_model=ModeloResponse)
async def update_modelo(
    modelo_id: UUID,
    body: ModeloUpdate,
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    cfg = body.config.model_dump() if body.config is not None else None
    modelo = await ReportingService(session).update_modelo(modelo_id, nome=body.nome, config=cfg)
    return _to_modelo_response(modelo)


@router.delete("/modelos/{modelo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_modelo(
    modelo_id: UUID,
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    await ReportingService(session).delete_modelo(modelo_id)


@router.post(
    "/empresas/{empresa_id}/gerar",
    response_model=GerarResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def gerar_relatorio(
    empresa_id: UUID,
    body: GerarRequest,
    claims: TokenClaims = Depends(get_current_claims),
):
    job_id = uuid4()
    # cria + commita o job (evita corrida com o worker), validando o modelo.
    async with worker_tenant_session(claims.tid) as s:
        modelo = await ReportingService(s).get_modelo(body.modelo_id)
        if modelo is None:
            raise NotFoundError("Modelo não encontrado.")
        JobRepository(s).add(
            ProcessingJob(
                id=job_id,
                tenant_id=claims.tid,
                user_id=claims.sub,
                kind=KIND_REPORT,
                status=STATUS_QUEUED,
            )
        )
        from app.modules.audit.application.service import AuditService

        await AuditService(s).registrar(
            tenant_id=claims.tid, user_id=claims.sub, acao="relatorio.gerar",
            entidade="modelo", entidade_id=str(body.modelo_id),
            detalhe={"modelo": modelo.nome, "ano": body.ano, "mes": body.mes},
        )

    generate_report.delay(
        str(job_id), str(claims.tid), str(empresa_id), str(claims.sub),
        str(body.modelo_id), body.ano, body.mes,
    )
    return GerarResponse(job_id=job_id, status=STATUS_QUEUED)


@router.get("/download/{job_id}")
async def download_relatorio(
    job_id: UUID,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    job = await JobRepository(session).by_id(job_id)
    if job is None or not job.result or not job.result.get("storage_key"):
        raise NotFoundError("Relatório não disponível (ainda gerando ou inexistente).")
    data = get_storage().get(job.result["storage_key"])
    filename = job.result.get("filename", "relatorio.xlsx")
    return Response(
        content=data,
        media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
