"""Extração de valores do XML por path de local-names (ignora namespace).

Resolve cada segmento buscando o 1º DESCENDENTE com aquele local-name — assim os
grupos de imposto (ICMS00/ICMSSN…, PISAliq…) são resolvidos sem fixar a variante.
"""
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException

# defusedxml: bloqueia XXE / expansão de entidades em XML de upload.
from defusedxml.ElementTree import fromstring

from app.modules.reporting.domain import tags as tags_mod
from app.modules.reporting.domain.tags import DERIVE, TAGS


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _find_desc(el, name: str):
    if el is None:
        return None
    for c in el.iter():
        if c is not el and _local(c.tag) == name:
            return c
    return None


def _resolve(el, path: list[str]) -> str:
    cur = el
    for seg in path:
        cur = _find_desc(cur, seg)
        if cur is None:
            return ""
    return (cur.text or "").strip()


def parse(xml_bytes: bytes):
    """Parseia o XML e retorna o elemento raiz (ou None se inválido)."""
    try:
        return fromstring(xml_bytes)
    except (ParseError, DefusedXmlException):
        return None


def find_inf(root):
    """Retorna o elemento <infNFe> (ou None se não for NF-e)."""
    if root is None:
        return None
    if _local(root.tag) == "infNFe":
        return root
    return _find_desc(root, "infNFe")


def inf_nfe(xml_bytes: bytes):
    """Compat: retorna <infNFe> direto do XML."""
    return find_inf(parse(xml_bytes))


def _derive(key: str, raw: str) -> str:
    if DERIVE.get(key) == "situacao":
        return tags_mod.situacao(raw)
    return raw


def extract_capa(root, inf, keys: list[str]) -> dict:
    """Valores das tags de capa. protNFe vem da raiz (fora de infNFe)."""
    out = {}
    for k in keys:
        t = TAGS.get(k)
        if not t:
            out[k] = ""
            continue
        base = root if (t["path"] and t["path"][0] == "protNFe") else inf
        out[k] = _derive(k, _resolve(base, t["path"]) if base is not None else "")
    return out


def extract_itens(inf, keys: list[str]) -> list[dict]:
    """Uma linha por <det>; valores das tags de item solicitadas."""
    if inf is None:
        return []
    dets = [c for c in inf.iter() if _local(c.tag) == "det"]
    linhas = []
    for det in dets:
        nitem = det.get("nItem")
        row = {"_nItem": int(nitem) if (nitem or "").isdigit() else (len(linhas) + 1)}
        for k in keys:
            t = TAGS.get(k)
            row[k] = _resolve(det, t["path"]) if t else ""
        linhas.append(row)
    return linhas
