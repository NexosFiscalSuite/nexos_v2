"""Rotas do relatório de divergências de ICMS-ST (REL_Divergencia_ST)."""
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.audit.application.service import AuditService
from app.modules.companies.infrastructure.repositories import EmpresaRepository
from app.modules.fiscal.api.auditoria_schemas import DivergenciasStResponse
from app.modules.fiscal.application.auditoria_query import (
    diagnostico_st,
    exportar_divergencias,
    listar_divergencias,
)
from app.modules.fiscal.application.matrizes_saude import ultima_atualizacao_matrizes
from app.modules.fiscal.application.reprocess_service import ReprocessService
from app.modules.fiscal.application.st_audit_service import StAuditService
from app.modules.fiscal.application.st_carta import gerar_carta_st
from app.modules.fiscal.application.st_diagnostico import gerar_diagnostico_pdf
from app.modules.fiscal.application.st_export import gerar_xlsx_divergencias
from app.modules.fiscal.application.triagem_service import definir_triagem
from app.modules.fiscal.domain.st.errors import ErroST
from app.modules.fiscal.infrastructure.repositories import NotaRepository
from app.modules.identity.infrastructure.models import User
from app.shared.domain.value_objects import only_digits

router = APIRouter(prefix="/auditoria/st", tags=["Auditoria ST"])


async def _email_do(claims: TokenClaims, session: AsyncSession) -> str:
    email = await session.scalar(select(User.email).where(User.id == claims.sub))
    return email or str(claims.sub)


class TriagemItemRef(BaseModel):
    nota_id: UUID
    numero_item: int


class TriagemBody(BaseModel):
    itens: list[TriagemItemRef] = Field(..., min_length=1)
    status: str = Field(..., description="EM_ABERTO | COBRADA | JUSTIFICADA | ACEITA")
    observacao: str | None = Field(default=None, max_length=300)


