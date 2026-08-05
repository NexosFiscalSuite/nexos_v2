"""Consulta de divergências de ICMS-ST (REL_Divergencia_ST do Vault).

Lê a `auditoria_icms_st` e cruza com a nota (fornecedor, UFs, período) e com os
CT-e vinculados (ADR-0001). Retorna o que precisa de atenção do analista:
itens DIVERGENTE e NAO_AUDITAVEL (com o motivo). DIVERGENTE primeiro, depois o
maior valor de diferença.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.infrastructure.models import (
    TRIAGENS,
    AuditoriaIcmsSt,
    DivergenciaTriagem,
    NfeCteVinculo,
    Nota,
    NotaItem,
)
from app.shared.domain.value_objects import only_digits

_A, _N, _IT, _T = AuditoriaIcmsSt, Nota, NotaItem, DivergenciaTriagem
# LEFT JOIN do item: dá nome/NCM/CEST à linha (a auditoria guarda só o nº).
_J_ITEM = and_(_IT.nota_id == _A.nota_id, _IT.numero_item == _A.numero_item)
# LEFT JOIN da triagem: a decisão do analista sobrevive ao reprocessamento.
_J_TRIAGEM = and_(_T.nota_id == _A.nota_id, _T.numero_item == _A.numero_item)


def _filtros(
    *,
    empresa_id: UUID,
    fluxo: str | None,
    data_inicio: str | None,
    data_fim: str | None,
    cnpj: str | None,
    status: str | None = None,
    codigo_erro: str | None = None,
    q: str | None = None,
    triagem: str | None = None,
) -> list:
    a, n, it = _A, _N, _IT
    where = [a.empresa_id == empresa_id, a.status != "OK"]   # DIVERGENTE + NAO_AUDITAVEL
    if triagem == "EM_ABERTO":
        where.append(_T.id.is_(None))            # sem decisão do analista ainda
    elif triagem in TRIAGENS:
        where.append(_T.status == triagem)
    if fluxo:   # abas Entradas (tpNF=0) × Saídas (tpNF=1)
        where.append(n.fluxo == fluxo)
    # data_emissao é 'YYYY-MM-DD' (ISO): comparação lexicográfica = cronológica.
    if data_inicio:
        where.append(n.data_emissao >= data_inicio)
    if data_fim:
        where.append(n.data_emissao <= data_fim)
    if cnpj:
        where.append(n.cnpj_emit == only_digits(cnpj))
    if status in ("DIVERGENTE", "NAO_AUDITAVEL"):
        where.append(a.status == status)
    if codigo_erro:
        where.append(func.coalesce(a.codigo_erro, "").like(f"%{codigo_erro}%"))
    if q and q.strip():
        # Busca livre: fornecedor/produto por nome; com dígitos, também nº da
        # NF, CNPJ, NCM e chave de acesso.
        termo = q.strip()
        like = f"%{termo}%"
        conds = [n.nome_emit.ilike(like), it.descricao.ilike(like)]
        digitos = only_digits(termo)
        if digitos:
            dlike = f"%{digitos}%"
            conds += [
                n.numero.like(dlike), n.cnpj_emit.like(dlike),
                it.ncm.like(dlike), a.chave_acesso.like(dlike),
            ]
        where.append(or_(*conds))
    return where


async def listar_divergencias(
    session: AsyncSession,
    *,
    empresa_id: UUID,
    fluxo: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    cnpj: str | None = None,
    status: str | None = None,
    codigo_erro: str | None = None,
    q: str | None = None,
    triagem: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    a, n, it = _A, _N, _IT
    where = _filtros(
        empresa_id=empresa_id, fluxo=fluxo, data_inicio=data_inicio,
        data_fim=data_fim, cnpj=cnpj, status=status, codigo_erro=codigo_erro, q=q,
        triagem=triagem,
    )

    page = max(1, page)
    page_size = max(1, min(500, page_size))

    total = await session.scalar(
        select(func.count()).select_from(a)
        .join(n, a.nota_id == n.id).outerjoin(it, _J_ITEM)
        .outerjoin(_T, _J_TRIAGEM).where(*where)
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
        ).select_from(a).join(n, a.nota_id == n.id).outerjoin(it, _J_ITEM)
        .outerjoin(_T, _J_TRIAGEM).where(*where)
    )).one()
    resumo = {
        "a_recolher": float(agg[0]), "a_favor": float(agg[1]),
        "antecipacao": float(agg[2]),
        "divergentes": int(agg[3]), "nao_auditaveis": int(agg[4]),
    }

    # Triagem dos DIVERGENTES do filtro: quanto já foi cobrado/justificado/
    # aceito e quanto segue em aberto — o pós-carta em números.
    tri_rows = (await session.execute(
        select(func.coalesce(_T.status, "EM_ABERTO"), func.count())
        .select_from(a).join(n, a.nota_id == n.id).outerjoin(it, _J_ITEM)
        .outerjoin(_T, _J_TRIAGEM)
        .where(*where, divergente)
        .group_by(func.coalesce(_T.status, "EM_ABERTO"))
    )).all()
    resumo["triagem"] = {s: int(c) for s, c in tri_rows}

    # Ranking de emitentes pelo valor COBRÁVEL (divergências sem ERRO_111):
    # quem cobrar primeiro / onde a parametrização mais erra.
    rank_rows = (await session.execute(
        select(
            n.cnpj_emit, n.nome_emit,
            func.count().label("itens"),
            func.coalesce(func.sum(func.abs(d)), 0).label("valor"),
        )
        .select_from(a).join(n, a.nota_id == n.id).outerjoin(it, _J_ITEM)
        .outerjoin(_T, _J_TRIAGEM)
        .where(*where, divergente, ~eh_antecipacao)
        .group_by(n.cnpj_emit, n.nome_emit)
        .order_by(func.coalesce(func.sum(func.abs(d)), 0).desc())
        .limit(20)
    )).all()
    ranking = [
        {"cnpj": r[0], "nome": r[1], "itens": int(r[2]), "valor": float(r[3] or 0)}
        for r in rank_rows
    ]
    res = await session.execute(
        select(a, n, it.descricao, it.codigo, it.ncm, it.cest,
               _T.status, _T.observacao, _T.definido_por, _T.definido_em)
        .join(n, a.nota_id == n.id)
        .outerjoin(it, _J_ITEM)
        .outerjoin(_T, _J_TRIAGEM)
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
        _linha(a_row, n_row, descricao, codigo, ncm, cest,
               ctes_por_chave.get(a_row.chave_acesso, []),
               (t_status, t_obs, t_por, t_em))
        for a_row, n_row, descricao, codigo, ncm, cest, t_status, t_obs, t_por, t_em
        in linhas
    ]
    return {
        "total": total or 0, "page": page, "page_size": page_size, "itens": itens,
        "resumo": resumo, "ranking_fornecedores": ranking,
    }


def _linha(a_row, n_row, descricao, codigo, ncm, cest, ctes: list[str],
           triagem: tuple = (None, None, None, None)) -> dict:
    t_status, t_obs, t_por, t_em = triagem
    return {
        "triagem": (
            {"status": t_status, "observacao": t_obs, "por": t_por,
             "em": t_em.isoformat() if t_em else None}
            if t_status else None
        ),
        "chave_acesso": a_row.chave_acesso,
        "nota_id": str(a_row.nota_id),
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
        "ctes_vinculados": ctes,
    }


async def diagnostico_st(
    session: AsyncSession,
    *,
    empresa_id: UUID,
    data_inicio: str | None = None,
    data_fim: str | None = None,
) -> dict:
    """Diagnóstico executivo do período: conformidade e dinheiro em jogo POR
    COMPETÊNCIA (inclui os itens OK — é o retrato completo da carteira), mais
    o top de fornecedores cobráveis. Alimenta o PDF de diagnóstico (o
    entregável do serviço de auditoria/recuperação retroativa)."""
    a, n = _A, _N
    where = [a.empresa_id == empresa_id]
    if data_inicio:
        where.append(n.data_emissao >= data_inicio)
    if data_fim:
        where.append(n.data_emissao <= data_fim)

    d = a.vicms_st_divergencia
    eh_antecipacao = func.coalesce(a.codigo_erro, "").like("%ERRO_111%")
    divergente = a.status == "DIVERGENTE"
    comp = func.substr(n.data_emissao, 1, 7)               # 'AAAA-MM'
    rows = (await session.execute(
        select(
            comp.label("competencia"),
            func.count(),
            func.coalesce(func.sum(case((a.status == "OK", 1), else_=0)), 0),
            func.coalesce(func.sum(case((divergente, 1), else_=0)), 0),
            func.coalesce(func.sum(case((a.status == "NAO_AUDITAVEL", 1), else_=0)), 0),
            func.coalesce(func.sum(case(
                (and_(divergente, d < 0, ~eh_antecipacao), -d), else_=0)), 0),
            func.coalesce(func.sum(case((and_(divergente, d > 0), d), else_=0)), 0),
            func.coalesce(func.sum(case((eh_antecipacao, -d), else_=0)), 0),
        ).select_from(a).join(n, a.nota_id == n.id).where(*where)
        .group_by(comp).order_by(comp)
    )).all()
    competencias = [
        {
            "competencia": r[0], "itens": int(r[1]), "ok": int(r[2]),
            "divergentes": int(r[3]), "nao_auditaveis": int(r[4]),
            "a_recolher": float(r[5]), "a_favor": float(r[6]),
            "antecipacao": float(r[7]),
        }
        for r in rows
    ]
    totais = {
        chave: round(sum(c[chave] for c in competencias), 2)
        for chave in ("itens", "ok", "divergentes", "nao_auditaveis",
                      "a_recolher", "a_favor", "antecipacao")
    }
    totais["pct_conformidade"] = (
        round(totais["ok"] / totais["itens"] * 100, 1) if totais["itens"] else 100.0
    )

    top_rows = (await session.execute(
        select(
            n.cnpj_emit, n.nome_emit,
            func.count().label("itens"),
            func.coalesce(func.sum(func.abs(d)), 0).label("valor"),
        )
        .select_from(a).join(n, a.nota_id == n.id)
        .where(*where, divergente, ~eh_antecipacao)
        .group_by(n.cnpj_emit, n.nome_emit)
        .order_by(func.coalesce(func.sum(func.abs(d)), 0).desc())
        .limit(10)
    )).all()
    top = [
        {"cnpj": r[0], "nome": r[1], "itens": int(r[2]), "valor": float(r[3] or 0)}
        for r in top_rows
    ]
    return {"competencias": competencias, "totais": totais, "top_fornecedores": top}


async def exportar_divergencias(
    session: AsyncSession,
    *,
    empresa_id: UUID,
    fluxo: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    cnpj: str | None = None,
    status: str | None = None,
    codigo_erro: str | None = None,
    q: str | None = None,
    triagem: str | None = None,
    limite: int = 20000,
) -> list[dict]:
    """Todas as linhas do filtro (sem paginação) para a planilha de trabalho —
    ordenadas por fornecedor/nota/item, do jeito que o analista confere."""
    a, n, it = _A, _N, _IT
    where = _filtros(
        empresa_id=empresa_id, fluxo=fluxo, data_inicio=data_inicio,
        data_fim=data_fim, cnpj=cnpj, status=status, codigo_erro=codigo_erro, q=q,
        triagem=triagem,
    )
    res = await session.execute(
        select(a, n, it.descricao, it.codigo, it.ncm, it.cest,
               _T.status, _T.observacao, _T.definido_por, _T.definido_em)
        .join(n, a.nota_id == n.id)
        .outerjoin(it, _J_ITEM)
        .outerjoin(_T, _J_TRIAGEM)
        .where(*where)
        .order_by(n.nome_emit, n.numero, a.numero_item)
        .limit(limite)
    )
    return [
        _linha(a_row, n_row, descricao, codigo, ncm, cest, [],
               (t_status, t_obs, t_por, t_em))
        for a_row, n_row, descricao, codigo, ncm, cest, t_status, t_obs, t_por, t_em
        in res.all()
    ]
