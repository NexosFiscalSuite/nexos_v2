"""Relatório de ITENS: tags de capa (Identificação/Emitente) herdadas e repetidas
em cada linha de produto (injeção capa→item)."""
from types import SimpleNamespace

from app.modules.reporting.domain.report_gen import gerar

_CHAVE = "35260112345678901234567890123456789012345678"
_XML = f"""<nfeProc>
  <NFe><infNFe Id="NFe{_CHAVE}">
    <ide><nNF>55</nNF><natOp>Venda</natOp></ide>
    <emit><CNPJ>11111111000111</CNPJ><xNome>FORNECEDOR SP</xNome></emit>
    <det nItem="1"><prod><xProd>Produto A</xProd></prod></det>
    <det nItem="2"><prod><xProd>Produto B</xProd></prod></det>
  </infNFe></NFe>
  <protNFe><infProt><chNFe>{_CHAVE}</chNFe></infProt></protNFe>
</nfeProc>""".encode()


def test_tags_de_capa_sao_repetidas_em_cada_linha_de_item():
    nota = SimpleNamespace(numero="55", serie="1", chave_acesso=_CHAVE, nome_emit="FORNECEDOR SP")
    config = {
        "capa": [],
        "itens": [{"tag": "chNFe"}, {"tag": "emit_CNPJ"}, {"tag": "it_xProd"}],
        "finalidade": False, "calculos": False, "totais": False,
    }
    res = gerar(config, [{"nota": nota, "tipos": {1: "", 2: ""}, "xml": _XML}], regime="Simples Nacional")

    itens = res["itens"]
    grupos = [c["grupo"] for c in itens["cols"]]
    assert "Identificação" in grupos and "Emitente" in grupos   # tags de capa entraram nos itens
    assert len(itens["rows"]) == 2

    # A chave de acesso e o CNPJ do emitente repetem em TODAS as linhas de produto.
    for linha in itens["rows"]:
        assert _CHAVE in linha
        assert "11111111000111" in linha
    assert "Produto A" in itens["rows"][0]
    assert "Produto B" in itens["rows"][1]
