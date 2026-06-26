"""Rotas de dashboard (agregações tenant-scoped)."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.dashboard.application.service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/geral")
async def geral(
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    return await DashboardService(session).geral()


@router.get("/saude")
async def saude(
    ano: str = Query(..., description="Ano da competência (AAAA)"),
    mes: str = Query(..., description="Mês da competência (MM)"),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Lista de empresas com os 4 indicadores estratégicos da competência."""
    return await DashboardService(session).saude(ano, mes)


@router.get("/empresas/{empresa_id}")
async def empresa(
    empresa_id: UUID,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    return await DashboardService(session).empresa(empresa_id)
