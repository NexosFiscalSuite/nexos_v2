"""Rotas de empresas (clientes do escritório)."""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.core.exceptions import DomainError, NotFoundError
from app.core.rbac import Role, require_role
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.core.worker_db import worker_tenant_session
from app.modules.audit.application.service import AuditService
from app.modules.companies.api.empresas_bulk import spec_empresas
from app.modules.companies.api.schemas import (
    EmpresaCreate,
    EmpresaResponse,
    EmpresaUpdate,
)
from app.modules.companies.application.service import EmpresaService
from app.modules.companies.infrastructure.models import Empresa
from app.modules.companies.workers import atualizar_cadastros
from app.modules.jobs.infrastructure.models import (
    KIND_ATUALIZA_CADASTRO,
    STATUS_QUEUED,
    STATUS_RUNNING,
    ProcessingJob,
)
from app.modules.jobs.infrastructure.repositories import JobRepository
from app.shared.bulk_csv import exportar_csv, importar_csv

router = APIRouter(prefix="/empresas", tags=["Empresas"])


@router.get("", response_model=list[EmpresaResponse])
async def list_empresas(
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    return await EmpresaService(session).list_for(claims)


# Rotas LITERAIS antes de /{empresa_id} ("export" não é um UUID).
@router.get("/export")
async def exportar_empresas(
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Planilha das empresas (vazia = template com o cabeçalho): preencha uma
    linha por empresa e importe de volta — upsert por CNPJ."""
    csv_text = await exportar_csv(session, spec_empresas(claims.tid))
    return Response(
        content="﻿" + csv_text,             # BOM → Excel abre com acentos
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="empresas.csv"'},
    )


@router.post("/import")
async def importar_empresas(
    arquivo: UploadFile = File(...),
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    """Cadastro em lote: valida cada linha (CNPJ com DV) e faz upsert por CNPJ.
    Linha ruim vira erro relatado (linha + motivo) sem derrubar o lote."""
    resumo = await importar_csv(session, spec_empresas(claims.tid), await arquivo.read())
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="empresas.import",
        entidade="empresa",
        detalhe={
            "inseridos": resumo.get("inseridos"), "atualizados": resumo.get("atualizados"),
            "erros": len(resumo.get("erros") or []),
        },
    )
    return resumo


@router.post("/atualizar-cadastros")
async def atualizar_cadastros_receita(
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
):
    """Atualiza TODAS as empresas pela base pública da Receita (OpenCNPJ), em
    segundo plano e com pausa entre consultas (rajada derruba a API gratuita).
    Retorna o job — o frontend acompanha o progresso por polling."""
    job_id = uuid4()
    # Transação própria (padrão do upload): o job commita ANTES do .delay,
    # senão o worker pode acordar e não encontrar a linha.
    async with worker_tenant_session(claims.tid) as s:
        ja_rodando = await s.scalar(
            select(func.count()).select_from(ProcessingJob).where(
                ProcessingJob.tenant_id == claims.tid,
                ProcessingJob.kind == KIND_ATUALIZA_CADASTRO,
                ProcessingJob.status.in_((STATUS_QUEUED, STATUS_RUNNING)),
            )
        )
        if ja_rodando:
            raise DomainError("Já existe uma atualização de cadastros em andamento.")
        total = await s.scalar(
            select(func.count()).select_from(Empresa).where(Empresa.tenant_id == claims.tid)
        )
        if not total:
            raise DomainError("Nenhuma empresa cadastrada para atualizar.")
        JobRepository(s).add(ProcessingJob(
            id=job_id, tenant_id=claims.tid, user_id=claims.sub,
            kind=KIND_ATUALIZA_CADASTRO, status=STATUS_QUEUED, total=total,
        ))
        await AuditService(s).registrar(
            tenant_id=claims.tid, user_id=claims.sub, acao="empresas.atualizar_cadastros",
            entidade="empresa", detalhe={"total": total, "job_id": str(job_id)},
        )
    atualizar_cadastros.delay(str(job_id), str(claims.tid))
    return {"job_id": str(job_id), "total": total, "status": STATUS_QUEUED}


@router.get("/{empresa_id}", response_model=EmpresaResponse)
async def get_empresa(
    empresa_id: UUID,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    empresa = await EmpresaService(session).get_for(claims, empresa_id)
    if empresa is None:
        raise NotFoundError("Empresa não encontrada.")
    return empresa


@router.post("", response_model=EmpresaResponse, status_code=status.HTTP_201_CREATED)
async def create_empresa(
    body: EmpresaCreate,
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    empresa = await EmpresaService(session).create(
        tenant_id=claims.tid, cnpj=body.cnpj, razao_social=body.razao_social,
        **body.model_dump(exclude={"cnpj", "razao_social"}),
    )
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="empresa.criar",
        entidade="empresa", entidade_id=str(empresa.id),
        detalhe={"cnpj": empresa.cnpj, "razao_social": empresa.razao_social},
    )
    return empresa


@router.patch("/{empresa_id}", response_model=EmpresaResponse)
async def update_empresa(
    empresa_id: UUID,
    body: EmpresaUpdate,
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    empresa = await EmpresaService(session).update(
        claims, empresa_id, body.model_dump(exclude_unset=True)
    )
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="empresa.editar",
        entidade="empresa", entidade_id=str(empresa.id),
        detalhe={"cnpj": empresa.cnpj},
    )
    return empresa
