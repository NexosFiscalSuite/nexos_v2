"""Carta timbrada de correção IBS/CBS: o PDF nasce válido, com timbre e quadro.

Testa o gerador puro (sem DB): PDF bem-formado, textos de entrada × saída,
produto repetido em várias notas vira UMA linha, paginação com muitos itens
e tolerância a caracteres fora do latin-1.
"""
import re
import zlib

from app.modules.fiscal.application.ibscbs_carta import (
    _LOGO,
    _agrupar_por_produto,
    gerar_carta,
)


def _texto(pdf: bytes) -> str:
    """Concatena os streams descomprimidos (fpdf2 usa FlateDecode)."""
    partes = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.DOTALL):
        try:
            partes.append(zlib.decompress(m.group(1)).decode("latin-1"))
        except zlib.error:
            pass
    return "".join(partes)


def _item(n: int = 1, **extra) -> dict:
    base = {
        "numero_nota": "1234", "numero_item": n, "data_emissao": "2026-06-15",
        "codigo": f"P{n:03d}",
        "descricao": f"CAFÉ TORRADO E MOÍDO 500G — item {n}",
        "cst": "000", "c_class_trib": "000001", "status": "SEM_DESTAQUE",
        "p_ibs": 0, "v_ibs": 0, "p_cbs": 0, "v_cbs": 0,
        "p_ibs_esperado": 0.10, "v_ibs_esperado": 0.10,
        "p_cbs_esperado": 0.90, "v_cbs_esperado": 0.90,
        "valor_produto": 100.0,
    }
    base.update(extra)
    return base


def _gerar(fluxo="entrada", itens=None, **kw) -> bytes:
    return gerar_carta(
        destinatario_nome="FORNECEDOR AGRO LTDA",
        destinatario_cnpj="11111111000111",
        fluxo=fluxo,
        competencia="06/2026",
        itens=itens or [_item()],
        **kw,
    )


def test_logo_do_timbrado_esta_no_pacote():
    """O asset extraído do cabecalhosol 2.0.docx precisa viajar com o app."""
    assert _LOGO.exists() and _LOGO.stat().st_size > 10_000


def test_pdf_valido_com_conteudo():
    pdf = _gerar(cliente_nome="CLIENTE MG LTDA")
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 3_000


def test_textos_entrada_e_saida():
    """Entrada fala com o fornecedor; saída fala com o próprio cliente emissor."""
    t_entrada = _texto(_gerar("entrada", cliente_nome="CLIENTE MG"))
    assert "V.Sa." in t_entrada and "CLIENTE MG" in t_entrada
    assert "ADCT" in t_entrada and "0,10%" in t_entrada

    t_saida = _texto(_gerar("saida"))
    assert "essa empresa" in t_saida and "V.Sa." not in t_saida


def test_detalhe_completo_mais_resumo_por_produto():
    """A carta traz o quadro completo nota a nota (dimensão do problema) E o
    resumo com cada produto uma única vez (o que corrigir no emissor)."""
    # Mesmo cProd em 3 notas (nItem pode variar) → agrupa pelo código.
    mesmo = dict(codigo="CAF-500", descricao="CAFE TORRADO 500G", chave_acesso=None)
    itens = [
        _item(1, numero_nota="111", **mesmo),
        _item(2, numero_nota="222", **mesmo),
        _item(1, numero_nota="333", **mesmo),
        _item(3, numero_nota="111", chave_acesso=None, descricao="OUTRO PRODUTO"),
    ]
    grupos = _agrupar_por_produto(itens)
    assert len(grupos) == 2
    assert next(g for g in grupos if g["descricao"] == "CAFE TORRADO 500G")["notas"] == \
        ["111", "222", "333"]

    t = _texto(_gerar(itens=itens))
    # parênteses são escapados nos literais do PDF — casamos sem eles
    assert "4 item" in t and "em 3 nota" in t          # quadro completo
    assert "Resumo para correção" in t and "2 produto" in t
    assert "111, 222, 333" in t                        # coluna Nota(s) do resumo
    assert t.count("CAFE TORRADO 500G") == 4           # 3 no detalhe + 1 no resumo
    assert t.count("CAF-500") == 1                     # cód do produto, só no resumo
    assert "uma única vez" in t                        # rodapé explicando o resumo


def test_mesmo_produto_com_situacao_diferente_nao_agrupa():
    """Situações distintas pedem correções distintas — não colapsar."""
    itens = [
        _item(1, descricao="PRODUTO X", status="SEM_DESTAQUE"),
        _item(2, descricao="PRODUTO X", status="ALIQUOTA_DIVERGENTE"),
    ]
    assert len(_agrupar_por_produto(itens)) == 2


def test_muitos_itens_paginam_sem_quebrar():
    pdf = _gerar(itens=[_item(i, status="ALIQUOTA_DIVERGENTE") for i in range(1, 201)])
    paginas = pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages")
    assert pdf[:5] == b"%PDF-" and paginas >= 2


def test_gred_no_veio_e_legenda():
    """Item com gRed no XML: o veio abre em nominal→efetiva ("0,10%>0,00%")
    e a carta ganha a legenda explicando a leitura."""
    itens = [_item(1, p_ibs=0.10, p_cbs=0.90,
                   p_aliq_efet_ibs=0.0, p_aliq_efet_cbs=0.0, p_red_aliq=100.0,
                   status="ALIQUOTA_DIVERGENTE")]
    t = _texto(_gerar(itens=itens))
    assert "0,10%>0,00%" in t and "0,90%>0,00%" in t
    assert "NOMINAL" in t and "EFETIVA" in t and "gRed" in t

    # Sem gRed: formato clássico, sem legenda.
    t2 = _texto(_gerar())
    assert ">0," not in t2 and "gRed" not in t2


def test_caracteres_fora_do_latin1_nao_derrubam():
    pdf = _gerar(itens=[_item(descricao="PRODUTO → TESTE 数据 ©", c_class_trib=None)])
    assert pdf[:5] == b"%PDF-"
