"""Parser de XMLs fiscais (portado do Nexos V1 — lógica validada em produção).

Suporta:
  - NF-e (modelo 55) / NFC-e (modelo 65)  - nfeProc / NFe
  - CT-e (modelo 57)                       - cteProc / CTe
  - NFS-e ABRASF                           - CompNfse / Nfse (xmlns abrasf.org.br)
  - NFS-e Padrão Nacional                  - <NFSe> com <infNFSe> (sped.fazenda)
  - procEventoNFe                          - eventos de cancelamento (tpEvento=110111)

Retorna sempre um dict normalizado ou levanta ValueError com mensagem clara.
`modelo` reflete: '55', '65', '57', 'NFSe-A' (ABRASF) ou 'NFSe-N' (Nacional).
"""
import re
from datetime import datetime
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException

# XML de upload é hostil por padrão: defusedxml bloqueia XXE e expansão de
# entidades (billion laughs). fromstring é drop-in da stdlib.
from defusedxml.ElementTree import fromstring

NS_NFSE_ABRASF = "http://www.abrasf.org.br/nfse.xsd"
TP_EVENTO_CANCELAMENTO = "110111"
TP_EVENTO_CCE = "110110"  # Carta de Correção Eletrônica


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _find_local(el, name: str):
    if el is None:
        return None
    for child in el.iter():
        if _local(child.tag) == name:
            return child
    return None


def _findall_local(el, name: str):
    if el is None:
        return []
    return [c for c in el.iter() if _local(c.tag) == name]


def _first_el(*els):
    """Primeiro elemento não-None. NÃO usar `a or b` com Elements: a verdade de
    um Element é deprecada e um elemento sem filhos é avaliado como falso."""
    for e in els:
        if e is not None:
            return e
    return None


def _text(el) -> str:
    if el is None:
        return ""
    return (el.text or "").strip()


def _g(el, name: str) -> str:
    return _text(_find_local(el, name))


def _f(s: str) -> float:
    if not s:
        return 0.0
    s = str(s).strip().replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _i(s: str) -> int:
    if not s:
        return 0
    try:
        return int(float(str(s).strip().replace(",", ".")))
    except (ValueError, TypeError):
        return 0


def _clean_cnpj(c: str) -> str:
    return re.sub(r"\D", "", c or "")


def _parse_dt(s: str) -> tuple:
    """ISO date (com/sem hora/tz) -> (YYYY-MM-DD, ano, mes). Tolerante."""
    if not s:
        return ("", "", "")
    s = s.strip()
    s_norm = re.sub(r"([+-]\d{2}:?\d{2}|Z)$", "", s)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s_norm, fmt)
            return (dt.strftime("%Y-%m-%d"), f"{dt.year:04d}", f"{dt.month:02d}")
        except ValueError:
            continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return (f"{m.group(1)}-{m.group(2)}-{m.group(3)}", m.group(1), m.group(2))
    return ("", "", "")


# --------------------------------------------------------------------------- #
# Identificação do tipo
# --------------------------------------------------------------------------- #
class TipoXML:
    NFE = "NFe"
    CTE = "CTe"
    NFSE_ABRASF = "NFSe-A"
    NFSE_NACIONAL = "NFSe-N"
    EVENTO_CANCELAMENTO = "EventoCancelamento"
    EVENTO_CCE = "EventoCCe"
    DESCONHECIDO = "Desconhecido"


