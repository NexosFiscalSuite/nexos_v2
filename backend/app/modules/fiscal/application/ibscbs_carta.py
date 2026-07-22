"""Carta timbrada de solicitação de correção do destaque IBS/CBS (PDF).

Enviada ao FORNECEDOR (aba Entradas) ou ao PRÓPRIO CLIENTE emissor (aba
Saídas), apontando item a item o que veio no XML e o que a Classificação
Tributária manda, com a base legal do ano-teste (EC 132/2023, ADCT art. 125;
NT 2025.002; LC 214/2025).

Identidade visual extraída do timbrado oficial ("cabecalhosol 2.0"):
azul-marinho #24477B, lilás #A4A7C6 e a logomarca Sol.
"""
from __future__ import annotations

from datetime import date

from fpdf.fonts import FontFace

from app.modules.fiscal.application.carta_base import (
    _LOGO,  # noqa: F401 — reexport (testes validam o asset por aqui)
    CINZA,
    NAVY,
    _brl,
    _cnpj,
    _pct,
    _t,
    nova_carta,
)

_STATUS = {
    "SEM_DESTAQUE": "Sem destaque",
    "ALIQUOTA_DIVERGENTE": "Alíquota divergente",
    "VALOR_DIVERGENTE": "Valor divergente",
}


def _veio_linha(nominal, efet, valor) -> str:
    """Linha do "veio": com gRed no XML mostra nominal→efetiva (é a efetiva
    que se compara com o devido); sem gRed, a alíquota aplicada direta."""
    if efet is None:
        return f"{_pct(nominal)} · {_brl(valor)}"
    return f"{_pct(nominal)}→{_pct(efet)} · {_brl(valor)}"


def _agrupar_por_produto(itens: list[dict]) -> list[dict]:
    """Produto repetido em várias notas vira UMA linha no resumo: corrigida a
    parametrização do produto no emissor, todas as emissões seguintes saem
    certas. Agrupa pelo código do produto (cProd) quando houver — é como o
    emitente localiza o item no sistema dele — senão pela descrição."""
    grupos: dict[tuple, dict] = {}
    for i in itens:
        produto = (str(i.get("codigo") or "").strip()
                   or (i.get("descricao") or "").strip().upper())
        chave = (produto, i.get("cst"), i.get("c_class_trib"), i.get("status"))
        g = grupos.get(chave)
        if g is None:
            g = grupos[chave] = dict(i, notas=[])
        nf = str(i.get("numero_nota") or "—")
        if nf not in g["notas"]:
            g["notas"].append(nf)
    return list(grupos.values())


