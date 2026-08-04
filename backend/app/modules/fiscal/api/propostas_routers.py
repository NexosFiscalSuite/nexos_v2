"""Fila de revisão da auto-alimentação das matrizes (Fase 1 da automação).

Leitura: qualquer usuário autenticado. Aprovar/rejeitar: `require_curador`
(mesmo freio das matrizes) — aprovar grava na matriz pelo caminho validado do
CRUD e tudo fica na trilha de auditoria (quem/quando/o quê).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.audit.application.service import AuditService
from app.modules.fiscal.api.curadoria import require_curador
from app.modules.fiscal.api.matrizes_routers import Pagina
from app.modules.fiscal.application.propostas_service import PropostasService
from app.modules.fiscal.infrastructure.propostas_models import (
    STATUS_PENDENTE,
    MatrizProposta,
)
from app.modules.identity.infrastructure.models import User

router = APIRouter(prefix="/matrizes/propostas", tags=["Matrizes Fiscais"])


class PropostaResponse(BaseModel):
    id: int
    tipo_matriz: str
    acao: str
    chave_resumo: str
    payload: dict
    linha_atual: dict | None
    linha_atual_id: int | None
    fonte: str
    status: str
    motivo_rejeicao: str | None
    revisado_por: str | None
    revisado_em: datetime | None
    created_at: datetime | None

    model_config = {"from_attributes": True}


class RejeitarBody(BaseModel):
    motivo: str | None = Field(default=None, max_length=300)


class LoteBody(BaseModel):
    tipo_matriz: str | None = None
    uf: str | None = None
    ids: list[int] | None = None


async def _email_do(claims: TokenClaims, session: AsyncSession) -> str:
    email = await session.scalar(select(User.email).where(User.id == claims.sub))
    return email or str(claims.sub)


@router.get("", response_model=Pagina[PropostaResponse])
async def listar_propostas(
    status: str = Query(default=STATUS_PENDENTE, description="PENDENTE | APROVADA | REJEITADA"),
    tipo: str | None = Query(default=None, description="mva | enquadramento | fcp | protocolos | aliquotas"),
    uf: str | None = Query(default=None, description="Filtra pela UF da chave"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=50),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    stmt = select(MatrizProposta)
    if status:
        stmt = stmt.where(MatrizProposta.status == status.upper())
    if tipo:
        stmt = stmt.where(MatrizProposta.tipo_matriz == tipo)
    if uf:
        stmt = stmt.where(MatrizProposta.chave_resumo.like(f"{uf.upper()} ·%"))
    stmt = stmt.order_by(MatrizProposta.created_at.desc(), MatrizProposta.id.desc())
    total = await session.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ) or 0
    rows = (await session.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Pagina(items=list(rows), total=total, page=page, page_size=page_size)


@router.get("/resumo")
async def resumo_propostas(
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Pendências por matriz — alimenta o contador da aba Revisão."""
    rows = (await session.execute(
        select(MatrizProposta.tipo_matriz, func.count())
        .where(MatrizProposta.status == STATUS_PENDENTE)
        .group_by(MatrizProposta.tipo_matriz)
    )).all()
    por_tipo = {tipo: n for tipo, n in rows}
    return {"total_pendentes": sum(por_tipo.values()), "por_tipo": por_tipo}


@router.post("/aprovar-lote")
async def aprovar_lote(
    body: LoteBody,
    claims: TokenClaims = Depends(require_curador),
    session: AsyncSession = Depends(tenant_session),
):
    revisor = await _email_do(claims, session)
    resumo = await PropostasService(session).aprovar_lote(
        revisor=revisor, tipo=body.tipo_matriz, uf=body.uf, ids=body.ids
    )
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="matriz_proposta.aprovar_lote",
        entidade="matriz_proposta",
        detalhe={"aprovadas": resumo["aprovadas"], "falhas": len(resumo["falhas"]),
                 "tipo": body.tipo_matriz, "uf": body.uf},
    )
    return resumo


@router.post("/{proposta_id}/aprovar", response_model=PropostaResponse)
async def aprovar_proposta(
    proposta_id: int,
    claims: TokenClaims = Depends(require_curador),
    session: AsyncSession = Depends(tenant_session),
):
    revisor = await _email_do(claims, session)
    p = await PropostasService(session).aprovar(proposta_id, revisor=revisor)
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="matriz_proposta.aprovar",
        entidade="matriz_proposta", entidade_id=str(p.id),
        detalhe={"tipo": p.tipo_matriz, "chave": p.chave_resumo, "acao": p.acao},
    )
    return p


@router.post("/{proposta_id}/rejeitar", response_model=PropostaResponse)
async def rejeitar_proposta(
    proposta_id: int,
    body: RejeitarBody,
    claims: TokenClaims = Depends(require_curador),
    session: AsyncSession = Depends(tenant_session),
):
    revisor = await _email_do(claims, session)
    p = await PropostasService(session).rejeitar(
        proposta_id, revisor=revisor, motivo=body.motivo
    )
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="matriz_proposta.rejeitar",
        entidade="matriz_proposta", entidade_id=str(p.id),
        detalhe={"tipo": p.tipo_matriz, "chave": p.chave_resumo,
                 "motivo": p.motivo_rejeicao},
    )
    return p