def identificar_tipo(root) -> str:
    root_local = _local(root.tag)

    if root_local in ("procEventoNFe", "evento", "envEvento", "retEnvEvento", "procEventoCTe"):
        tp = _g(root, "tpEvento")
        desc = _g(root, "descEvento") or ""
        if tp == TP_EVENTO_CANCELAMENTO or "Cancelamento" in desc:
            return TipoXML.EVENTO_CANCELAMENTO
        if tp == TP_EVENTO_CCE or "Correção" in desc or "Correcao" in desc:
            return TipoXML.EVENTO_CCE
        return "EventoOutro"

    if root_local in ("nfeProc", "NFe"):
        return TipoXML.NFE
    if root_local in ("cteProc", "CTe"):
        return TipoXML.CTE

    if NS_NFSE_ABRASF in (root.tag or ""):
        return TipoXML.NFSE_ABRASF
    if root_local in (
        "ConsultarNfseFaixaResposta",
        "ConsultarNfseResposta",
        "GerarNfseResposta",
        "CompNfse",
        "Nfse",
    ):
        return TipoXML.NFSE_ABRASF

    if root_local in ("NFSe",) and _find_local(root, "infNFSe") is not None:
        return TipoXML.NFSE_NACIONAL

    if _find_local(root, "infNFe") is not None:
        return TipoXML.NFE
    if _find_local(root, "infCte") is not None:
        return TipoXML.CTE
    if _find_local(root, "Nfse") is not None and _find_local(root, "InfNfse") is not None:
        return TipoXML.NFSE_ABRASF
    if _find_local(root, "infNFSe") is not None:
        return TipoXML.NFSE_NACIONAL

    return TipoXML.DESCONHECIDO


# --------------------------------------------------------------------------- #
# Endereços
# --------------------------------------------------------------------------- #
def _endereco_abrasf(ender_el) -> dict:
    if ender_el is None:
        return {}
    return {
        "logradouro": _g(ender_el, "Endereco"),
        "numero": _g(ender_el, "Numero"),
        "complemento": _g(ender_el, "Complemento"),
        "bairro": _g(ender_el, "Bairro"),
        "municipio": _g(ender_el, "CodigoMunicipio"),
        "uf": _g(ender_el, "Uf"),
        "cep": _g(ender_el, "Cep"),
        "pais": "Brasil",
    }


def _endereco_nac(ender_el) -> dict:
    if ender_el is None:
        return {}
    return {
        "logradouro": _g(ender_el, "xLgr"),
        "numero": _g(ender_el, "nro"),
        "complemento": _g(ender_el, "xCpl"),
        "bairro": _g(ender_el, "xBairro"),
        "municipio": _g(ender_el, "cMun"),
        "uf": _g(ender_el, "UF"),
        "cep": _g(ender_el, "CEP"),
        "pais": "Brasil",
    }


def _endereco_nfe(ender_el) -> dict:
    if ender_el is None:
        return {}
    return {
        "logradouro": _g(ender_el, "xLgr"),
        "numero": _g(ender_el, "nro"),
        "complemento": _g(ender_el, "xCpl"),
        "bairro": _g(ender_el, "xBairro"),
        "municipio": _g(ender_el, "xMun"),
        "uf": _g(ender_el, "UF"),
        "cep": _g(ender_el, "CEP"),
        "pais": _g(ender_el, "xPais") or "Brasil",
    }


