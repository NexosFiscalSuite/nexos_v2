"""Fase 2 — extração das tags de ST/FCP (NF-e) e das chaves vinculadas (CT-e)."""
from app.modules.fiscal.domain.parser import parse_xml

_CHAVE_NFE = "1" * 44
_CHAVE_CTE = "3" * 44

# NF-e com CST 10 (ST por MVA) + FCP-ST + IPI. O vBC aparece no ICMS e no IPI:
# o parser deve pegar o do ICMS (escopo no grupo <ICMS>).
_NFE = f"""<nfeProc><NFe><infNFe Id="NFe{_CHAVE_NFE}">
  <ide><mod>55</mod><serie>1</serie><nNF>1</nNF><dhEmi>2026-06-01T10:00:00-03:00</dhEmi></ide>
  <emit><CNPJ>11111111000111</CNPJ><xNome>EMIT</xNome><CRT>3</CRT>
    <enderEmit><UF>SP</UF></enderEmit></emit>
  <dest><CNPJ>22222222000122</CNPJ><xNome>DEST</xNome><enderDest><UF>MG</UF></enderDest></dest>
  <det nItem="1">
    <prod><cProd>A1</cProd><xProd>Autopeca</xProd><NCM>87082919</NCM><CEST>0107500</CEST>
      <CFOP>6404</CFOP><uCom>UN</uCom><qCom>1</qCom><vUnCom>731.35</vUnCom>
      <vProd>731.35</vProd><vOutro>0.00</vOutro></prod>
    <imposto>
      <ICMS><ICMS10>
        <orig>0</orig><CST>10</CST>
        <modBC>3</modBC><vBC>731.35</vBC><pICMS>12.00</pICMS><vICMS>87.76</vICMS>
        <modBCST>4</modBCST><pMVAST>71.78</pMVAST><pICMSST>18.00</pICMSST>
        <vBCST>1473.69</vBCST><vICMSST>177.50</vICMSST>
        <vBCFCPST>1473.69</vBCFCPST><pFCPST>2.00</pFCPST><vFCPST>10.00</vFCPST>
      </ICMS10></ICMS>
      <IPI><IPITrib><vBC>731.35</vBC><pIPI>1.37</pIPI><vIPI>10.02</vIPI></IPITrib></IPI>
    </imposto>
  </det>
  <total><ICMSTot><vNF>918.87</vNF></ICMSTot></total>
</infNFe></NFe></nfeProc>"""

# CT-e que transporta DUAS NF-e (cardinalidade N:N do ADR-0001).
_CTE = f"""<cteProc><CTe><infCte Id="CTe{_CHAVE_CTE}">
  <ide><CFOP>6352</CFOP><dhEmi>2026-06-01T10:00:00-03:00</dhEmi><tpCTe>0</tpCTe>
    <nCT>5</nCT><serie>1</serie></ide>
  <emit><CNPJ>33333333000133</CNPJ><xNome>TRANSP</xNome>
    <enderEmit><UF>SP</UF></enderEmit></emit>
  <vPrest><vTPrest>136.10</vTPrest></vPrest>
  <infCTeNorm><infDoc>
    <infNFe><chave>{"1" * 44}</chave></infNFe>
    <infNFe><chave>{"2" * 44}</chave></infNFe>
  </infDoc></infCTeNorm>
</infCte></CTe></cteProc>"""


def test_parser_nfe_extrai_tags_st_fcp():
    item = parse_xml(_NFE.encode("utf-8"))["itens"][0]

    assert item["cest"] == "0107500"
    assert item["orig"] == "0"
    assert item["cst"] == "10"
    assert item["mod_bc_st"] == 4
    assert item["p_mva_st"] == 71.78
    assert item["p_icms_st"] == 18.00
    assert item["v_bc_st"] == 1473.69
    assert item["valor_icms_st"] == 177.50
    # ICMS próprio (vBC escopado ao ICMS, não confundido com o vBC do IPI).
    assert item["base_calculo"] == 731.35
    assert item["valor_icms"] == 87.76
    assert item["p_icms"] == 12.00
    # FCP-ST em trilha própria.
    assert item["v_fcp_st"] == 10.00
    assert item["p_fcp_st"] == 2.00
    # IPI lido do grupo <IPI>.
    assert item["valor_ipi"] == 10.02


def test_parser_cte_extrai_vtprest_e_chaves_nfe():
    parsed = parse_xml(_CTE.encode("utf-8"))

    assert parsed["tipo"] == "CTe"
    assert parsed["vtprest"] == 136.10
    assert parsed["tp_cte"] == "0"
    assert parsed["chaves_nfe"] == ["1" * 44, "2" * 44]   # N:N: 2 NF-e num CT-e


def test_infra_fiscal_importa_sem_erro():
    """Smoke de import: pega o shadowing de `list[...]` em repositories.py
    (a suíte não importava esse módulo, então o erro passava batido)."""
    from app.modules.fiscal.application.import_service import ImportService  # noqa: F401
    from app.modules.fiscal.infrastructure.models import NfeCteVinculo, NotaItem
    from app.modules.fiscal.infrastructure.repositories import NotaRepository

    assert hasattr(NotaRepository, "add_vinculo_cte")
    assert hasattr(NotaRepository, "ctes_da_nfe")
    assert hasattr(NotaItem, "v_bc_st") and hasattr(NotaItem, "v_fcp_st")
    assert NfeCteVinculo.__tablename__ == "nfe_cte_vinculo"
