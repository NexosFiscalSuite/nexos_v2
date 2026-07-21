"""Rotas da verificação de IBS/CBS (Reforma Tributária — ano-teste 2026)."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.core.storage import get_storage
from app.modules.companies.infrastructure.repositories import EmpresaRepository
from app.modules.fiscal.application.ibscbs_carta import gerar_carta
from app.modules.fiscal.application.ibscbs_service import IbsCbsService
from app.shared.domain.value_objects import only_digits

router = APIRouter(prefix="/fiscal/ibs-cbs", tags=["IBS/CBS 2026"])


@router.get("/verificacao")
async def verificacao(
    empresa_id: UUID | None = Query(default=None, description="Limita a uma empresa"),
    ano: str | None = Query(default=None, description="Competência: ano (AAAA)"),
    mes: str | None = Query(default=None, description="Competência: mês (MM)"),
    fluxo: str | None = Query(default=None, description="entrada | saida"),
    status: str | None = Query(default=None,
                               description="Lista itens só desta situação (ex.: OK)"),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Confronta o destaque de IBS/CBS dos XMLs com as alíquotas de teste de
    2026 (IBS 0,1% + CBS 0,9%): sem destaque, alíquota errada ou conta que não
    fecha viram apontamento, com ranking de emitentes problemáticos. Com
    `status`, a lista de itens traz a situação pedida (inclusive OK/dispensado,
    com a justificativa da classificação) — resumo e ranking não mudam."""
    return await IbsCbsService(session).verificar(
        empresa_id=empresa_id, ano=ano, mes=mes, fluxo=fluxo, apenas_status=status
    )


@router.get("/carta")
async def carta_correcao(
    cnpj_emit: str = Query(..., description="CNPJ do emitente apontado"),
    empresa_id: UUID | None = Query(default=None),
    ano: str | None = Query(default=None),
    mes: str | None = Query(default=None),
    fluxo: str | None = Query(default=None, description="entrada | saida"),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Carta timbrada (PDF) solicitando a correção do destaque de IBS/CBS,
    com o quadro item a item (veio × devido) do emitente no filtro atual."""
    resultado = await IbsCbsService(session).verificar(
        empresa_id=empresa_id, ano=ano, mes=mes, fluxo=fluxo, limite_itens=2000
    )
    alvo = only_digits(cnpj_emit)
    itens = [i for i in resultado["itens"] if only_digits(i.get("cnpj_emit") or "") == alvo]
    if not itens:
        raise NotFoundError("Nenhum apontamento para este emitente no filtro atual.")

    cliente_nome = None
    if empresa_id:
        empresa = await EmpresaRepository(session).by_id(empresa_id)
        cliente_nome = empresa.razao_social if empresa else None

    competencia = f"{mes}/{ano}" if ano and mes else (ano or "período completo")
    pdf = gerar_carta(
        destinatario_nome=itens[0].get("emitente") or "Emitente",
        destinatario_cnpj=alvo,
        fluxo=fluxo or "entrada",
        competencia=competencia,
        itens=itens,
        cliente_nome=cliente_nome,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="carta-ibscbs-{alvo}.pdf"'},
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