# --------------------------------------------------------------------------- #
# NF-e / NFC-e
# --------------------------------------------------------------------------- #
def _parse_nfe(root) -> dict:
    inf_nfe = _find_local(root, "infNFe")
    if inf_nfe is None:
        raise ValueError("XML NF-e sem tag <infNFe>")

    raw_id = inf_nfe.get("Id") or ""
    chave = re.sub(r"^NFe", "", raw_id).strip()
    if not re.fullmatch(r"\d{44}", chave):
        chave = _g(root, "chNFe") or ""
    chave = re.sub(r"\D", "", chave)
    if len(chave) != 44:
        raise ValueError("Chave de acesso da NF-e inválida (esperado 44 dígitos)")

    ide = _find_local(inf_nfe, "ide")
    emit = _find_local(inf_nfe, "emit")
    dest = _find_local(inf_nfe, "dest")
    total = _find_local(inf_nfe, "total")
    transp = _find_local(inf_nfe, "transp")
    prot = _first_el(_find_local(root, "protNFe"), _find_local(root, "infProt"))

    mod = _g(ide, "mod") or chave[20:22]
    tipo = "NFe" if mod == "55" else ("NFCe" if mod == "65" else "NFe")

    data_iso, ano, mes = _parse_dt(_g(ide, "dhEmi") or _g(ide, "dEmi"))

    cnpj_emit = _clean_cnpj(_g(emit, "CNPJ") or _g(emit, "CPF"))
    cnpj_dest = _clean_cnpj(_g(dest, "CNPJ") or _g(dest, "CPF"))

    transporta = _find_local(transp, "transporta") if transp is not None else None
    icms_tot = _find_local(total, "ICMSTot") if total is not None else None

    itens = []
    for det in _findall_local(inf_nfe, "det"):
        nitem = _i(det.get("nItem")) or (len(itens) + 1)
        prod = _find_local(det, "prod")
        if prod is None:
            continue
        # Imposto: tags de ICMS/FCP ficam sob det/imposto/ICMS/ICMSxx (ou ICMSSNxxx).
        # Escopa ao grupo <ICMS> para não confundir o vBC do ICMS com o vBC do IPI.
        imposto = _find_local(det, "imposto")
        icms = _find_local(imposto, "ICMS")
        ipi = _find_local(imposto, "IPI")
        # Reforma Tributária (NT 2025.002): grupo <IBSCBS> com o destaque de
        # IBS (UF+Mun) e CBS — obrigatório no ano-teste 2026 (ADCT art. 125).
        # Escopado ao grupo para o vBC do IBS/CBS não colidir com o do ICMS.
        ibscbs = _find_local(imposto, "IBSCBS")
        modbcst = _g(icms, "modBCST")
        itens.append({
            "numero_item": nitem,
            "codigo": _g(prod, "cProd"),
            "descricao": _g(prod, "xProd"),
            "ncm": _g(prod, "NCM"),
            "cest": _g(prod, "CEST"),
            "cfop": _g(prod, "CFOP"),
            "unidade": _g(prod, "uCom") or _g(prod, "uTrib"),
            "quantidade": _f(_g(prod, "qCom") or _g(prod, "qTrib")),
            "valor_unitario": _f(_g(prod, "vUnCom") or _g(prod, "vUnTrib")),
            "valor_total": _f(_g(prod, "vProd")),
            "valor_produto": _f(_g(prod, "vProd")),
            "valor_desconto": _f(_g(prod, "vDesc")),
            "valor_frete": _f(_g(prod, "vFrete")),
            "valor_seguro": _f(_g(prod, "vSeg")),
            "valor_outro": _f(_g(prod, "vOutro")),
            "valor_ipi": _f(_g(ipi, "vIPI")),
            # Situação tributária e origem
            "orig": _g(icms, "orig"),
            "cst": _g(icms, "CST"),
            "csosn": _g(icms, "CSOSN"),
            # ICMS próprio
            "base_calculo": _f(_g(icms, "vBC")),
            "valor_icms": _f(_g(icms, "vICMS")),
            "p_icms": _f(_g(icms, "pICMS")),
            "p_red_bc": _f(_g(icms, "pRedBC")),
            # ICMS-ST
            "mod_bc_st": _i(modbcst) if modbcst else None,
            "p_mva_st": _f(_g(icms, "pMVAST")),
            "p_red_bc_st": _f(_g(icms, "pRedBCST")),
            "p_icms_st": _f(_g(icms, "pICMSST")),
            "v_bc_st": _f(_g(icms, "vBCST")),
            "valor_icms_st": _f(_g(icms, "vICMSST")),
            # FCP (próprio e ST) — trilhas paralelas
            "v_fcp": _f(_g(icms, "vFCP")),
            "p_fcp": _f(_g(icms, "pFCP")),
            "v_bc_fcp": _f(_g(icms, "vBCFCP")),
            "v_fcp_st": _f(_g(icms, "vFCPST")),
            "p_fcp_st": _f(_g(icms, "pFCPST")),
            "v_bc_fcp_st": _f(_g(icms, "vBCFCPST")),
            # IBS/CBS (Reforma Tributária — destaque do ano-teste 2026)
            "cst_ibs_cbs": _g(ibscbs, "CST") or None,
            "v_bc_ibs_cbs": _f(_g(ibscbs, "vBC")),
            "p_ibs_uf": _f(_g(ibscbs, "pIBSUF")),
            "v_ibs_uf": _f(_g(ibscbs, "vIBSUF")),
            "p_ibs_mun": _f(_g(ibscbs, "pIBSMun")),
            "v_ibs_mun": _f(_g(ibscbs, "vIBSMun")),
            "p_cbs": _f(_g(ibscbs, "pCBS")),
            "v_cbs": _f(_g(ibscbs, "vCBS")),
        })

    return {
        "tipo": tipo,
        "modelo": mod,
        "chave_acesso": chave,
        "serie": _g(ide, "serie"),
        "numero": _g(ide, "nNF"),
        "data_emissao": data_iso,
        "ano": ano,
        "mes": mes,
        "cnpj_emit": cnpj_emit,
        "nome_emit": _g(emit, "xNome"),
        "ie_emit": _g(emit, "IE"),
        "uf_emit": _g(_find_local(emit, "enderEmit"), "UF"),
        # CRT do emitente (1=Simples, 2=Simples excesso, 3=Normal, 4=MEI) —
        # fonte primária do regime do fornecedor para o motor de auditoria de ST.
        "crt_emit": _g(emit, "CRT"),
        "cnpj_dest": cnpj_dest,
        "nome_dest": _g(dest, "xNome"),
        "ie_dest": _g(dest, "IE"),
        "uf_dest": _g(_find_local(dest, "enderDest"), "UF"),
        "endereco_emit": _endereco_nfe(_find_local(emit, "enderEmit")),
        "endereco_dest": _endereco_nfe(_find_local(dest, "enderDest")),
        "transportadora_cnpj": _clean_cnpj(_g(transporta, "CNPJ") or _g(transporta, "CPF")),
        "transportadora_nome": _g(transporta, "xNome"),
        "valor_total": _f(_g(icms_tot, "vNF")),
        "protocolo": _g(prot, "nProt") if prot is not None else "",
        "iss_retido": None,
        "itens": itens,
    }


