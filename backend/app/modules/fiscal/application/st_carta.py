"""Carta timbrada de cobrança/correção de ICMS-ST (PDF).

Enviada ao FORNECEDOR (entradas: reteve errado — a menor ou a maior) ou usada
como apontamento da EMISSÃO PRÓPRIA (saídas). Lista item a item o confronto
"destacado no XML × calculado pelo motor" com a diferença e a ação, apoiada na
memória de cálculo persistida (MVA, alíquotas e matrizes com vigência).

Antecipações do destinatário (ERRO_111) NÃO entram: são obrigação do próprio
cliente (guia local), não há o que cobrar do fornecedor.
"""
from __future__ import annotations

from datetime import date

from fpdf.fonts import FontFace

from app.modules.fiscal.application.carta_base import (
    CINZA,
    NAVY,
    _brl,
    _cnpj,
    _t,
    nova_carta,
)

_ACAO_CURTA = {
    "ERRO_101_MVA_AJUSTADA_INDEVIDA": "MVA ajustada indevidamente",
    "ERRO_102_BC_ST_DIVERGENTE": "Base do ST divergente",
    "ERRO_103_DEDUCAO_ST_INCORRETA": "Dedução do próprio incorreta",
    "ERRO_104_VALOR_ST_DIVERGENTE": "Valor do ST divergente",
    "ERRO_105_FCP_ST_OMITIDO": "FCP-ST divergente",
    "ERRO_107_ICMS_PROPRIO_ZERADO_COM_ST": "ICMS próprio zerado",
    "ERRO_109_MODBCST_INCOMPATIVEL": "Base sem MVA (modBCST)",
    "ERRO_110_ST_INDEVIDO_REVENDA": "ST indevido (já retido)",
}


def _situacao(item: dict) -> str:
    for cod, txt in _ACAO_CURTA.items():
        if cod in (item.get("codigo_erro") or ""):
            return txt
    return "Divergente"


def gerar_carta_st(
    *,
    destinatario_nome: str,
    destinatario_cnpj: str,
    fluxo: str,
    competencia: str,
    itens: list[dict],
    cliente_nome: str | None = None,
) -> bytes:
    """Monta o PDF com os itens DIVERGENTES (sem ERRO_111) do emitente."""
    pdf = nova_carta()

    # Título + data
    pdf.set_font("helvetica", "B", 13)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, _t("Solicitação de correção — Retenção de ICMS-ST"),
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

    if fluxo == "saida":
        intro = (
            "Na conferência das notas emitidas por essa empresa"
            + (f" ({cliente_nome})" if cliente_nome else "")
            + f" na competência {competencia}, o recálculo do ICMS-ST apontou as "
            "divergências abaixo entre o valor destacado e o valor devido."
        )
        pedido = (
            "Solicitamos a revisão da parametrização do sistema emissor (MVA, base "
            "e alíquotas da UF de destino) e, quando cabível, a emissão de NF-e "
            "complementar ou o pedido de ressarcimento, conforme o quadro acima."
        )
    else:
        intro = (
            "Na conferência das notas emitidas por V.Sa."
            + (f" contra nosso cliente {cliente_nome}" if cliente_nome else " contra nosso cliente")
            + f" na competência {competencia}, o recálculo do ICMS-ST apontou as "
            "divergências abaixo entre o valor retido e o valor devido."
        )
        pedido = (
            "Solicitamos a correção das próximas emissões e, conforme o caso, NF-e "
            "complementar (retenção a menor) ou providências para ressarcimento "
            "(retenção a maior). Caso a operação esteja amparada por dispensa de "
            "retenção (ausência de convênio/protocolo aplicável ao produto, regime "
            "especial ou condição específica de inscrição), pedimos a gentileza de "
            "nos indicar a base normativa para a baixa do apontamento. A memória de "
            "cálculo de cada item — MVA aplicada, alíquotas e base — está à "
            "disposição para conferência conjunta."
        )

    metodo = (
        "O recálculo segue a legislação da UF de destino vigente na data de emissão "
        "de cada nota: enquadramento por NCM/CEST, MVA original/ajustada, redução de "
        "base, alíquotas interna e interestadual, dedução do ICMS próprio e FCP-ST. "
        "Diferença NEGATIVA = ST a menor (complemento); POSITIVA = ST a maior "
        "(ressarcimento)."
    )

    # Bases legais das regras aplicadas (memória de cálculo): o laudo cita a
    # norma, não só o número interno da matriz — padrão "pronto para auditoria".
    bases = sorted({
        b for i in itens for b in (
            (i.get("memoria") or {}).get("mva_base_legal"),
            (i.get("memoria") or {}).get("aliquota_base_legal"),
        ) if b
    })
    paragrafos = [intro, metodo]
    if bases:
        paragrafos.append("Bases legais aplicadas no recálculo: " + "; ".join(bases) + ".")

    pdf.set_font("helvetica", "", 10)
    for paragrafo in paragrafos:
        pdf.multi_cell(0, 5.4, _t(paragrafo))
        pdf.ln(2)

    # Quadro item a item
    total_xml = sum(float(i.get("vicms_st_xml") or 0) for i in itens)
    total_calc = sum(float(i.get("vicms_st_calculado") or 0) for i in itens)
    total_dif = sum(float(i.get("diferenca") or 0) for i in itens)
    n_notas = len({i.get("chave_acesso") or i.get("numero_nota") for i in itens})

    pdf.ln(1)
    pdf.set_font("helvetica", "B", 10.5)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, _t(f"Itens apontados ({len(itens)} item(ns) em {n_notas} nota(s))"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(30, 30, 30)
    pdf.set_font("helvetica", "", 7.4)

    with pdf.table(
        col_widths=(16, 17, 45, 26, 26, 26, 26),
        text_align=("CENTER", "CENTER", "LEFT", "RIGHT", "RIGHT", "RIGHT", "CENTER"),
        borders_layout="HORIZONTAL_LINES",
        line_height=3.6,
        headings_style=FontFace(emphasis="BOLD", color=NAVY),
        padding=1.2,
    ) as table:
        cab = table.row()
        for h in ("NF / Item", "Emissão", "Produto", "ST no XML", "ST devido",
                  "Diferença", "Situação"):
            cab.cell(_t(h))
        for i in itens:
            data_br = "/".join(reversed((i.get("data_emissao") or "").split("-")))
            linha = table.row()
            linha.cell(_t(f"{i.get('numero_nota') or '—'} / {i.get('numero_item')}"))
            linha.cell(_t(data_br))
            linha.cell(_t((i.get("descricao") or "—")[:56]
                          + (f"\nNCM {i.get('ncm')}" if i.get("ncm") else "")))
            linha.cell(_t(_brl(i.get("vicms_st_xml"))))
            linha.cell(_t(_brl(i.get("vicms_st_calculado"))))
            linha.cell(_t(_brl(i.get("diferenca"))))
            linha.cell(_t(_situacao(i)))
        rodape = table.row()
        pdf.set_font("helvetica", "B", 7.4)
        rodape.cell(_t("TOTAL"), colspan=3)
        rodape.cell(_t(_brl(total_xml)))
        rodape.cell(_t(_brl(total_calc)))
        rodape.cell(_t(_brl(total_dif)))
        rodape.cell("")
        pdf.set_font("helvetica", "", 7.4)

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
