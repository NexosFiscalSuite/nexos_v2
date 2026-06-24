"""Rotas de dashboard (agregações tenant-scoped)."""
from uuid import UUID

from fastapi import APIRouter, Depends
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


@router.get("/empresas/{empresa_id}")
async def empresa(
    empresa_id: UUID,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    return await DashboardService(session).empresa(empresa_id)
