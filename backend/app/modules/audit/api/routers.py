"""Rotas da trilha de auditoria (somente supervisor/admin)."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Role, require_role
from app.core.rls import tenant_session
from app.core.security import TokenClaims
from app.modules.audit.api.schemas import AuditResponse
from app.modules.audit.application.service import AuditService

router = APIRouter(prefix="/audit", tags=["Auditoria"])


@router.get("", response_model=list[AuditResponse])
async def listar(
    acao: str | None = None,
    user_id: UUID | None = None,
    dias: int | None = Query(default=30, ge=1, le=365),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    return await AuditService(session).listar(acao=acao, user_id=user_id, dias=dias, limit=limit, offset=offset)


@router.get("/acoes", response_model=list[str])
async def acoes(
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    return await AuditService(session).acoes()
