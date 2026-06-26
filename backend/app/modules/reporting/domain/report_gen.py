"""Motor do gerador de relatórios avançado.

Lê os XMLs, extrai as tags MOC selecionadas (capa = 1 linha/NF; itens = 1 linha/
item), aplica:
  - colunas condicionais (descarta tag vazia em TODOS os XMLs);
  - colunas calculadas de auditoria (Valor Líquido, Total Calculado, Diferença);
  - coluna Finalidade (Tipo SPED do item; "Múltiplas Finalidades" na capa);
  - motor de vedação de crédito (regime × finalidade) -> zera impostos indevidos
    e gera linhas na aba de Alertas com base legal.

Entrada: notas_dados = [{ "nota": Nota, "tipos": {nItem: tipo_sped}, "xml": bytes|None }]
Saída: estrutura consumida por excel.build_excel.
"""
from app.modules.reporting.domain import extract
from app.modules.reporting.domain.tags import TAGS

USO_CONSUMO = "Material de Uso e Consumo"

# Tags de totais da capa necessárias às colunas calculadas (extraídas sempre).
CALC_KEYS = ["vProd", "vFrete", "vSeg", "vOutro", "vDesc", "vST", "vIPI", "vNF"]
# Tags de item extraídas sempre (vedação + colunas calculadas dos itens).
EXTRA_ITEM_KEYS = [
    "it_vProd", "it_vFrete", "it_vSeg", "it_vOutro", "it_vDesc", "it_vICMSST",
    "it_vBC", "it_pICMS", "it_vICMS", "it_IPI_vIPI", "it_PIS_vPIS", "it_COFINS_vCOFINS",
]

# Colunas calculadas como FÓRMULAS do Excel. Cada operando é uma tag (vira
# referência à célula real daquela coluna, onde quer que ela esteja; se a coluna
# não estiver no relatório, vira o número literal) ou "@id" (outra coluna calc).
#   spec "soma": termos [(sinal, operando)]   |   spec "prod": a*b/div
CAPA_CALC = [
    ("liq", "Valor Líquido (Itens)", {"tipo": "soma", "termos": [
        ("+", "vProd"), ("+", "vFrete"), ("+", "vSeg"), ("+", "vOutro"), ("-", "vDesc")]}),
    ("total", "Valor Total Nota", {"tipo": "soma", "termos": [
        ("+", "@liq"), ("+", "vST"), ("+", "vIPI")]}),
    ("dif", "Diferença (NF x Calc)", {"tipo": "soma", "termos": [
        ("+", "vNF"), ("-", "@total")]}),
]
ITEM_CALC = [
    ("liq", "Valor Líquido (Item)", {"tipo": "soma", "termos": [
        ("+", "it_vProd"), ("+", "it_vFrete"), ("+", "it_vSeg"), ("+", "it_vOutro"),
        ("-", "it_vDesc"), ("+", "it_vICMSST")]}),
    ("apurado", "ICMS Apurado", {"tipo": "prod", "a": "it_vBC", "b": "it_pICMS", "div": 100}),
    ("dificms", "Diferença ICMS", {"tipo": "soma", "termos": [
        ("+", "it_vICMS"), ("-", "@apurado")]}),
]

BASE_ICMS = "LC 87/1996 (Lei Kandir), Art. 33, I, c/c LC 171/2019."
BASE_PISCOFINS_REAL = "Leis 10.637/2002 e 10.833/2003 (Art. 3º); IN RFB 2.121/2022; STJ REsp 1.221.170/PR."


