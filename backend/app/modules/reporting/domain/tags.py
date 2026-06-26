"""Dicionário de tags SEFAZ (MOC) para o gerador de relatórios.

Cada tag: key, label, escopo ('capa' = nível NF | 'item'), grupo (para a UI),
path (lista de local-names a descer no XML, buscando 1º descendente em cada nível)
e money (bool — coluna financeira: formata, soma com SUBTOTAL e pode sofrer vedação).

A extração é por local-name (ignora namespace) e desce por descendentes, então
os grupos de imposto (ICMS00/ICMSSN…, PISAliq…, etc.) são resolvidos sem fixar a
variante. Foco em NF-e/NFC-e (modelo 55/65).
"""

# (key, label, escopo, grupo, path, money)
_DEFS = [
    # ── Capa: identificação ──
    ("chNFe", "Chave de Acesso", "capa", "Identificação", ["protNFe", "infProt", "chNFe"], False),
    ("nNF", "Número", "capa", "Identificação", ["ide", "nNF"], False),
    ("serie", "Série", "capa", "Identificação", ["ide", "serie"], False),
    ("dhEmi", "Data de Emissão", "capa", "Identificação", ["ide", "dhEmi"], False),
    ("dhSaiEnt", "Data Saída/Entrada", "capa", "Identificação", ["ide", "dhSaiEnt"], False),
    ("natOp", "Natureza da Operação", "capa", "Identificação", ["ide", "natOp"], False),
    ("tpNF", "Tipo (0=Ent,1=Saí)", "capa", "Identificação", ["ide", "tpNF"], False),
    ("modelo", "Modelo", "capa", "Identificação", ["ide", "mod"], False),
    # ── Capa: emitente ──
    ("emit_CNPJ", "CNPJ Emitente", "capa", "Emitente", ["emit", "CNPJ"], False),
    ("emit_xNome", "Nome Emitente", "capa", "Emitente", ["emit", "xNome"], False),
    ("emit_IE", "IE Emitente", "capa", "Emitente", ["emit", "IE"], False),
    ("emit_UF", "UF Emitente", "capa", "Emitente", ["emit", "enderEmit", "UF"], False),
    ("emit_xMun", "Município Emitente", "capa", "Emitente", ["emit", "enderEmit", "xMun"], False),
    # ── Capa: destinatário ──
    ("dest_CNPJ", "CNPJ/CPF Destinatário", "capa", "Destinatário", ["dest", "CNPJ"], False),
    ("dest_xNome", "Nome Destinatário", "capa", "Destinatário", ["dest", "xNome"], False),
    ("dest_IE", "IE Destinatário", "capa", "Destinatário", ["dest", "IE"], False),
    ("dest_UF", "UF Destinatário", "capa", "Destinatário", ["dest", "enderDest", "UF"], False),
    # ── Capa: totais (ICMSTot) — agrupados por tipo de imposto p/ cor ──
    ("vProd", "Valor Produtos", "capa", "Totais", ["total", "ICMSTot", "vProd"], True),
    ("vFrete", "Frete", "capa", "Totais", ["total", "ICMSTot", "vFrete"], True),
    ("vSeg", "Seguro", "capa", "Totais", ["total", "ICMSTot", "vSeg"], True),
    ("vDesc", "Desconto", "capa", "Totais", ["total", "ICMSTot", "vDesc"], True),
    ("vOutro", "Outras Despesas", "capa", "Totais", ["total", "ICMSTot", "vOutro"], True),
    ("vNF", "Valor Total da NF", "capa", "Totais", ["total", "ICMSTot", "vNF"], True),
    ("vBC", "BC ICMS", "capa", "ICMS", ["total", "ICMSTot", "vBC"], True),
    ("vICMS", "Valor ICMS", "capa", "ICMS", ["total", "ICMSTot", "vICMS"], True),
    ("vBCST", "BC ICMS ST", "capa", "ICMS ST", ["total", "ICMSTot", "vBCST"], True),
    ("vST", "Valor ICMS ST", "capa", "ICMS ST", ["total", "ICMSTot", "vST"], True),
    ("vIPI", "Valor IPI", "capa", "IPI", ["total", "ICMSTot", "vIPI"], True),
    ("vPIS", "Valor PIS", "capa", "PIS", ["total", "ICMSTot", "vPIS"], True),
    ("vCOFINS", "Valor COFINS", "capa", "COFINS", ["total", "ICMSTot", "vCOFINS"], True),
    # ── Capa: transporte / pagamento ──
    ("modFrete", "Modalidade Frete", "capa", "Transporte", ["transp", "modFrete"], False),
    ("transporta_xNome", "Transportadora", "capa", "Transporte", ["transp", "transporta", "xNome"], False),
    ("tPag", "Forma de Pagamento", "capa", "Pagamento", ["pag", "detPag", "tPag"], False),
    ("vPag", "Valor Pago", "capa", "Pagamento", ["pag", "detPag", "vPag"], True),
    # ── Capa: informações adicionais (observação da nota) ──
    ("infCpl", "Informações Complementares", "capa", "Adicionais", ["infAdic", "infCpl"], False),
    ("obsCont", "Observação do Contribuinte", "capa", "Adicionais", ["infAdic", "obsCont", "xTexto"], False),
    # ── Capa: situação / autenticação SEFAZ (protNFe, fora de infNFe) ──
    ("situacao", "Autenticação SEFAZ", "capa", "Situação", ["protNFe", "infProt", "cStat"], False),
    ("cStat", "Status SEFAZ (cód.)", "capa", "Situação", ["protNFe", "infProt", "cStat"], False),
    ("xMotivo", "Motivo SEFAZ", "capa", "Situação", ["protNFe", "infProt", "xMotivo"], False),
    ("nProt", "Protocolo de Autorização", "capa", "Situação", ["protNFe", "infProt", "nProt"], False),

    # ── Item: produto ──
    ("it_cProd", "Código Produto", "item", "Produto", ["prod", "cProd"], False),
    ("it_xProd", "Descrição", "item", "Produto", ["prod", "xProd"], False),
    ("it_NCM", "NCM", "item", "Produto", ["prod", "NCM"], False),
    ("it_CEST", "CEST", "item", "Produto", ["prod", "CEST"], False),
    ("it_CFOP", "CFOP", "item", "Produto", ["prod", "CFOP"], False),
    ("it_cEAN", "EAN", "item", "Produto", ["prod", "cEAN"], False),
    ("it_uCom", "Unidade", "item", "Produto", ["prod", "uCom"], False),
    ("it_qCom", "Quantidade", "item", "Produto", ["prod", "qCom"], True),
    ("it_vUnCom", "Valor Unitário", "item", "Produto", ["prod", "vUnCom"], True),
    ("it_vProd", "Valor Produto", "item", "Produto", ["prod", "vProd"], True),
    ("it_vDesc", "Desconto", "item", "Produto", ["prod", "vDesc"], True),
    ("it_vFrete", "Frete", "item", "Produto", ["prod", "vFrete"], True),
    ("it_vSeg", "Seguro", "item", "Produto", ["prod", "vSeg"], True),
    ("it_vOutro", "Outras Despesas", "item", "Produto", ["prod", "vOutro"], True),
    # ── Item: ICMS ──
    ("it_orig", "Origem", "item", "ICMS", ["imposto", "ICMS", "orig"], False),
    ("it_CST", "CST/CSOSN ICMS", "item", "ICMS", ["imposto", "ICMS", "CST"], False),
    ("it_CSOSN", "CSOSN", "item", "ICMS", ["imposto", "ICMS", "CSOSN"], False),
    ("it_vBC", "BC ICMS", "item", "ICMS", ["imposto", "ICMS", "vBC"], True),
    ("it_pICMS", "Alíquota ICMS", "item", "ICMS", ["imposto", "ICMS", "pICMS"], False),
    ("it_vICMS", "Valor ICMS", "item", "ICMS", ["imposto", "ICMS", "vICMS"], True),
    ("it_vBCST", "BC ICMS ST", "item", "ICMS ST", ["imposto", "ICMS", "vBCST"], True),
    ("it_vICMSST", "Valor ICMS ST", "item", "ICMS ST", ["imposto", "ICMS", "vICMSST"], True),
    # ── Item: IPI ──
    ("it_IPI_CST", "CST IPI", "item", "IPI", ["imposto", "IPI", "CST"], False),
    ("it_IPI_vBC", "BC IPI", "item", "IPI", ["imposto", "IPI", "vBC"], True),
    ("it_IPI_pIPI", "Alíquota IPI", "item", "IPI", ["imposto", "IPI", "pIPI"], False),
    ("it_IPI_vIPI", "Valor IPI", "item", "IPI", ["imposto", "IPI", "vIPI"], True),
    # ── Item: PIS ──
    ("it_PIS_CST", "CST PIS", "item", "PIS", ["imposto", "PIS", "CST"], False),
    ("it_PIS_vBC", "BC PIS", "item", "PIS", ["imposto", "PIS", "vBC"], True),
    ("it_PIS_pPIS", "Alíquota PIS", "item", "PIS", ["imposto", "PIS", "pPIS"], False),
    ("it_PIS_vPIS", "Valor PIS", "item", "PIS", ["imposto", "PIS", "vPIS"], True),
    # ── Item: COFINS ──
    ("it_COFINS_CST", "CST COFINS", "item", "COFINS", ["imposto", "COFINS", "CST"], False),
    ("it_COFINS_vBC", "BC COFINS", "item", "COFINS", ["imposto", "COFINS", "vBC"], True),
    ("it_COFINS_pCOFINS", "Alíquota COFINS", "item", "COFINS", ["imposto", "COFINS", "pCOFINS"], False),
    ("it_COFINS_vCOFINS", "Valor COFINS", "item", "COFINS", ["imposto", "COFINS", "vCOFINS"], True),
]

TAGS = {
    key: {"key": key, "label": label, "escopo": escopo, "grupo": grupo, "path": path, "money": money}
    for (key, label, escopo, grupo, path, money) in _DEFS
}


def tags_por_escopo(escopo: str) -> list[dict]:
    return [t for t in TAGS.values() if t["escopo"] == escopo]


# ── Tags derivadas (valor transformado após extrair) ──
DERIVE = {"situacao": "situacao"}

_SITUACAO = {
    "100": "Autorizada", "150": "Autorizada",
    "101": "Cancelada", "151": "Cancelada", "135": "Cancelada",
    "110": "Denegada", "301": "Denegada", "302": "Denegada", "303": "Denegada",
}


def situacao(cstat: str) -> str:
    c = (cstat or "").strip()
    if not c:
        return ""
    return _SITUACAO.get(c, f"cStat {c}")
