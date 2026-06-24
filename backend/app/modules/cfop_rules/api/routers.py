"""Rotas das regras De/Para CFOP -> Tipo de Item."""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Role, require_role
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.cfop_rules.api.schemas import (
    CfopRegraCreate,
    CfopRegraResponse,
    CfopRegraUpdate,
)
from app.modules.cfop_rules.application.service import CfopRegraService

router = APIRouter(prefix="/cfop-regras", tags=["Regras CFOP"])


@router.get("", response_model=list[CfopRegraResponse])
async def listar(
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    return await CfopRegraService(session).list()


@router.post("", response_model=CfopRegraResponse, status_code=status.HTTP_201_CREATED)
async def criar(
    body: CfopRegraCreate,
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    return await CfopRegraService(session).create(tenant_id=claims.tid, **body.model_dump())


@router.patch("/{rid}", response_model=CfopRegraResponse)
async def atualizar(
    rid: UUID,
    body: CfopRegraUpdate,
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    return await CfopRegraService(session).update(rid, body.model_dump(exclude_unset=True))


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir(
    rid: UUID,
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    await CfopRegraService(session).delete(rid)