# --------------------------------------------------------------------------- #
# CT-e
# --------------------------------------------------------------------------- #
def _parse_cte(root) -> dict:
    inf_cte = _find_local(root, "infCte")
    if inf_cte is None:
        raise ValueError("XML CT-e sem tag <infCte>")

    raw_id = inf_cte.get("Id") or ""
    chave = re.sub(r"\D", "", re.sub(r"^CTe", "", raw_id).strip())
    if len(chave) != 44:
        chave = re.sub(r"\D", "", _g(root, "chCTe") or "")
    if len(chave) != 44:
        raise ValueError("Chave de acesso do CT-e inválida")

    ide = _find_local(inf_cte, "ide")
    emit = _find_local(inf_cte, "emit")
    rem = _find_local(inf_cte, "rem")
    exped = _find_local(inf_cte, "exped")
    receb = _find_local(inf_cte, "receb")
    dest_node = _find_local(inf_cte, "dest")
    v_prest = _find_local(inf_cte, "vPrest")

    data_iso, ano, mes = _parse_dt(_g(ide, "dhEmi"))
    cnpj_emit = _clean_cnpj(_g(emit, "CNPJ"))

    # Tomador: toma4 (CNPJ direto) ou toma3 (código 0=rem,1=exped,2=receb,3=dest)
    toma_codigo = _g(ide, "toma") or _g(_find_local(ide, "toma3"), "toma")
    cnpj_toma = nome_toma = uf_toma = ""
    toma4 = _find_local(ide, "toma4")
    if toma4 is not None:
        cnpj_toma = _clean_cnpj(_g(toma4, "CNPJ") or _g(toma4, "CPF"))
        nome_toma = _g(toma4, "xNome")
        uf_toma = _g(_find_local(toma4, "enderToma"), "UF")
    elif toma_codigo:
        node = {"0": rem, "1": exped, "2": receb, "3": dest_node}.get(toma_codigo)
        if node is not None:
            cnpj_toma = _clean_cnpj(_g(node, "CNPJ") or _g(node, "CPF"))
            nome_toma = _g(node, "xNome")
            for ender_tag in ("enderReme", "enderExped", "enderReceb", "enderDest"):
                en = _find_local(node, ender_tag)
                if en is not None:
                    uf_toma = _g(en, "UF")
                    break

    valor_total = _f(_g(v_prest, "vTPrest"))

    # Chaves das NF-e transportadas (1..N) — base do ADR-0001 (cardinalidade N:N).
    # Ficam em infCte/infCTeNorm/infDoc/infNFe/chave (uma por documento).
    chaves_nfe = []
    for infnfe in _findall_local(inf_cte, "infNFe"):
        ch = re.sub(r"\D", "", _g(infnfe, "chave"))
        if len(ch) == 44 and ch not in chaves_nfe:
            chaves_nfe.append(ch)
    tp_cte = _g(ide, "tpCTe")   # 0=normal, 1=complementar, 2=anulação, 3=substituto

    cfop = _g(ide, "CFOP") or _g(_find_local(inf_cte, "imp"), "CFOP")
    info_doc = _first_el(_find_local(inf_cte, "infCTeNorm"), inf_cte)
    obs = _g(info_doc, "infCarga") or _g(inf_cte, "xObs")
    descricao = f"Serviço de transporte - {obs[:200]}" if obs else "Serviço de transporte"

    itens = [{
        "numero_item": 1, "codigo": "TRANSP", "descricao": descricao, "ncm": "",
        "cfop": cfop, "unidade": "UN", "quantidade": 1.0,
        "valor_unitario": valor_total, "valor_total": valor_total,
        "valor_desconto": 0.0, "valor_frete": 0.0, "valor_seguro": 0.0,
    }]

    return {
        "tipo": "CTe",
        "modelo": "57",
        "chave_acesso": chave,
        "serie": _g(ide, "serie"),
        "numero": _g(ide, "nCT"),
        "data_emissao": data_iso,
        "ano": ano,
        "mes": mes,
        "cnpj_emit": cnpj_emit,
        "nome_emit": _g(emit, "xNome"),
        "ie_emit": _g(emit, "IE"),
        "uf_emit": _g(_find_local(emit, "enderEmit"), "UF"),
        "cnpj_dest": cnpj_toma,
        "nome_dest": nome_toma,
        "ie_dest": "",
        "uf_dest": uf_toma,
        "endereco_emit": {},
        "endereco_dest": {},
        "transportadora_cnpj": cnpj_emit,
        "transportadora_nome": _g(emit, "xNome"),
        "valor_total": valor_total,
        "protocolo": _g(root, "nProt"),
        "iss_retido": None,
        "vtprest": valor_total,
        "chaves_nfe": chaves_nfe,
        "tp_cte": tp_cte,
        "itens": itens,
    }


