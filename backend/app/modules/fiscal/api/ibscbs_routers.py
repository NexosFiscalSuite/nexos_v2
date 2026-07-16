"""Rotas da verificação de IBS/CBS (Reforma Tributária — ano-teste 2026)."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.core.storage import get_storage
from app.modules.fiscal.application.ibscbs_service import IbsCbsService

router = APIRouter(prefix="/fiscal/ibs-cbs", tags=["IBS/CBS 2026"])


@router.get("/verificacao")
async def verificacao(
    empresa_id: UUID | None = Query(default=None, description="Limita a uma empresa"),
    ano: str | None = Query(default=None, description="Competência: ano (AAAA)"),
    mes: str | None = Query(default=None, description="Competência: mês (MM)"),
    fluxo: str | None = Query(default=None, description="entrada | saida"),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Confronta o destaque de IBS/CBS dos XMLs com as alíquotas de teste de
    2026 (IBS 0,1% + CBS 0,9%): sem destaque, alíquota errada ou conta que não
    fecha viram apontamento, com ranking de emitentes problemáticos."""
    return await IbsCbsService(session).verificar(
        empresa_id=empresa_id, ano=ano, mes=mes, fluxo=fluxo
    )


@router.post("/reprocessar")
async def reprocessar(
    empresa_id: UUID | None = Query(default=None),
    ano: str | None = Query(default=None),
    mes: str | None = Query(default=None),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Backfill: re-lê os XMLs já armazenados e preenche os campos de IBS/CBS
    dos itens — para notas importadas antes deste módulo existir."""
    return await IbsCbsService(session).reprocessar(
        get_storage(), empresa_id=empresa_id, ano=ano, mes=mes
    )