def _num(s):
    if s is None or s == "":
        return None
    try:
        return float(str(s).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _presente(key: str, v) -> bool:
    """Coluna condicional: financeira só "presente" se houver valor != 0;
    demais, basta um texto não vazio (ex.: CEST ausente em todos -> some)."""
    if v in (None, ""):
        return False
    if TAGS[key]["money"]:
        return _num(v) not in (None, 0)
    return True


def _is_real(regime: str) -> bool:
    return "real" in (regime or "").lower()


def _is_presumido(regime: str) -> bool:
    return "presumido" in (regime or "").lower()


def _alerta(nota, item, campo, valor, base):
    return {
        "numero": nota.numero, "serie": nota.serie, "chave": nota.chave_acesso,
        "emitente": nota.nome_emit, "item": item,
        "motivo": f"Crédito de {campo} vedado para Uso e Consumo",
        "valor_xml": valor, "valor_corrigido": 0.0,
        "acao": f"Zerar {campo}", "base_legal": base,
    }


def gerar(config: dict, notas_dados: list, regime: str) -> dict:
    capa_all = list(config.get("capa", []))
    item_all = list(config.get("itens", []))
    # auditoria "legada" (campo separado) -> colunas de auditoria no fim da capa
    capa_all += [{"audit": True, "label": str(n)} for n in config.get("auditoria", []) if str(n).strip()]
    capa_tags = [c for c in capa_all if c.get("tag") in TAGS]
    item_tags = [c for c in item_all if c.get("tag") in TAGS]
    # Herança capa→item: tags de CAPA pedidas no relatório de ITENS (Identificação,
    # Emitente, Destinatário…) são extraídas da nota e REPETIDAS em cada linha de
    # produto — permite filtros/tabelas dinâmicas no Excel.
    item_capa_keys = [c["tag"] for c in item_tags if TAGS[c["tag"]]["escopo"] == "capa"]
    item_own_keys = [c["tag"] for c in item_tags if TAGS[c["tag"]]["escopo"] == "item"]
    inc_finalidade = config.get("finalidade", True)
    inc_calc = config.get("calculos", True)

    capa_rows, item_rows, alertas = [], [], []
    # presença por tag (coluna condicional)
    capa_seen = {c["tag"]: False for c in capa_tags}
    item_seen = {c["tag"]: False for c in item_tags}

    for nd in notas_dados:
        nota = nd["nota"]
        tipos = nd.get("tipos", {})
        root = extract.parse(nd.get("xml") or b"")
        inf = extract.find_inf(root)

        capa_keys = list({*[c["tag"] for c in capa_tags], *CALC_KEYS, *item_capa_keys})
        capa_vals = extract.extract_capa(root, inf, capa_keys) if inf is not None else {}
        for k, v in capa_vals.items():
            if k in capa_seen and _presente(k, v):
                capa_seen[k] = True

        # Finalidade da capa: distinta entre os itens
        fins = {t for t in tipos.values() if t}
        finalidade_capa = "Múltiplas Finalidades" if len(fins) > 1 else (next(iter(fins), "") if fins else "")

        # Itens: tags próprias do item + tags "extra" (vedação e cálculos), sempre
        # extraídas. As tags de capa pedidas vêm de capa_vals (injetadas por linha).
        itens_x = extract.extract_itens(inf, item_own_keys) if inf is not None else []
        extra_map = {r["_nItem"]: r for r in (extract.extract_itens(inf, EXTRA_ITEM_KEYS) if inf is not None else [])}

        for r in itens_x:
            ni = r["_nItem"]
            fin = tipos.get(ni, "")
            vals = dict(r)
            # Injeta os dados da nota-pai (chave, CNPJ emit, data…) na linha do item.
            for k in item_capa_keys:
                vals[k] = capa_vals.get(k, "")
            extra = extra_map.get(ni, {})
            for k in [c["tag"] for c in item_tags]:
                if _presente(k, vals.get(k)):
                    item_seen[k] = True

            # ── Motor de vedação ──
            if fin == USO_CONSUMO and (_is_real(regime) or _is_presumido(regime)):
                vicms = _num(extra.get("it_vICMS"))
                if vicms:
                    alertas.append(_alerta(nota, ni, "ICMS", vicms, BASE_ICMS))
                    if "it_vICMS" in vals:
                        vals["it_vICMS"] = "0.00"
                if _is_real(regime):
                    vpis = _num(extra.get("it_PIS_vPIS"))
                    vcof = _num(extra.get("it_COFINS_vCOFINS"))
                    if vpis:
                        alertas.append(_alerta(nota, ni, "PIS", vpis, BASE_PISCOFINS_REAL))
                        if "it_PIS_vPIS" in vals:
                            vals["it_PIS_vPIS"] = "0.00"
                    if vcof:
                        alertas.append(_alerta(nota, ni, "COFINS", vcof, BASE_PISCOFINS_REAL))
                        if "it_COFINS_vCOFINS" in vals:
                            vals["it_COFINS_vCOFINS"] = "0.00"

            item_rows.append({"_tags": vals, "_finalidade": fin, "_extra": extra, "_nota": nota})

        capa_rows.append({"_tags": capa_vals, "_finalidade": finalidade_capa, "_nota": nota})

    # ── Monta colunas finais: mantém a ORDEM escolhida (inclusive auditoria),
    # descartando só as tags de dados vazias em todos os XMLs (condicional). ──
    def _keep(cols_all, seen):
        return [c for c in cols_all
                if c.get("audit") or (c.get("tag") in TAGS and seen.get(c["tag"]))]

    capa_cols = _keep(capa_all, capa_seen)
    item_cols = _keep(item_all, item_seen)

    calc_list = CAPA_CALC if inc_calc else []
    item_calc_list = ITEM_CALC if inc_calc else []

    def montar(cols, rows, calc_list, lit_key, lit_keys):
        out_cols = []
        for c in cols:
            if c.get("audit"):
                out_cols.append({"label": c.get("label") or "Auditoria", "tag": "_audit", "money": False, "audit": True, "grupo": "_audit"})
            else:
                t = c["tag"]
                out_cols.append({"label": c.get("label") or TAGS[t]["label"], "tag": t, "money": TAGS[t]["money"], "grupo": TAGS[t]["grupo"]})
        if inc_finalidade:
            out_cols.append({"label": "Finalidade", "tag": "_finalidade", "money": False, "grupo": "_finalidade"})
        for cid, label, spec in calc_list:
            out_cols.append({"label": label, "tag": "_calc", "money": True, "grupo": "_calc",
                             "calc_id": cid, "calc_spec": spec})
        out_rows, out_lits = [], []
        for r in rows:
            line = []
            for c in cols:
                if c.get("audit"):
                    line.append("")
                else:
                    t = c["tag"]
                    v = r["_tags"].get(t, "")
                    line.append(_num(v) if TAGS[t]["money"] else v)
            if inc_finalidade:
                line.append(r["_finalidade"])
            out_rows.append(line)
            # literais dos operandos (fallback p/ fórmula quando a coluna não está no relatório)
            src = r.get(lit_key, {})
            out_lits.append({k: _f(src.get(k)) for k in lit_keys})
        return {"cols": out_cols, "rows": out_rows, "literals": out_lits}

    capa = montar(capa_cols, capa_rows, calc_list, "_tags", CALC_KEYS)
    itens = montar(item_cols, item_rows, item_calc_list, "_extra", EXTRA_ITEM_KEYS)

    alerta_pack = None
    if alertas:
        alerta_pack = {
            "cols": ["Número", "Série", "Chave", "Emitente", "Item", "Motivo",
                     "Valor XML", "Valor Corrigido", "Ação Sugerida", "Base Legal"],
            "rows": [[a["numero"], a["serie"], a["chave"], a["emitente"], a["item"],
                      a["motivo"], a["valor_xml"], a["valor_corrigido"], a["acao"], a["base_legal"]]
                     for a in alertas],
        }

    return {
        "capa": capa, "itens": itens,
        "totais": bool(config.get("totais", False)),
        "alertas": alerta_pack,
        "total_notas": len(capa_rows),
    }


def _f(v) -> float:
    """Número (0.0 se ausente/inválido) — usado nos literais de fórmula."""
    n = _num(v)
    return n if n is not None else 0.0
