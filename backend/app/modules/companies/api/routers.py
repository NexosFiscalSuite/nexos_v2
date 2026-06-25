"""Rotas de empresas (clientes do escritório)."""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.rbac import Role, require_role
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.audit.application.service import AuditService
from app.modules.companies.api.schemas import (
    EmpresaCreate,
    EmpresaResponse,
    EmpresaUpdate,
)
from app.modules.companies.application.service import EmpresaService

router = APIRouter(prefix="/empresas", tags=["Empresas"])


@router.get("", response_model=list[EmpresaResponse])
async def list_empresas(
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    return await EmpresaService(session).list_for(claims)


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