# --------------------------------------------------------------------------- #
# NFS-e ABRASF
# --------------------------------------------------------------------------- #
def _parse_nfse_abrasf_single(nfse_node, root_for_cancel) -> dict:
    inf_nfse = _find_local(nfse_node, "InfNfse")
    if inf_nfse is None:
        raise ValueError("XML NFS-e ABRASF sem tag <InfNfse>")

    numero = _g(inf_nfse, "Numero")
    data_iso, ano, mes = _parse_dt(_g(inf_nfse, "DataEmissao"))
    valores = _find_local(inf_nfse, "ValoresNfse")
    valor_total = _f(_g(valores, "ValorLiquidoNfse") or _g(valores, "BaseCalculo"))

    prestador = _find_local(inf_nfse, "PrestadorServico")
    cnpj_emit = _clean_cnpj(_g(_find_local(prestador, "IdentificacaoPrestador"), "Cnpj"))

    decl = _find_local(inf_nfse, "DeclaracaoPrestacaoServico")
    inf_decl = _find_local(decl, "InfDeclaracaoPrestacaoServico") if decl is not None else None
    servico = _find_local(inf_decl, "Servico") if inf_decl is not None else None
    tomador = _find_local(inf_decl, "Tomador") if inf_decl is not None else None

    cnpj_dest = nome_dest = uf_dest = ""
    if tomador is not None:
        ident = _find_local(tomador, "IdentificacaoTomador")
        if ident is not None:
            cnpj_dest = _clean_cnpj(_g(ident, "Cnpj") or _g(ident, "Cpf"))
        nome_dest = _g(tomador, "RazaoSocial")
        uf_dest = _g(_find_local(tomador, "Endereco"), "Uf")

    competencia_raw = _g(inf_decl, "Competencia") if inf_decl is not None else ""
    _, comp_ano, comp_mes = _parse_dt(competencia_raw)
    competencia = f"{comp_ano}-{comp_mes}" if comp_ano and comp_mes else f"{ano}-{mes}"

    iss_retido = None
    if servico is not None:
        iss_raw = _g(servico, "IssRetido")  # ABRASF: 1=SIM, 2=NAO
        if iss_raw == "1":
            iss_retido = 1
        elif iss_raw == "2":
            iss_retido = 0

    discriminacao = _g(servico, "Discriminacao") if servico is not None else ""
    item_lista = _g(servico, "ItemListaServico") if servico is not None else ""
    codigo_trib = _g(servico, "CodigoTributacaoMunicipio") if servico is not None else ""

    itens = [{
        "numero_item": 1,
        "codigo": codigo_trib or item_lista,
        "descricao": discriminacao or f"Serviço ItemListaServico {item_lista}",
        "ncm": "", "cfop": "", "unidade": "UN", "quantidade": 1.0,
        "valor_unitario": valor_total, "valor_total": valor_total,
        "valor_desconto": 0.0, "valor_frete": 0.0, "valor_seguro": 0.0,
    }]

    cancelada = False
    cancelada_em = ""
    canc = _find_local(root_for_cancel, "NfseCancelamento")
    if canc is not None:
        ident_canc = _find_local(canc, "IdentificacaoNfse")
        if ident_canc is not None and _g(ident_canc, "Numero") == numero:
            cancelada = True
            cancelada_em = _g(canc, "DataHora")

    return {
        "tipo": "NFSe",
        "modelo": "NFSe-A",
        "chave_acesso": f"NFSE-{cnpj_emit}-{numero}".replace(" ", ""),
        "serie": "",
        "numero": numero,
        "data_emissao": data_iso,
        "ano": ano,
        "mes": mes,
        "cnpj_emit": cnpj_emit,
        "nome_emit": _g(prestador, "RazaoSocial"),
        "ie_emit": "",
        "uf_emit": _g(_find_local(prestador, "Endereco"), "Uf"),
        "cnpj_dest": cnpj_dest,
        "nome_dest": nome_dest,
        "ie_dest": "",
        "uf_dest": uf_dest,
        "transportadora_cnpj": "",
        "transportadora_nome": "",
        "valor_total": valor_total,
        "protocolo": "",
        "iss_retido": iss_retido,
        "competencia": competencia,
        "itens": itens,
        "endereco_emit": _endereco_abrasf(_find_local(prestador, "Endereco")),
        "endereco_dest": _endereco_abrasf(_find_local(tomador, "Endereco")) if tomador is not None else {},
        "_cancelada_inline": cancelada,
        "_cancelada_em": cancelada_em,
    }


