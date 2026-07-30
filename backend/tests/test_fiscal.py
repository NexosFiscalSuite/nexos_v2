"""Testes do domínio fiscal portado: parser de XML, classificação de fluxo e
mapa CFOP->SPED. Tudo stdlib (sem banco)."""
import pytest

from app.modules.fiscal.domain import parser as xmlparser
from app.modules.fiscal.domain.cfop_sped import sugerir_tipo_sped
from app.modules.fiscal.domain.flow import FlowRejected, classificar_fluxo

# NF-e mínima (modelo 55). Chave = 44 dígitos.
_CHAVE = "3" * 44
NFE_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe Id="NFe{_CHAVE}">
      <ide><mod>55</mod><serie>1</serie><nNF>15</nNF><dhEmi>2026-03-10T10:00:00-03:00</dhEmi></ide>
      <emit><CNPJ>11444777000161</CNPJ><xNome>Empresa Emitente LTDA</xNome>
        <enderEmit><UF>SP</UF></enderEmit></emit>
      <dest><CNPJ>11222333000181</CNPJ><xNome>Cliente Destino SA</xNome>
        <enderDest><UF>RJ</UF></enderDest></dest>
      <det nItem="1"><prod>
        <cProd>001</cProd><xProd>Produto X</xProd><NCM>12345678</NCM><CFOP>5102</CFOP>
        <uCom>UN</uCom><qCom>2.0000</qCom><vUnCom>50.00</vUnCom><vProd>100.00</vProd>
      </prod></det>
      <total><ICMSTot><vNF>100.00</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
  <protNFe><infProt><nProt>123456789</nProt></infProt></protNFe>
</nfeProc>
""".encode()


def test_parse_nfe():
    p = xmlparser.parse_xml(NFE_XML)
    assert p["tipo"] == "NFe"
    assert p["modelo"] == "55"
    assert p["chave_acesso"] == _CHAVE
    assert p["cnpj_emit"] == "11444777000161"
    assert p["cnpj_dest"] == "11222333000181"
    assert p["valor_total"] == 100.0
    assert len(p["itens"]) == 1
    assert p["itens"][0]["cfop"] == "5102"
    assert p["itens"][0]["ncm"] == "12345678"


def test_parse_xml_multi_envelopa_unico():
    assert len(xmlparser.parse_xml_multi(NFE_XML)) == 1


def test_xml_invalido():
    with pytest.raises(ValueError):
        xmlparser.parse_xml(b"<isto/>")


def test_classificar_fluxo():
    p = xmlparser.parse_xml(NFE_XML)
    assert classificar_fluxo(p, "11444777000161") == "saida"   # empresa = emitente
    assert classificar_fluxo(p, "11222333000181") == "entrada"  # empresa = destinatária
    with pytest.raises(FlowRejected):
        classificar_fluxo(p, "99999999000199")


def test_classificar_fluxo_nota_de_entrada_tpnf0():
    """Nota de ENTRADA (tpNF=0) emitida pelo comprador — padrão na compra de
    produtor rural: para o emitente é compra; quem está no destinatário (o
    produtor) é o remetente da mercadoria, ou seja, fez a VENDA."""
    p = xmlparser.parse_xml(NFE_XML)
    p["tp_nf"] = "0"
    assert classificar_fluxo(p, "11444777000161") == "entrada"   # comprador
    assert classificar_fluxo(p, "11222333000181") == "saida"     # produtor


def test_parser_extrai_tpnf():
    xml = NFE_XML.replace(b"<mod>55</mod>", b"<mod>55</mod><tpNF>0</tpNF>")
    assert xmlparser.parse_xml(xml)["tp_nf"] == "0"
    assert xmlparser.parse_xml(NFE_XML)["tp_nf"] is None   # sem a tag: padrão


def test_cfop_sped():
    assert sugerir_tipo_sped("1102") == "Mercadoria para Revenda"
    assert sugerir_tipo_sped("1551") == "Ativo Imobilizado"
    assert sugerir_tipo_sped("5999") == ""
    assert sugerir_tipo_sped("") == ""
