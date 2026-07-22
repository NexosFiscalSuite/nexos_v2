"""Consulta de divergências de ICMS-ST (REL_Divergencia_ST do Vault).

Lê a `auditoria_icms_st` e cruza com a nota (fornecedor, UFs, período) e com os
CT-e vinculados (ADR-0001). Retorna o que precisa de atenção do analista:
itens DIVERGENTE e NAO_AUDITAVEL (com o motivo). DIVERGENTE primeiro, depois o
maior valor de diferença.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.infrastructure.models import (
    AuditoriaIcmsSt,
    NfeCteVinculo,
    Nota,
    NotaItem,
)
from app.shared.domain.value_objects import only_digits


async def listar_divergencias(
    session: AsyncSession,
    *,
    empresa_id: UUID,
    fluxo: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    cnpj: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    a, n = AuditoriaIcmsSt, Nota
    where = [a.empresa_id == empresa_id, a.status != "OK"]   # DIVERGENTE + NAO_AUDITAVEL
    if fluxo:   # abas Entradas (tpNF=0) × Saídas (tpNF=1)
        where.append(n.fluxo == fluxo)
    # data_emissao é 'YYYY-MM-DD' (ISO): comparação lexicográfica = cronológica.
    if data_inicio:
        where.append(n.data_emissao >= data_inicio)
    if data_fim:
        where.append(n.data_emissao <= data_fim)
    if cnpj:
        where.append(n.cnpj_emit == only_digits(cnpj))

    page = max(1, page)
    page_size = max(1, min(500, page_size))

    total = await session.scalar(
        select(func.count()).select_from(a).join(n, a.nota_id == n.id).where(*where)
    )

    # ── Agregados do período inteiro (sem paginação): o dinheiro em jogo. ──
    # diferença = XML − calculado: negativa = a recolher; positiva = a favor.
    # Antecipação (ERRO_111) é obrigação do PRÓPRIO cliente — sai da conta do
    # fornecedor e ganha card próprio.
    d = a.vicms_st_divergencia
    eh_antecipacao = func.coalesce(a.codigo_erro, "").like("%ERRO_111%")
    divergente = a.status == "DIVERGENTE"
    agg = (await session.execute(
        select(
            func.coalesce(func.sum(case(
                (and_(divergente, d < 0, ~eh_antecipacao), -d), else_=0)), 0),
            func.coalesce(func.sum(case(
                (and_(divergente, d > 0), d), else_=0)), 0),
            func.coalesce(func.sum(case((eh_antecipacao, -d), else_=0)), 0),
            func.coalesce(func.sum(case((divergente, 1), else_=0)), 0),
            func.coalesce(func.sum(case((a.status == "NAO_AUDITAVEL", 1), else_=0)), 0),
        ).select_from(a).join(n, a.nota_id == n.id).where(*where)
    )).one()
    resumo = {
        "a_recolher": float(agg[0]), "a_favor": float(agg[1]),
        "antecipacao": float(agg[2]),
        "divergentes": int(agg[3]), "nao_auditaveis": int(agg[4]),
    }

    # Ranking de emitentes pelo valor COBRÁVEL (divergências sem ERRO_111):
    # quem cobrar primeiro / onde a parametrização mais erra.
    rank_rows = (await session.execute(
        select(
            n.cnpj_emit, n.nome_emit,
            func.count().label("itens"),
            func.coalesce(func.sum(func.abs(d)), 0).label("valor"),
        )
        .select_from(a).join(n, a.nota_id == n.id)
        .where(*where, divergente, ~eh_antecipacao)
        .group_by(n.cnpj_emit, n.nome_emit)
        .order_by(func.coalesce(func.sum(func.abs(d)), 0).desc())
        .limit(20)
    )).all()
    ranking = [
        {"cnpj": r[0], "nome": r[1], "itens": int(r[2]), "valor": float(r[3] or 0)}
        for r in rank_rows
    ]
    it = NotaItem
    res = await session.execute(
        select(a, n, it.descricao, it.codigo, it.ncm, it.cest)
        .join(n, a.nota_id == n.id)
        # LEFT JOIN: o item dá nome/NCM/CEST à linha (a auditoria guarda só o nº).
        .outerjoin(it, and_(it.nota_id == a.nota_id, it.numero_item == a.numero_item))
        .where(*where)
        # DIVERGENTE ('D') antes de NAO_AUDITAVEL ('N'); depois a maior diferença.
        .order_by(a.status.asc(), func.abs(a.vicms_st_divergencia).desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    linhas = res.all()

    # CT-e vinculados por chave de NF-e (badge 🚚 do ADR-0001).
    chaves = {linha[0].chave_acesso for linha in linhas}
    ctes_por_chave: dict[str, list[str]] = {}
    if chaves:
        vinc = await session.execute(
            select(NfeCteVinculo.chave_nfe, NfeCteVinculo.chave_cte).where(
                NfeCteVinculo.empresa_id == empresa_id,
                NfeCteVinculo.chave_nfe.in_(chaves),
            )
        )
        for chave_nfe, chave_cte in vinc.all():
            ctes_por_chave.setdefault(chave_nfe, []).append(chave_cte)

    itens = [
        {
            "chave_acesso": a_row.chave_acesso,
            "numero_item": a_row.numero_item,
            "descricao": descricao,
            "codigo": codigo,
            "ncm": ncm,
            "cest": cest,
            "numero_nota": n_row.numero,
            "fornecedor": n_row.nome_emit,
            "cnpj_emit": n_row.cnpj_emit,
            "uf_origem": n_row.uf_emit,
            "uf_destino": n_row.uf_dest,
            "data_emissao": n_row.data_emissao,
            "fluxo": n_row.fluxo,
            "cst_csosn": a_row.cst_csosn,
            "mod_bc_st": a_row.mod_bc_st,
            "pmva_xml": a_row.pmva_xml,
            "pmva_calculada": a_row.pmva_calculada,
            "vbc_st_xml": a_row.vbc_st_xml,
            "vbc_st_calculado": a_row.vbc_st_calculado,
            "vicms_st_xml": a_row.vicms_st_xml,
            "vicms_st_calculado": a_row.vicms_st_calculado,
            "diferenca": a_row.vicms_st_divergencia,   # XML − calculado (negativo = a recolher)
            "vfcp_st_xml": a_row.vfcp_st_xml,
            "vfcp_st_calculado": a_row.vfcp_st_calculado,
            "status": a_row.status,
            "codigo_erro": a_row.codigo_erro,
            "observacao": a_row.observacao,
            "memoria": a_row.memoria,
            "ctes_vinculados": ctes_por_chave.get(a_row.chave_acesso, []),
        }
        for a_row, n_row, descricao, codigo, ncm, cest in linhas
    ]
    return {
        "total": total or 0, "page": page, "page_size": page_size, "itens": itens,
        "resumo": resumo, "ranking_fornecedores": ranking,
    }