def _parse_nfse_abrasf(root) -> dict:
    nfse = _find_local(root, "Nfse")
    if nfse is None:
        raise ValueError("XML NFS-e ABRASF sem tag <Nfse>")
    return _parse_nfse_abrasf_single(nfse, root)


# --------------------------------------------------------------------------- #
# NFS-e Padrão Nacional (defensivo)
# --------------------------------------------------------------------------- #
def _parse_nfse_nacional(root) -> dict:
    inf = _first_el(_find_local(root, "infNFSe"), root)
    chave = _g(root, "chNFSe") or ""
    if not chave:
        chave = re.sub(r"^NFSe", "", (inf.get("Id") or "")).strip()
    chave = re.sub(r"\D", "", chave)
    if not chave:
        cnpj_em = _clean_cnpj(_g(inf, "CNPJEmit") or _g(_find_local(inf, "emit"), "CNPJ"))
        num = _g(inf, "nNFSe") or _g(inf, "nDPS") or "0"
        chave = f"NFSE-N-{cnpj_em}-{num}"

    data_iso, ano, mes = _parse_dt(_g(inf, "dhEmi") or _g(inf, "DataEmissao"))

    emit = _first_el(_find_local(inf, "emit"), _find_local(inf, "prest"))
    cnpj_emit = _clean_cnpj(_g(emit, "CNPJ") or _g(emit, "Cnpj"))
    ender_emit = _first_el(_find_local(emit, "enderNac"), _find_local(emit, "end")) if emit is not None else None

    dps = _find_local(inf, "DPS")
    inf_dps = _find_local(dps, "infDPS") if dps is not None else None
    escopo_toma = inf_dps if inf_dps is not None else inf

    tom = _first_el(
        _find_local(escopo_toma, "toma"), _find_local(inf, "toma"), _find_local(inf, "Tomador")
    )
    cnpj_dest = _clean_cnpj(_g(tom, "CNPJ") or _g(tom, "Cnpj") or _g(tom, "CPF") or _g(tom, "Cpf"))
    ender_dest = _first_el(
        _find_local(tom, "end"), _find_local(tom, "enderNac"), _find_local(tom, "enderExt")
    ) if tom is not None else None

    valor_total = _f(
        _g(inf, "vLiq") or _g(inf, "vServ") or _g(inf, "ValorLiquidoNfse")
        or _g(_find_local(inf, "valores"), "vLiq")
    )

    comp_raw = (_g(inf, "dCompet") or _g(inf_dps, "dCompet")) if inf_dps is not None else _g(inf, "dCompet")
    comp_raw = comp_raw or _g(inf, "Competencia") or _g(inf, "competencia")
    _, comp_ano, comp_mes = _parse_dt(comp_raw)
    competencia = f"{comp_ano}-{comp_mes}" if comp_ano and comp_mes else f"{ano}-{mes}"

    iss_raw = _g(escopo_toma, "tpRetISSQN") or _g(inf, "IssRetido") or _g(inf, "tribISSQN")
    iss_retido = 1 if iss_raw == "1" else (0 if iss_raw in ("2", "0") else None)

    descricao = (
        _g(escopo_toma, "xDescServ") or _g(inf, "xDescServ")
        or _g(inf, "Discriminacao") or "Serviço prestado"
    )
    codigo_serv = _g(escopo_toma, "cTribNac") or _g(inf, "cTribNac") or ""

    itens = [{
        "numero_item": 1, "codigo": codigo_serv, "descricao": descricao, "ncm": "",
        "cfop": "", "unidade": "UN", "quantidade": 1.0,
        "valor_unitario": valor_total, "valor_total": valor_total,
        "valor_desconto": 0.0, "valor_frete": 0.0, "valor_seguro": 0.0,
    }]

    return {
        "tipo": "NFSe",
        "modelo": "NFSe-N",
        "chave_acesso": chave,
        "serie": "",
        "numero": _g(inf, "nNFSe") or _g(inf, "nDPS"),
        "data_emissao": data_iso,
        "ano": ano,
        "mes": mes,
        "cnpj_emit": cnpj_emit,
        "nome_emit": _g(emit, "xNome") or _g(emit, "RazaoSocial"),
        "ie_emit": "",
        "uf_emit": _g(ender_emit, "UF") if ender_emit is not None else "",
        "cnpj_dest": cnpj_dest,
        "nome_dest": _g(tom, "xNome") or _g(tom, "RazaoSocial"),
        "ie_dest": "",
        "uf_dest": _g(ender_dest, "UF") if ender_dest is not None else "",
        "transportadora_cnpj": "",
        "transportadora_nome": "",
        "valor_total": valor_total,
        "protocolo": "",
        "iss_retido": iss_retido,
        "competencia": competencia,
        "itens": itens,
        "endereco_emit": _endereco_nac(ender_emit),
        "endereco_dest": _endereco_nac(ender_dest),
    }


