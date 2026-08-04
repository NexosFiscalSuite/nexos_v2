"""Rotas de contrapartes (clientes/fornecedores) + lookup de CNPJ (OpenCNPJ)."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.contrapartes.api.schemas import (
    CnpjLookupResponse,
    ContraparteCreate,
    ContraparteResponse,
    ContraparteUpdate,
)
from app.modules.contrapartes.application.service import ContraparteService
from app.shared.cnpj_lookup import consultar_opencnpj

router = APIRouter(prefix="/contrapartes", tags=["Cadastros"])


class PaginaContrapartes(BaseModel):
    """Envelope de paginação: uma empresa acumula milhares de fornecedores
    (upsert dos XMLs) — a tela busca uma página por vez."""

    items: list[ContraparteResponse]
    total: int
    page: int
    page_size: int


@router.get("/empresas/{empresa_id}", response_model=PaginaContrapartes)
async def listar(
    empresa_id: UUID,
    tipo: str | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=50),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    items, total = await ContraparteService(session).list(
        empresa_id, tipo, search, page=page, page_size=page_size
    )
    return PaginaContrapartes(items=items, total=total, page=page, page_size=page_size)


@router.post("/empresas/{empresa_id}", response_model=ContraparteResponse, status_code=status.HTTP_201_CREATED)
async def criar(
    empresa_id: UUID,
    body: ContraparteCreate,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    return await ContraparteService(session).create(
        tenant_id=claims.tid, empresa_id=empresa_id,
        tipo=body.tipo, cnpj=body.cnpj,
        **body.model_dump(exclude={"tipo", "cnpj"}),
    )


@router.patch("/{contraparte_id}", response_model=ContraparteResponse)
async def atualizar(
    contraparte_id: UUID,
    body: ContraparteUpdate,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    return await ContraparteService(session).update(contraparte_id, body.model_dump(exclude_unset=True))


# ── Lookup de CNPJ (OpenCNPJ) — usado por empresas e contrapartes ────────────
# Endpoint SÍNCRONO de propósito: a chamada urllib é bloqueante e o FastAPI a
# executa num threadpool, sem travar o event loop.
lookup_router = APIRouter(prefix="/cnpj", tags=["Lookup"])


@lookup_router.get("/{cnpj}", response_model=CnpjLookupResponse)
def consultar_cnpj(
    cnpj: str,
    contexto: str = "empresa",
    claims: TokenClaims = Depends(get_current_claims),
):
    return consultar_opencnpj(cnpj, contexto if contexto in ("empresa", "contraparte") else "empresa")
