"""Classificação de fluxo da nota (portado da lógica do upload do V1).

A partir do CNPJ/CPF da empresa-cliente e dos documentos do XML, decide:
  - entrada  : empresa é destinatária (NF-e/NFC-e) ou tomadora de serviço —
               ou emitente de nota de ENTRADA (tpNF=0: compra de produtor
               rural, importação, retorno)
  - saida    : empresa é emitente (NF-e/NFC-e) — ou está no destinatário de
               nota de entrada emitida pelo comprador (a venda é dela)
  - servico  : NFS-e em que a empresa é a prestadora
  - cte      : CT-e em que a empresa é a tomadora

Levanta FlowRejected quando a nota não pertence à empresa selecionada.
"""
import re

FLUXOS = ("entrada", "saida", "servico", "cte")


class FlowRejected(Exception):
    """A nota não pertence à empresa (nem emitente, nem destinatária/tomadora)."""


def _clean(c: str) -> str:
    return re.sub(r"\D", "", c or "")


def classificar_fluxo(parsed: dict, cnpj_empresa: str) -> str:
    cnpj_emp = _clean(cnpj_empresa)
    cnpj_emit = _clean(parsed.get("cnpj_emit"))
    cnpj_dest = _clean(parsed.get("cnpj_dest"))
    tipo = parsed.get("tipo")

    if tipo == "CTe":
        if cnpj_dest == cnpj_emp:
            return "cte"
        raise FlowRejected("CT-e em que a empresa selecionada não é a tomadora.")

    if tipo == "NFSe":
        if cnpj_emit == cnpj_emp:
            return "servico"
        if cnpj_dest == cnpj_emp:
            return "entrada"  # serviço tomado
        raise FlowRejected("NFS-e em que a empresa não é prestadora nem tomadora.")

    # NF-e / NFC-e. O documento diz DE QUEM é a nota; o tpNF (0=entrada,
    # 1=saída, sempre do ponto de vista do emitente) diz o SENTIDO econômico.
    # Sem tpNF vale o padrão: emitente vende, destinatário compra. Com tpNF=0
    # inverte — nota de ENTRADA emitida pelo comprador (compra de produtor
    # rural, importação, retorno): quem está no destinatário é o remetente da
    # mercadoria, ou seja, fez a venda.
    tp_nf = (parsed.get("tp_nf") or "").strip()
    if cnpj_emit == cnpj_emp:
        return "entrada" if tp_nf == "0" else "saida"
    if cnpj_dest == cnpj_emp:
        return "saida" if tp_nf == "0" else "entrada"
    raise FlowRejected("Nota em que a empresa não é emitente nem destinatária.")