# --------------------------------------------------------------------------- #
# Eventos (cancelamento / carta de correção)
# --------------------------------------------------------------------------- #
def _parse_evento(root, tipo: str) -> dict:
    chave = re.sub(r"\D", "", _g(root, "chNFe") or _g(root, "chCTe"))
    if len(chave) != 44:
        raise ValueError("Evento sem chave de acesso válida")
    return {
        "tipo": tipo,  # EventoCancelamento | EventoCCe
        "chave_acesso": chave,
        "tp_evento": _g(root, "tpEvento"),
        "data_evento": _g(root, "dhEvento"),
        "protocolo_cancelamento": _g(root, "nProt"),
        "cstat": _g(root, "cStat"),
        "justificativa": _g(root, "xJust") or _g(root, "xCorrecao"),
    }


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def parse_xml(content: bytes) -> dict:
    """Parseia um XML fiscal. Levanta ValueError se inválido/não suportado."""
    if not content:
        raise ValueError("XML vazio")
    try:
        root = fromstring(content)
    except (ParseError, DefusedXmlException) as e:
        raise ValueError(f"XML mal-formado ou inseguro: {e}") from e

    tipo = identificar_tipo(root)
    if tipo == TipoXML.NFE:
        return _parse_nfe(root)
    if tipo == TipoXML.CTE:
        return _parse_cte(root)
    if tipo == TipoXML.NFSE_ABRASF:
        return _parse_nfse_abrasf(root)
    if tipo == TipoXML.NFSE_NACIONAL:
        return _parse_nfse_nacional(root)
    if tipo == TipoXML.EVENTO_CANCELAMENTO:
        return _parse_evento(root, TipoXML.EVENTO_CANCELAMENTO)
    if tipo == TipoXML.EVENTO_CCE:
        return _parse_evento(root, TipoXML.EVENTO_CCE)
    if tipo == "EventoOutro":
        raise ValueError("Evento fiscal ignorado (não é cancelamento nem CC-e)")
    raise ValueError(f"Tipo de XML não suportado (raiz: {_local(root.tag)})")


def parse_xml_multi(content: bytes) -> list:
    """ABRASF pode trazer várias <Nfse> num arquivo. Outros tipos: lista de 1."""
    if not content:
        raise ValueError("XML vazio")
    try:
        root = fromstring(content)
    except (ParseError, DefusedXmlException) as e:
        raise ValueError(f"XML mal-formado ou inseguro: {e}") from e

    if identificar_tipo(root) != TipoXML.NFSE_ABRASF:
        return [parse_xml(content)]

    nfses = _findall_local(root, "Nfse")
    if not nfses:
        return [parse_xml(content)]

    resultados = []
    for nfse_node in nfses:
        try:
            comp = nfse_node
            for anc in root.iter():
                if _local(anc.tag) == "CompNfse" and nfse_node in list(anc.iter()):
                    comp = anc
                    break
            resultados.append(_parse_nfse_abrasf_single(nfse_node, comp))
        except Exception as e:
            resultados.append({"_erro": str(e), "tipo": "NFSe", "modelo": "NFSe-A"})
    return resultados