@router.post("/triagem")
async def triagem_divergencias(
    body: TriagemBody,
    empresa_id: UUID = Query(..., description="Empresa (cliente) auditada"),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Triagem do pós-auditoria: registra o que o escritório decidiu sobre os
    itens divergentes (cobrada/justificada/aceita), com quem/quando na
    trilha. EM_ABERTO desfaz. A decisão sobrevive ao reprocessamento."""
    revisor = await _email_do(claims, session)
    resumo = await definir_triagem(
        session, tenant_id=claims.tid, empresa_id=empresa_id,
        itens=[(i.nota_id, i.numero_item) for i in body.itens],
        status=body.status, observacao=body.observacao, por=revisor,
    )
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="st.triagem",
        entidade="empresa", entidade_id=str(empresa_id),
        detalhe={"status": body.status, "itens": len(body.itens), **resumo},
    )
    return resumo


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


@router.post("/notas/{nota_id}/confirmar-sem-cte")
async def confirmar_sem_cte(
    nota_id: UUID,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Confirma que a nota NÃO tem CT-e (frete por conta do tomador sem
    conhecimento): grava quem/quando — trilha de auditoria — e reaudita a
    nota na hora, destravando o ERRO_FRETE_PENDENTE_CTE."""
    nota = await NotaRepository(session).by_id(nota_id)
    if nota is None:
        raise NotFoundError("Nota não encontrada.")
    email = await session.scalar(select(User.email).where(User.id == claims.sub))
    nota.frete_sem_cte_confirmado = True
    nota.frete_confirmado_por = email
    nota.frete_confirmado_em = datetime.now(UTC)
    await session.flush()
    await StAuditService(session).auditar_nota(nota.empresa_id, nota_id)
    return {"confirmado": True, "por": email}


@router.get("/diagnostico")
async def diagnostico(
    empresa_id: UUID = Query(..., description="Empresa (cliente) auditada"),
    data_inicio: str | None = Query(default=None, description="AAAA-MM-DD (vazio = tudo)"),
    data_fim: str | None = Query(default=None),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Diagnóstico executivo em PDF: conformidade e dinheiro em jogo por
    competência + top fornecedores — o entregável do serviço de auditoria
    (inclusive retroativa: sem datas, cobre TUDO que foi importado)."""
    dados = await diagnostico_st(
        session, empresa_id=empresa_id, data_inicio=data_inicio, data_fim=data_fim
    )
    if not dados["competencias"]:
        raise NotFoundError("Nenhum item auditado no período para diagnosticar.")
    empresa = await EmpresaRepository(session).by_id(empresa_id)
    pdf = gerar_diagnostico_pdf(
        empresa_nome=(empresa.razao_social if empresa else "Empresa"),
        empresa_cnpj=(empresa.cnpj if empresa else None),
        dados=dados,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="diagnostico-st.pdf"'},
    )


@router.post("/ciencia-legislacao")
async def ciencia_legislacao(
    empresa_id: UUID = Query(..., description="Empresa do documento a emitir"),
    destino: str = Query(..., description="carta | export | diagnostico"),
    competencia: str | None = Query(default=None, description="MM/AAAA do filtro"),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Trilha do aviso de legislação (Fase 2): registra QUEM confirmou ter
    verificado a norma vigente antes de emitir o documento — mesmo padrão da
    confirmação de nota sem CT-e (quem/quando ficam na auditoria)."""
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="st.ciencia_legislacao",
        entidade="empresa", entidade_id=str(empresa_id),
        detalhe={"destino": destino, "competencia": competencia},
    )
    return {"ok": True, "registrado_em": datetime.now(UTC).isoformat()}


@router.get("/carta")
async def carta_st(
    empresa_id: UUID = Query(..., description="Empresa (cliente) auditada"),
    cnpj_emit: str = Query(..., description="CNPJ do emitente apontado"),
    fluxo: str | None = Query(default=None),
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Carta timbrada (PDF) de cobrança/correção de ICMS-ST do emitente:
    itens DIVERGENTES no filtro, EXCETO antecipações (ERRO_111 é guia do
    próprio cliente — não há o que cobrar do fornecedor)."""
    res = await listar_divergencias(
        session, empresa_id=empresa_id, fluxo=fluxo,
        data_inicio=data_inicio, data_fim=data_fim, cnpj=cnpj_emit, page_size=500,
    )
    itens = [
        i for i in res["itens"]
        if i["status"] == "DIVERGENTE" and "ERRO_111" not in (i["codigo_erro"] or "")
    ]
    if not itens:
        raise NotFoundError("Nenhuma divergência cobrável deste emitente no filtro atual.")

    empresa = await EmpresaRepository(session).by_id(empresa_id)
    competencia = (
        f"{data_inicio[5:7]}/{data_inicio[:4]}" if data_inicio and len(data_inicio) >= 7
        else "período completo"
    )
    alvo = only_digits(cnpj_emit)
    # Carimbo do aviso de legislação: quando a base de matrizes foi verificada
    # por um humano pela última vez (Fase 2 da automação).
    verificacao = await ultima_atualizacao_matrizes(session)
    pdf = gerar_carta_st(
        destinatario_nome=itens[0].get("fornecedor") or "Emitente",
        destinatario_cnpj=alvo,
        fluxo=fluxo or "entrada",
        competencia=competencia,
        itens=itens,
        cliente_nome=empresa.razao_social if empresa else None,
        verificacao_matrizes=verificacao.strftime("%d/%m/%Y") if verificacao else None,
    )
    # Gerar a carta É a cobrança: marca os itens como COBRADA na triagem —
    # sem sobrescrever decisão que o analista já tenha tomado.
    await definir_triagem(
        session, tenant_id=claims.tid, empresa_id=empresa_id,
        itens=[(UUID(i["nota_id"]), i["numero_item"]) for i in itens],
        status="COBRADA",
        observacao=f"Carta gerada em {datetime.now(UTC).strftime('%d/%m/%Y')}",
        por=await _email_do(claims, session),
        apenas_em_aberto=True,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="carta-st-{alvo}.pdf"'},
    )


@router.get("/divergencias", response_model=DivergenciasStResponse)
async def divergencias(
    empresa_id: UUID = Query(..., description="Empresa (cliente) auditada"),
    fluxo: str | None = Query(default=None, description="entrada (tpNF=0) | saida (tpNF=1)"),
    data_inicio: str | None = Query(default=None, description="Emissão >= AAAA-MM-DD"),
    data_fim: str | None = Query(default=None, description="Emissão <= AAAA-MM-DD"),
    cnpj: str | None = Query(default=None, description="CNPJ do fornecedor (emitente)"),
    status: str | None = Query(default=None, description="DIVERGENTE | NAO_AUDITAVEL"),
    codigo_erro: str | None = Query(default=None, description="Filtra por código do motor"),
    q: str | None = Query(default=None, description="Busca livre: fornecedor/produto/NF/NCM"),
    triagem: str | None = Query(default=None, description="EM_ABERTO | COBRADA | JUSTIFICADA | ACEITA"),
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
        status=status,
        codigo_erro=codigo_erro,
        q=q,
        triagem=triagem,
        page=page,
        page_size=page_size,
    )


@router.get("/divergencias/export")
async def divergencias_export(
    empresa_id: UUID = Query(...),
    fluxo: str | None = Query(default=None),
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
    cnpj: str | None = Query(default=None),
    status: str | None = Query(default=None),
    codigo_erro: str | None = Query(default=None),
    q: str | None = Query(default=None),
    triagem: str | None = Query(default=None),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Planilha Excel do filtro atual, SEM paginação: aba item a item + aba
    consolidada por fornecedor (anexo de cobrança/pedido de ressarcimento)."""
    itens = await exportar_divergencias(
        session, empresa_id=empresa_id, fluxo=fluxo, data_inicio=data_inicio,
        data_fim=data_fim, cnpj=cnpj, status=status, codigo_erro=codigo_erro, q=q,
        triagem=triagem,
    )
    if not itens:
        raise NotFoundError("Nenhuma divergência no filtro atual.")
    periodo = (
        f"{data_inicio[5:7]}/{data_inicio[:4]}" if data_inicio and len(data_inicio) >= 7
        else "período completo"
    )
    xlsx = gerar_xlsx_divergencias(itens, periodo)
    nome = f"divergencias-st-{periodo.replace('/', '-')}.xlsx"
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