def gerar_carta(
    *,
    destinatario_nome: str,
    destinatario_cnpj: str,
    fluxo: str,
    competencia: str,
    itens: list[dict],
    cliente_nome: str | None = None,
) -> bytes:
    """Monta o PDF. `itens` = apontamentos do verificador (com veio/devido)."""
    pdf = nova_carta()

    # Título + data
    pdf.set_font("helvetica", "B", 13)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, _t("Solicitação de correção — Destaque de IBS/CBS (ano-teste 2026)"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 9)
    pdf.set_text_color(*CINZA)
    pdf.cell(0, 6, _t(f"Emitida em {date.today().strftime('%d/%m/%Y')} · Competência: {competencia}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Destinatário
    pdf.set_text_color(30, 30, 30)
    pdf.set_font("helvetica", "B", 10.5)
    pdf.cell(0, 6, _t(f"À {destinatario_nome}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 6, _t(f"CNPJ: {_cnpj(destinatario_cnpj)}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Corpo
    if fluxo == "saida":
        intro = (
            "Na análise dos documentos fiscais emitidos por essa empresa"
            + (f" ({cliente_nome})" if cliente_nome else "")
            + f" na competência {competencia}, identificamos inconsistências no destaque "
            "do IBS e da CBS exigido no período de testes da Reforma Tributária."
        )
        pedido = (
            "Solicitamos a adequação da parametrização do sistema emissor para as "
            "próximas emissões, conforme o resumo acima, evitando notificações e "
            "rejeições futuras pelo Fisco."
        )
    else:
        intro = (
            "Na análise dos documentos fiscais emitidos por V.Sa."
            + (f" contra nosso cliente {cliente_nome}" if cliente_nome else " contra nosso cliente")
            + f" na competência {competencia}, identificamos inconsistências no destaque "
            "do IBS e da CBS exigido no período de testes da Reforma Tributária."
        )
        pedido = (
            "Solicitamos a gentileza de ajustar a parametrização do sistema emissor "
            "para as próximas emissões, conforme o resumo acima. Permanecemos à "
            "disposição para alinhamento técnico."
        )

    base_legal = (
        "Nos termos do art. 125 do ADCT (EC nº 132/2023), da LC nº 214/2025 e da "
        "NT 2025.002, os documentos fiscais de 2026 devem destacar o IBS (0,10%) e a "
        "CBS (0,90%) — observados os tratamentos da Tabela de Classificação Tributária "
        "(isenções, reduções e regimes específicos), sem recolhimento nesta fase."
    )

    pdf.set_font("helvetica", "", 10)
    for paragrafo in (intro, base_legal):
        pdf.multi_cell(0, 5.4, _t(paragrafo))
        pdf.ln(2)

    grupos = _agrupar_por_produto(itens)
    n_notas = len({i.get("chave_acesso") or i.get("numero_nota") for i in itens})

    # Quadro 1 — todos os apontamentos, nota a nota: o destinatário enxerga a
    # extensão do problema (quantas notas e quais itens).
    pdf.ln(1)
    pdf.set_font("helvetica", "B", 10.5)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, _t(f"Itens apontados ({len(itens)} item(ns) em {n_notas} nota(s))"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(30, 30, 30)
    pdf.set_font("helvetica", "", 7.4)

    with pdf.table(
        col_widths=(15, 16, 44, 21, 34, 30, 22),
        text_align=("CENTER", "CENTER", "LEFT", "CENTER", "RIGHT", "RIGHT", "CENTER"),
        borders_layout="HORIZONTAL_LINES",
        line_height=3.6,
        headings_style=FontFace(emphasis="BOLD", color=NAVY),
        padding=1.2,
    ) as table:
        cab = table.row()
        for h in ("NF / Item", "Emissão", "Produto", "Classif.", "Veio (IBS / CBS)",
                  "Devido (IBS / CBS)", "Situação"):
            cab.cell(_t(h))
        for i in itens:
            data_br = "/".join(reversed((i.get("data_emissao") or "").split("-")))
            veio = (
                _veio_linha(i.get("p_ibs"), i.get("p_aliq_efet_ibs"), i.get("v_ibs"))
                + "\n"
                + _veio_linha(i.get("p_cbs"), i.get("p_aliq_efet_cbs"), i.get("v_cbs"))
            )
            if i.get("p_ibs_esperado") is None:
                devido = "sem régua\npercentual"
            else:
                devido = (f"{_pct(i.get('p_ibs_esperado'))} · {_brl(i.get('v_ibs_esperado'))}\n"
                          f"{_pct(i.get('p_cbs_esperado'))} · {_brl(i.get('v_cbs_esperado'))}")
            linha = table.row()
            linha.cell(_t(f"{i.get('numero_nota') or '—'} / {i.get('numero_item')}"))
            linha.cell(_t(data_br))
            linha.cell(_t((i.get("descricao") or "—")[:60]))
            linha.cell(_t(f"{i.get('cst') or '—'}\n{i.get('c_class_trib') or ''}"))
            linha.cell(_t(veio))
            linha.cell(_t(devido))
            linha.cell(_t(_STATUS.get(i.get("status"), i.get("status") or "")))

    if any(i.get("p_aliq_efet_ibs") is not None or i.get("p_aliq_efet_cbs") is not None
           for i in itens):
        pdf.ln(2)
        pdf.set_font("helvetica", "I", 8)
        pdf.set_text_color(*CINZA)
        pdf.multi_cell(0, 4.2, _t(
            'Leitura "x% → y%": x é a alíquota NOMINAL de teste (obrigatória na NF-e) e '
            "y é a alíquota EFETIVA declarada no grupo de redução (gRed) do XML - é a "
            "efetiva que se compara com a coluna Devido."
        ))
        pdf.set_text_color(30, 30, 30)

    # Quadro 2 — resumo por produto: o que efetivamente precisa ser corrigido.
    # Corrigida a parametrização do produto, todas as notas seguintes saem certas.
    pdf.ln(4)
    pdf.set_font("helvetica", "B", 10.5)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, _t(f"Resumo para correção ({len(grupos)} produto(s))"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(30, 30, 30)
    pdf.set_font("helvetica", "", 7.4)

    with pdf.table(
        col_widths=(20, 48, 20, 32, 24, 38),
        text_align=("CENTER", "LEFT", "CENTER", "CENTER", "CENTER", "CENTER"),
        borders_layout="HORIZONTAL_LINES",
        line_height=3.6,
        headings_style=FontFace(emphasis="BOLD", color=NAVY),
        padding=1.2,
    ) as table:
        cab = table.row()
        for h in ("Cód.", "Produto", "Classif.", "Devido (IBS / CBS)", "Situação",
                  "Nota(s)"):
            cab.cell(_t(h))
        for g in grupos:
            if g.get("p_ibs_esperado") is None:
                devido = "sem régua percentual"
            else:
                devido = (f"IBS {_pct(g.get('p_ibs_esperado'))} · "
                          f"CBS {_pct(g.get('p_cbs_esperado'))}")
            nfs = g["notas"]
            notas = ", ".join(nfs[:3]) + (f" +{len(nfs) - 3}" if len(nfs) > 3 else "")
            linha = table.row()
            linha.cell(_t(g.get("codigo") or "—"))
            linha.cell(_t((g.get("descricao") or "—")[:60]))
            linha.cell(_t(f"{g.get('cst') or '—'}\n{g.get('c_class_trib') or ''}"))
            linha.cell(_t(devido))
            linha.cell(_t(_STATUS.get(g.get("status"), g.get("status") or "")))
            linha.cell(_t(notas))

    pdf.ln(2)
    pdf.set_font("helvetica", "I", 8)
    pdf.set_text_color(*CINZA)
    pdf.multi_cell(0, 4.2, _t(
        "No resumo, cada produto aparece uma única vez: corrigida a parametrização do "
        "produto no sistema emissor, todas as próximas emissões saem corretas."
    ))
    pdf.set_text_color(30, 30, 30)

    pdf.ln(5)
    pdf.set_font("helvetica", "", 10)
    pdf.multi_cell(0, 5.4, _t(pedido))
    pdf.ln(8)
    pdf.set_font("helvetica", "B", 10.5)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, _t("Sol Contabilidade e Consultoria"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 9)
    pdf.set_text_color(*CINZA)
    pdf.cell(0, 5, _t("Departamento Fiscal"), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
