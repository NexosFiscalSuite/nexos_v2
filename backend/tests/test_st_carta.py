"""Carta timbrada de cobrança de ICMS-ST: PDF válido, textos e totais.

Gerador puro (sem DB), sobre os itens do relatório de divergências. As
antecipações (ERRO_111) são filtradas ANTES, no endpoint — a carta cobra o
fornecedor apenas do que é dele.
"""
import re
import zlib

from app.modules.fiscal.application.st_carta import gerar_carta_st


def _texto(pdf: bytes) -> str:
    partes = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.DOTALL):
        try:
            partes.append(zlib.decompress(m.group(1)).decode("latin-1"))
        except zlib.error:
            pass
    return "".join(partes)


def _item(n: int = 1, **extra) -> dict:
    base = {
        "chave_acesso": "1" * 44, "numero_nota": "130", "numero_item": n,
        "data_emissao": "2026-06-25", "descricao": f"PNEU AGRICOLA {n}",
        "ncm": "40117000",
        "vicms_st_xml": 249.48, "vicms_st_calculado": 331.72, "diferenca": -82.24,
        "status": "DIVERGENTE", "codigo_erro": "ERRO_104_VALOR_ST_DIVERGENTE",
    }
    base.update(extra)
    return base


def _gerar(fluxo="entrada", itens=None, **kw) -> bytes:
    return gerar_carta_st(
        destinatario_nome="PNEUAGRO E MAQUINAS BRASIL LTDA",
        destinatario_cnpj="31312326000188",
        fluxo=fluxo,
        competencia="06/2026",
        itens=itens or [_item()],
        **kw,
    )


def test_pdf_valido_com_totais():
    pdf = _gerar(itens=[_item(1), _item(2, diferenca=-10.00, vicms_st_xml=100.00,
                                        vicms_st_calculado=110.00)],
                 cliente_nome="IRRIGACER SISTEMAS LTDA")
    assert pdf[:5] == b"%PDF-"
    t = _texto(pdf)
    assert "ICMS-ST" in t and "IRRIGACER" in t
    assert "R$ 349,48" in t          # total XML (249,48 + 100,00)
    assert "R$ 441,72" in t          # total calculado (331,72 + 110,00)
    assert "-R$ 92,24" in t or "R$ -92,24" in t.replace("R$ ", "R$ ")  # total diferença


def test_situacao_traduzida_e_fluxos():
    t = _texto(_gerar())
    assert "Valor do ST" in t         # rótulo da situação (quebra de linha na célula)
    assert "V.Sa." in t                                   # entrada fala com o fornecedor

    t_saida = _texto(_gerar("saida"))
    assert "essa empresa" in t_saida and "V.Sa." not in t_saida


def test_ncm_no_quadro():
    t = _texto(_gerar())
    assert "NCM 40117000" in t
