"""Rotas do relatório de divergências de ICMS-ST (REL_Divergencia_ST)."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.fiscal.api.auditoria_schemas import DivergenciasStResponse
from app.modules.fiscal.application.auditoria_query import listar_divergencias
from app.modules.fiscal.application.reprocess_service import ReprocessService
from app.modules.fiscal.domain.st.errors import ErroST

router = APIRouter(prefix="/auditoria/st", tags=["Auditoria ST"])


@router.get("/catalogo-erros")
async def catalogo_erros(claims: TokenClaims = Depends(get_current_claims)):
    """Catálogo do motor: código → mensagem + ação sugerida. A régua de conduta
    do analista sai do código-fonte e vai para a tela (uma fonte só)."""
    return [
        {"codigo": e.codigo, "mensagem": e.mensagem, "acao": e.acao_sugerida}
        for e in ErroST
    ]


@router.post("/reprocessar-pendentes")
async def reprocessar_pendentes(
    empresa_id: UUID | None = Query(default=None, description="Limita a uma empresa (opcional)"),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Retroatividade: re-aplica o De/Para CFOP e re-audita as notas travadas
    (gargalo de CFOP ou NAO_AUDITAVEL por matriz faltante)."""
    return await ReprocessService(session).reprocessar_pendentes(empresa_id)


@router.get("/divergencias", response_model=DivergenciasStResponse)
async def divergencias(
    empresa_id: UUID = Query(..., description="Empresa (cliente) auditada"),
    fluxo: str | None = Query(default=None, description="entrada (tpNF=0) | saida (tpNF=1)"),
    data_inicio: str | None = Query(default=None, description="Emissão >= AAAA-MM-DD"),
    data_fim: str | None = Query(default=None, description="Emissão <= AAAA-MM-DD"),
    cnpj: str | None = Query(default=None, description="CNPJ do fornecedor (emitente)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=500),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Itens com ICMS-ST divergente ou não auditável: declarado × calculado, a
    diferença e a memória de cálculo (JSON) para o modal de explicação."""
    return await listar_divergencias(
        session,
        empresa_id=empresa_id,
        fluxo=fluxo,
        data_inicio=data_inicio,
        data_fim=data_fim,
        cnpj=cnpj,
        page=page,
        page_size=page_size,
    )
