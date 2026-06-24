"""Rotas de compliance: quebra de sequência + ciência."""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Role, require_role
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.compliance.api.schemas import (
    CienciaCreate,
    CienciaLoteCreate,
    CienciaResponse,
    QuebraResponse,
)
from app.modules.compliance.application.service import ComplianceService

router = APIRouter(prefix="/compliance", tags=["Compliance"])


@router.get("/empresas/{empresa_id}/quebras", response_model=list[QuebraResponse])
async def listar_quebras(
    empresa_id: UUID,
    ano: str | None = None,
    mes: str | None = None,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    return await ComplianceService(session).detectar_quebras(empresa_id, ano, mes)


@router.get("/empresas/{empresa_id}/ciencias", response_model=list[CienciaResponse])
async def listar_ciencias(
    empresa_id: UUID,
    classificacao: str | None = None,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    return await ComplianceService(session).listar_ciencias(empresa_id, classificacao)


@router.post("/empresas/{empresa_id}/ciencia-lote")
async def registrar_ciencia_lote(
    empresa_id: UUID,
    body: CienciaLoteCreate,
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    n = await ComplianceService(session).registrar_ciencia_lote(
        tenant_id=claims.tid,
        empresa_id=empresa_id,
        faixas=[f.model_dump() for f in body.faixas],
        classificacao=body.classificacao,
        justificativa=body.justificativa,
        auditor_email=body.auditor_email,
        auditor_senha=body.auditor_password,
        registrado_por=claims.sub,
    )
    return {"afetadas": n}


@router.post(
    "/empresas/{empresa_id}/ciencia",
    response_model=CienciaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def registrar_ciencia(
    empresa_id: UUID,
    body: CienciaCreate,
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    return await ComplianceService(session).registrar_ciencia(
        tenant_id=claims.tid,
        empresa_id=empresa_id,
        modelo=body.modelo,
        serie=body.serie,
        num_inicio=body.num_inicio,
        num_fim=body.num_fim,
        classificacao=body.classificacao,
        justificativa=body.justificativa,
        ciente_nome=body.ciente_nome,
        registrado_por=claims.sub,
    )
