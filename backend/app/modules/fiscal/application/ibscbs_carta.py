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
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

NAVY = (36, 71, 123)      # #24477B
LILAS = (164, 167, 198)   # #A4A7C6
CINZA = (90, 96, 105)
_LOGO = Path(__file__).resolve().parents[3] / "shared" / "assets" / "sol-logo.png"

_STATUS = {
    "SEM_DESTAQUE": "Sem destaque",
    "ALIQUOTA_DIVERGENTE": "Alíquota divergente",
    "VALOR_DIVERGENTE": "Valor divergente",
}


_TROCAS = str.maketrans({"—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"'})


def _t(s) -> str:
    """Fontes core do PDF são latin-1 — cobre o português; travessões e aspas
    tipográficas são normalizados antes (senão virariam '?')."""
    return (
        str(s if s is not None else "")
        .translate(_TROCAS)
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


def _pct(v) -> str:
    return f"{float(v or 0):.2f}%".replace(".", ",")


def _brl(v) -> str:
    s = f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _cnpj(c) -> str:
    c = str(c or "")
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    return c or "—"


def _agrupar_por_produto(itens: list[dict]) -> list[dict]:
    """Produto repetido em várias notas vira UMA linha na carta: corrigida a
    parametrização do produto no emissor, todas as emissões seguintes saem
    certas. Valores/percentuais exibidos são os da primeira ocorrência."""
    grupos: dict[tuple, dict] = {}
    for i in itens:
        chave = ((i.get("descricao") or "").strip().upper(), i.get("cst"),
                 i.get("c_class_trib"), i.get("status"))
        g = grupos.get(chave)
        if g is None:
            g = grupos[chave] = dict(i, notas=[])
        nf = str(i.get("numero_nota") or "—")
        if nf not in g["notas"]:
            g["notas"].append(nf)
    return list(grupos.values())


class _CartaPDF(FPDF):
    def header(self):
        # Logo quase quadrada (472×378): 30mm de largura ≈ 24mm de altura.
        if _LOGO.exists():
            self.image(str(_LOGO), x=14, y=8, w=30)
        # Barras da marca (eco das faixas diagonais do timbrado)
        self.set_fill_color(*NAVY)
        self.rect(176, 8, 5.5, 24, "F")
        self.set_fill_color(*LILAS)
        self.rect(184, 8, 3.5, 24, "F")
        self.set_draw_color(*NAVY)
        self.set_line_width(0.7)
        self.line(14, 35, 196, 35)
        self.set_draw_color(*LILAS)
        self.set_line_width(0.4)
        self.line(14, 36.6, 196, 36.6)
        self.set_y(43)

    def footer(self):
        self.set_y(-17)
        self.set_draw_color(*LILAS)
        self.set_line_width(0.4)
        self.line(14, self.get_y(), 196, self.get_y())
        self.set_font("helvetica", "", 8)
        self.set_text_color(*CINZA)
        self.cell(0, 9, _t("Sol Contabilidade e Consultoria · CNPJ 04.640.241/0001-56"), align="C")
        self.set_x(-30)
        self.cell(0, 9, _t(f"pág. {self.page_no()}"), align="R")


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
    pdf = _CartaPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.set_margins(14, 10, 14)
    pdf.add_page()

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
        col_widths=(15, 16, 48, 21, 30, 30, 22),
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
            veio = (f"{_pct(i.get('p_ibs'))} · {_brl(i.get('v_ibs'))}\n"
                    f"{_pct(i.get('p_cbs'))} · {_brl(i.get('v_cbs'))}")
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
        col_widths=(58, 22, 34, 26, 42),
        text_align=("LEFT", "CENTER", "CENTER", "CENTER", "CENTER"),
        borders_layout="HORIZONTAL_LINES",
        line_height=3.6,
        headings_style=FontFace(emphasis="BOLD", color=NAVY),
        padding=1.2,
    ) as table:
        cab = table.row()
        for h in ("Produto", "Classif.", "Devido (IBS / CBS)", "Situação", "Nota(s)"):
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
