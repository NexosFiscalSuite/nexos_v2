"""CRUD de Matrizes Fiscais — tabelas GLOBAIS (sem RLS): MVA, Enquadramento e FCP.

Leitura: qualquer usuário autenticado. Escrita: supervisor+ (a regra vale para
todos os tenants do escritório). Um factory registra os 4 verbos por matriz para
não repetir o mesmo CRUD três vezes.
"""
from collections.abc import Callable

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.core.exceptions import NotFoundError
from app.core.rbac import Role, require_role
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.audit.application.service import AuditService
from app.modules.fiscal.api.matrizes_schemas import (
    MatrizEnquadramentoCreate,
    MatrizEnquadramentoResponse,
    MatrizEnquadramentoUpdate,
    MatrizFcpCreate,
    MatrizFcpResponse,
    MatrizFcpUpdate,
    MatrizMvaCreate,
    MatrizMvaResponse,
    MatrizMvaUpdate,
)
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
)
from app.shared.domain.value_objects import only_digits

router = APIRouter(prefix="/matrizes", tags=["Matrizes Fiscais"])


def _registrar_crud(
    sub: str,
    modelo: type[Base],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    response_schema: type[BaseModel],
    *,
    entidade: str,
    detalhe: Callable[[object], dict],
    filtrar: Callable | None = None,
) -> None:
    """Registra GET/POST/PATCH/DELETE de uma matriz sob /matrizes/{sub}."""

    @router.get(f"/{sub}", response_model=list[response_schema], name=f"listar_{sub}")
    async def _listar(
        uf: str | None = Query(default=None, description="Filtra por UF destino"),
        ncm: str | None = Query(default=None, description="Filtra por NCM (prefixo)"),
        claims: TokenClaims = Depends(get_current_claims),
        session: AsyncSession = Depends(tenant_session),
    ):
        stmt = select(modelo)
        if filtrar is not None:
            stmt = filtrar(stmt, uf, ncm)
        return list((await session.execute(stmt)).scalars().all())

    @router.post(
        f"/{sub}", response_model=response_schema,
        status_code=status.HTTP_201_CREATED, name=f"criar_{sub}",
    )
    async def _criar(
        body: create_schema,  # type: ignore[valid-type]
        claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
        session: AsyncSession = Depends(tenant_session),
    ):
        linha = modelo(**body.normalizado())
        session.add(linha)
        await session.flush()
        await AuditService(session).registrar(
            tenant_id=claims.tid, user_id=claims.sub, acao=f"{entidade}.criar",
            entidade=entidade, entidade_id=str(linha.id), detalhe=detalhe(linha),
        )
        return linha

    @router.patch(f"/{sub}/{{linha_id}}", response_model=response_schema, name=f"editar_{sub}")
    async def _editar(
        linha_id: int,
        body: update_schema,  # type: ignore[valid-type]
        claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
        session: AsyncSession = Depends(tenant_session),
    ):
        linha = await session.get(modelo, linha_id)
        if linha is None:
            raise NotFoundError("Matriz não encontrada.")
        for campo, valor in body.normalizado().items():
            setattr(linha, campo, valor)
        await session.flush()
        await AuditService(session).registrar(
            tenant_id=claims.tid, user_id=claims.sub, acao=f"{entidade}.editar",
            entidade=entidade, entidade_id=str(linha.id), detalhe=detalhe(linha),
        )
        return linha

    @router.delete(
        f"/{sub}/{{linha_id}}", status_code=status.HTTP_204_NO_CONTENT, name=f"remover_{sub}",
    )
    async def _remover(
        linha_id: int,
        claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
        session: AsyncSession = Depends(tenant_session),
    ):
        linha = await session.get(modelo, linha_id)
        if linha is None:
            raise NotFoundError("Matriz não encontrada.")
        await session.delete(linha)
        await AuditService(session).registrar(
            tenant_id=claims.tid, user_id=claims.sub, acao=f"{entidade}.remover",
            entidade=entidade, entidade_id=str(linha_id), detalhe={},
        )


def _ordenar(modelo, *cols):
    """Filtro de UF/NCM + ordenação, fechado sobre o modelo da matriz."""
    def _f(stmt, uf, ncm):
        if uf:
            stmt = stmt.where(modelo.uf_destino == uf.upper())
        if ncm:
            stmt = stmt.where(modelo.ncm.like(f"{only_digits(ncm)}%"))
        return stmt.order_by(*cols)
    return _f


_registrar_crud(
    "mva", MatrizMva, MatrizMvaCreate, MatrizMvaUpdate, MatrizMvaResponse,
    entidade="matriz_mva",
    detalhe=lambda m: {"ncm": m.ncm, "cest": m.cest, "uf": m.uf_destino},
    filtrar=_ordenar(MatrizMva, MatrizMva.uf_destino, MatrizMva.ncm, MatrizMva.cest),
)
_registrar_crud(
    "enquadramento", MatrizEnquadramentoSt, MatrizEnquadramentoCreate,
    MatrizEnquadramentoUpdate, MatrizEnquadramentoResponse,
    entidade="matriz_enquadramento",
    detalhe=lambda m: {"ncm": m.ncm, "cest": m.cest, "uf": m.uf_destino, "regime": m.regime},
    filtrar=_ordenar(
        MatrizEnquadramentoSt, MatrizEnquadramentoSt.uf_destino,
        MatrizEnquadramentoSt.ncm, MatrizEnquadramentoSt.cest,
    ),
)
_registrar_crud(
    "fcp", MatrizFcp, MatrizFcpCreate, MatrizFcpUpdate, MatrizFcpResponse,
    entidade="matriz_fcp",
    detalhe=lambda m: {"uf": m.uf_destino, "ncm": m.ncm, "fcp_st": str(m.aliq_fcp_st)},
    filtrar=_ordenar(MatrizFcp, MatrizFcp.uf_destino, MatrizFcp.ncm),
)
