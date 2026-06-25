"""CRUD de Matrizes Fiscais (V1: MVA Original) — tabela GLOBAL (sem RLS).

Leitura: qualquer usuário autenticado. Escrita: supervisor+ (a regra vale para
todos os tenants do escritório, então é operação sensível).
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.rbac import Role, require_role
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.audit.application.service import AuditService
from app.modules.fiscal.api.matrizes_schemas import (
    MatrizMvaCreate,
    MatrizMvaResponse,
    MatrizMvaUpdate,
)
from app.modules.fiscal.infrastructure.matrizes_models import MatrizMva
from app.shared.domain.value_objects import only_digits

router = APIRouter(prefix="/matrizes", tags=["Matrizes Fiscais"])


@router.get("/mva", response_model=list[MatrizMvaResponse])
async def listar_mva(
    uf: str | None = Query(default=None, description="Filtra por UF destino"),
    ncm: str | None = Query(default=None, description="Filtra por NCM (prefixo)"),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    stmt = select(MatrizMva)
    if uf:
        stmt = stmt.where(MatrizMva.uf_destino == uf.upper())
    if ncm:
        stmt = stmt.where(MatrizMva.ncm.like(f"{only_digits(ncm)}%"))
    stmt = stmt.order_by(MatrizMva.uf_destino, MatrizMva.ncm, MatrizMva.cest)
    return list((await session.execute(stmt)).scalars().all())


@router.post("/mva", response_model=MatrizMvaResponse, status_code=status.HTTP_201_CREATED)
async def criar_mva(
    body: MatrizMvaCreate,
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    linha = MatrizMva(**body.normalizado())
    session.add(linha)
    await session.flush()
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="matriz_mva.criar",
        entidade="matriz_mva", entidade_id=str(linha.id),
        detalhe={"ncm": linha.ncm, "cest": linha.cest, "uf": linha.uf_destino},
    )
    return linha


@router.patch("/mva/{linha_id}", response_model=MatrizMvaResponse)
async def editar_mva(
    linha_id: int,
    body: MatrizMvaUpdate,
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    linha = await session.get(MatrizMva, linha_id)
    if linha is None:
        raise NotFoundError("Matriz de MVA não encontrada.")
    for campo, valor in body.normalizado().items():
        setattr(linha, campo, valor)
    await session.flush()
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="matriz_mva.editar",
        entidade="matriz_mva", entidade_id=str(linha.id),
        detalhe={"ncm": linha.ncm, "cest": linha.cest, "uf": linha.uf_destino},
    )
    return linha


@router.delete("/mva/{linha_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_mva(
    linha_id: int,
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    linha = await session.get(MatrizMva, linha_id)
    if linha is None:
        raise NotFoundError("Matriz de MVA não encontrada.")
    await session.delete(linha)
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="matriz_mva.remover",
        entidade="matriz_mva", entidade_id=str(linha_id), detalhe={},
    )
