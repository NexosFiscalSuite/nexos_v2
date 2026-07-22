"""Diagnóstico executivo de ICMS-ST em PDF timbrado (o entregável comercial).

Retrato do período auditado por competência: conformidade, ST retido a menor
(risco/cobrança), pago a maior (oportunidade de ressarcimento) e antecipações
devidas — mais o top de fornecedores. É o relatório que justifica o serviço
de auditoria/recuperação retroativa perante o cliente.
"""
from __future__ import annotations

from datetime import date

from fpdf.fonts import FontFace

from app.modules.fiscal.application.carta_base import (
    CINZA,
    LILAS,
    NAVY,
    _brl,
    _cnpj,
    _t,
    nova_carta,
)


def _comp_br(c: str) -> str:
    """'2026-06' → '06/2026'."""
    partes = (c or "").split("-")
    return f"{partes[1]}/{partes[0]}" if len(partes) == 2 else (c or "—")


def gerar_diagnostico_pdf(
    *,
    empresa_nome: str,
    empresa_cnpj: str | None,
    dados: dict,
) -> bytes:
    pdf = nova_carta()
    competencias = dados["competencias"]
    totais = dados["totais"]
    periodo = (
        f"{_comp_br(competencias[0]['competencia'])} a "
        f"{_comp_br(competencias[-1]['competencia'])}"
        if competencias else "—"
    )

    pdf.set_font("helvetica", "B", 13)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, _t("Diagnóstico de ICMS-ST — Auditoria da carteira de notas"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 9)
    pdf.set_text_color(*CINZA)
    pdf.cell(0, 6, _t(f"{empresa_nome}"
                      + (f" · CNPJ {_cnpj(empresa_cnpj)}" if empresa_cnpj else "")
                      + f" · Período: {periodo} · Emitido em {date.today().strftime('%d/%m/%Y')}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # ── Sumário executivo: 3 números que importam ──────────────────────────
    def cartao(x, largura, titulo, valor, cor):
        pdf.set_xy(x, pdf.get_y())
        pdf.set_draw_color(*LILAS)
        pdf.set_line_width(0.3)
        pdf.rect(x, pdf.get_y(), largura, 20)
        pdf.set_xy(x + 3, pdf.get_y() + 3)
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(*CINZA)
        pdf.cell(largura - 6, 4, _t(titulo))
        pdf.set_xy(x + 3, pdf.get_y() + 5.5)
        pdf.set_font("helvetica", "B", 12.5)
        pdf.set_text_color(*cor)
        pdf.cell(largura - 6, 7, _t(valor))

    y0 = pdf.get_y()
    cartao(14, 58, "ST retido a MENOR — complemento", _brl(totais["a_recolher"]), (179, 55, 46))
    pdf.set_y(y0)
    cartao(76, 58, "Pago a MAIOR — ressarcimento", _brl(totais["a_favor"]), (27, 122, 75))
    pdf.set_y(y0)
    cartao(138, 58, "Antecipações — guia própria", _brl(totais["antecipacao"]), NAVY)
    pdf.set_y(y0 + 25)

    pdf.set_font("helvetica", "", 9.5)
    pdf.set_text_color(30, 30, 30)
    pdf.multi_cell(0, 5.2, _t(
        f"Foram auditados {totais['itens']} item(ns) no período — conformidade de "
        f"{totais['pct_conformidade']}% ({totais['ok']} corretos, "
        f"{totais['divergentes']} divergentes e {totais['nao_auditaveis']} pendentes "
        "de matriz/insumo). Valores apurados pela memória de cálculo do motor "
        "(MVA, alíquotas e enquadramentos com vigência na data de cada emissão)."
    ))
    pdf.ln(3)

    # ── Por competência ─────────────────────────────────────────────────────
    pdf.set_font("helvetica", "B", 10.5)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, _t("Evolução por competência"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(30, 30, 30)
    pdf.set_font("helvetica", "", 7.6)
    with pdf.table(
        col_widths=(22, 16, 14, 18, 18, 32, 32, 30),
        text_align=("CENTER", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT"),
        borders_layout="HORIZONTAL_LINES",
        line_height=4.4,
        headings_style=FontFace(emphasis="BOLD", color=NAVY),
        padding=1.2,
    ) as table:
        cab = table.row()
        for h in ("Competência", "Itens", "OK", "Diverg.", "Pend.",
                  "A recolher", "A favor", "Antecipação"):
            cab.cell(_t(h))
        for c in competencias:
            linha = table.row()
            linha.cell(_t(_comp_br(c["competencia"])))
            linha.cell(str(c["itens"]))
            linha.cell(str(c["ok"]))
            linha.cell(str(c["divergentes"]))
            linha.cell(str(c["nao_auditaveis"]))
            linha.cell(_t(_brl(c["a_recolher"])))
            linha.cell(_t(_brl(c["a_favor"])))
            linha.cell(_t(_brl(c["antecipacao"])))
        rodape = table.row()
        pdf.set_font("helvetica", "B", 7.6)
        rodape.cell(_t("TOTAL"))
        rodape.cell(str(totais["itens"]))
        rodape.cell(str(totais["ok"]))
        rodape.cell(str(totais["divergentes"]))
        rodape.cell(str(totais["nao_auditaveis"]))
        rodape.cell(_t(_brl(totais["a_recolher"])))
        rodape.cell(_t(_brl(totais["a_favor"])))
        rodape.cell(_t(_brl(totais["antecipacao"])))
        pdf.set_font("helvetica", "", 7.6)

    # ── Top fornecedores ────────────────────────────────────────────────────
    top = dados.get("top_fornecedores") or []
    if top:
        pdf.ln(5)
        pdf.set_font("helvetica", "B", 10.5)
        pdf.set_text_color(*NAVY)
        pdf.cell(0, 7, _t("Fornecedores com maior divergência cobrável"),
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(30, 30, 30)
        pdf.set_font("helvetica", "", 7.6)
        with pdf.table(
            col_widths=(86, 34, 20, 42),
            text_align=("LEFT", "CENTER", "RIGHT", "RIGHT"),
            borders_layout="HORIZONTAL_LINES",
            line_height=4.4,
            headings_style=FontFace(emphasis="BOLD", color=NAVY),
            padding=1.2,
        ) as table:
            cab = table.row()
            for h in ("Fornecedor", "CNPJ", "Itens", "Divergência acumulada"):
                cab.cell(_t(h))
            for f in top:
                linha = table.row()
                linha.cell(_t(f.get("nome") or "—"))
                linha.cell(_t(_cnpj(f.get("cnpj"))))
                linha.cell(str(f.get("itens")))
                linha.cell(_t(_brl(f.get("valor"))))

    pdf.ln(6)
    pdf.set_font("helvetica", "I", 8)
    pdf.set_text_color(*CINZA)
    pdf.multi_cell(0, 4.2, _t(
        "Metodologia: recálculo item a item do ICMS-ST (Nexos Fiscal Suite) com "
        "memória de cálculo aberta por item — enquadramento NCM/CEST, MVA "
        "original/ajustada, alíquotas e protocolos vigentes na data de cada "
        "emissão. Antecipações (sem protocolo no par de UFs) são obrigação do "
        "destinatário e não compõem a cobrança de fornecedores."
    ))
    return bytes(pdf.output())
