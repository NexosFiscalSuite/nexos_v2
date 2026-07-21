"""Verificação do destaque de IBS/CBS — Reforma Tributária, ano-teste 2026.

ADCT art. 125 (EC 132/2023) + LC 214/2025: em 2026 as NF-e/NFC-e de emitentes
do regime normal devem DESTACAR IBS 0,1% e CBS 0,9% (fase de teste, sem
recolhimento). Optantes do Simples/MEI (CRT 1/4) estão dispensados.

Este módulo confronta o que veio nos XMLs importados:
  SEM_DESTAQUE         — nota de regime normal sem o grupo IBS/CBS (risco: o
                         emitente ainda não se adequou à NT 2025.002).
  ALIQUOTA_DIVERGENTE  — destacou, mas fora dos percentuais de teste.
  VALOR_DIVERGENTE     — alíquotas certas, mas a conta (base × alíquota) não fecha.
  TRATAMENTO_DIFERENCIADO — CST do IBS/CBS ≠ 000 (isenção, imunidade, alíquota
                         zero, diferimento, monofásica…): a operação NÃO está
                         sujeita às alíquotas de teste — zerado aqui é legítimo,
                         não é apontado como problema.
  DISPENSADO           — emitente do Simples/MEI: destaque não exigido em 2026.
  OK                   — destaque presente e correto.

A régua fina usa a tabela oficial de Classificação Tributária (SVRS/NT
2025.002) embarcada em domain/classtrib_2026.json — por cClassTrib:
  modo "padrao": alíquota esperada = teste × (1 − %redução) — inclusive as
                 reduções de 30/40/60/80% (ex.: alimentos), conferidas de fato;
  modo "zero":   isenção/imunidade/não-incidência — o destaque deve vir zerado;
  modo "livre":  fixa, uniforme, diferimento, monofásica — sem checagem
                 matemática (estruturas que o destaque padrão não descreve).
Item sem cClassTrib (ou código fora da tabela) cai no critério do CST:
só o 000 exige as alíquotas cheias de teste.

A classificação é query-time (nada persistido): mudou o XML/regra, muda o
resultado — e o backfill repara notas importadas antes desta versão.
"""
from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import Storage
from app.modules.fiscal.domain import parser as xmlparser
from app.modules.fiscal.infrastructure.models import Nota, NotaItem

_CLASSTRIB_PATH = Path(__file__).resolve().parent.parent / "domain" / "classtrib_2026.json"


@lru_cache(maxsize=1)
def tabela_classtrib() -> dict:
    """Snapshot da tabela oficial de Classificação Tributária (SVRS)."""
    return json.loads(_CLASSTRIB_PATH.read_text(encoding="utf-8"))

# Alíquotas do ano-teste (ADCT art. 125): IBS 0,1% (UF+Mun) e CBS 0,9%.
ALIQ_IBS_TESTE = Decimal("0.10")
ALIQ_CBS_TESTE = Decimal("0.90")
# Tolerâncias: percentual (arredondamento de 2 casas) e centavos por item.
TOL_PCT = Decimal("0.011")
TOL_VALOR = Decimal("0.02")

_CRT_SIMPLES = ("1", "4")          # Simples Nacional / MEI — dispensados em 2026
_MODELOS = ("55", "65")            # NF-e / NFC-e (o grupo IBSCBS é delas)
_INICIO_TESTE = "2026-01-01"
CST_INTEGRAL = "000"               # único CST que exige as alíquotas cheias de teste

OK = "OK"
SEM_DESTAQUE = "SEM_DESTAQUE"
ALIQUOTA_DIVERGENTE = "ALIQUOTA_DIVERGENTE"
VALOR_DIVERGENTE = "VALOR_DIVERGENTE"
TRATAMENTO_DIFERENCIADO = "TRATAMENTO_DIFERENCIADO"
DISPENSADO = "DISPENSADO"
_COM_PROBLEMA = (SEM_DESTAQUE, ALIQUOTA_DIVERGENTE, VALOR_DIVERGENTE)


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def regua_do_item(cst: str | None, c_class_trib: str | None) -> dict:
    """Régua esperada do item: percentuais devidos (None = sem régua percentual,
    ex.: monofásica/fixa) + a descrição oficial que justifica — alimenta o
    "veio ▸ esperado" da tela."""
    regra = tabela_classtrib().get((c_class_trib or "").strip())
    if regra is not None:
        base = {"desc": regra["desc"]}
        if regra["modo"] == "livre":
            return {**base, "p_ibs": None, "p_cbs": None}
        if regra["modo"] == "zero":
            return {**base, "p_ibs": Decimal("0"), "p_cbs": Decimal("0")}
        return {
            **base,
            "p_ibs": ALIQ_IBS_TESTE * (100 - regra["red_ibs"]) / 100,
            "p_cbs": ALIQ_CBS_TESTE * (100 - regra["red_cbs"]) / 100,
        }
    cst = (cst or "").strip()
    if cst and cst != CST_INTEGRAL:
        return {"desc": f"CST {cst} — tratamento diferenciado (sem régua percentual)",
                "p_ibs": None, "p_cbs": None}
    return {"desc": "Tributação integral — alíquotas de teste de 2026",
            "p_ibs": ALIQ_IBS_TESTE, "p_cbs": ALIQ_CBS_TESTE}


def classificar_item(
    *,
    crt_emit: str | None,
    p_ibs_uf: Decimal,
    p_ibs_mun: Decimal,
    v_ibs_uf: Decimal,
    v_ibs_mun: Decimal,
    p_cbs: Decimal,
    v_cbs: Decimal,
    v_bc: Decimal,
    cst: str | None = None,
    c_class_trib: str | None = None,
) -> str:
    """Classificação pura de um item (testável sem banco)."""
    if (crt_emit or "").strip() in _CRT_SIMPLES:
        return DISPENSADO

    p_ibs = p_ibs_uf + p_ibs_mun
    v_ibs = v_ibs_uf + v_ibs_mun
    zerado = p_ibs == 0 and p_cbs == 0 and v_ibs == 0 and v_cbs == 0

    regra = tabela_classtrib().get((c_class_trib or "").strip())
    if regra is None:
        # Sem cClassTrib (ou código fora da tabela): o CST decide. ≠ 000 é
        # tratamento próprio — zerado/diferente é legítimo, não erro.
        cst = (cst or "").strip()
        if cst and cst != CST_INTEGRAL:
            return TRATAMENTO_DIFERENCIADO
        if zerado:
            return SEM_DESTAQUE
        exp_ibs, exp_cbs = ALIQ_IBS_TESTE, ALIQ_CBS_TESTE
        reduzido = False
    elif regra["modo"] == "livre":
        # Fixa/uniforme/diferimento/monofásica: estrutura que a régua
        # percentual não descreve — registra sem apontar.
        return TRATAMENTO_DIFERENCIADO
    elif regra["modo"] == "zero":
        # Isenção/imunidade/não-incidência: o destaque DEVE vir zerado.
        return TRATAMENTO_DIFERENCIADO if zerado else ALIQUOTA_DIVERGENTE
    else:  # modo "padrao" — com ou sem redução percentual
        exp_ibs = ALIQ_IBS_TESTE * (100 - regra["red_ibs"]) / 100
        exp_cbs = ALIQ_CBS_TESTE * (100 - regra["red_cbs"]) / 100
        reduzido = regra["red_ibs"] > 0 or regra["red_cbs"] > 0
        if exp_ibs == 0 and exp_cbs == 0:      # redução de 100% = espera zero
            return TRATAMENTO_DIFERENCIADO if zerado else ALIQUOTA_DIVERGENTE
        if zerado:
            # Declarou a classificação mas não aplicou as alíquotas devidas.
            return ALIQUOTA_DIVERGENTE

    if abs(p_ibs - exp_ibs) > TOL_PCT or abs(p_cbs - exp_cbs) > TOL_PCT:
        return ALIQUOTA_DIVERGENTE

    # Matemática do destaque (só quando a base veio no XML).
    if v_bc > 0:
        esperado_ibs = v_bc * exp_ibs / 100
        esperado_cbs = v_bc * exp_cbs / 100
        if abs(v_ibs - esperado_ibs) > TOL_VALOR or abs(v_cbs - esperado_cbs) > TOL_VALOR:
            return VALOR_DIVERGENTE
    # Conforme: alíquota cheia = OK; reduzida conferida = diferenciado (conforme).
    return TRATAMENTO_DIFERENCIADO if reduzido else OK


class IbsCbsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def verificar(
        self,
        *,
        empresa_id: UUID | None = None,
        ano: str | None = None,
        mes: str | None = None,
        fluxo: str | None = None,
        apenas_status: str | None = None,
        limite_itens: int = 500,
    ) -> dict:
        n, it = Nota, NotaItem
        stmt = (
            select(
                it.id, n.empresa_id, n.chave_acesso, n.numero, n.nome_emit,
                n.cnpj_emit, n.crt_emit, n.fluxo, n.data_emissao,
                it.numero_item, it.codigo, it.descricao, it.valor_produto,
                it.v_bc_ibs_cbs, it.p_ibs_uf, it.v_ibs_uf, it.p_ibs_mun,
                it.v_ibs_mun, it.p_cbs, it.v_cbs, it.cst_ibs_cbs, it.c_class_trib,
            )
            .join(n, it.nota_id == n.id)
            .where(
                n.modelo.in_(_MODELOS),
                n.status == "ativa",
                n.data_emissao >= _INICIO_TESTE,
            )
            .order_by(n.data_emissao.desc(), n.chave_acesso, it.numero_item)
        )
        if empresa_id:
            stmt = stmt.where(n.empresa_id == empresa_id)
        if ano:
            stmt = stmt.where(n.ano == ano)
        if mes:
            stmt = stmt.where(n.mes == mes)
        if fluxo:
            stmt = stmt.where(n.fluxo == fluxo)

        rows = (await self.session.execute(stmt)).all()

        resumo: dict[str, dict] = {}
        emitentes: dict[str, dict] = {}
        problemas: list[dict] = []
        for r in rows:
            status = classificar_item(
                crt_emit=r.crt_emit,
                p_ibs_uf=_d(r.p_ibs_uf), p_ibs_mun=_d(r.p_ibs_mun),
                v_ibs_uf=_d(r.v_ibs_uf), v_ibs_mun=_d(r.v_ibs_mun),
                p_cbs=_d(r.p_cbs), v_cbs=_d(r.v_cbs),
                v_bc=_d(r.v_bc_ibs_cbs),
                cst=r.cst_ibs_cbs, c_class_trib=r.c_class_trib,
            )
            agg = resumo.setdefault(status, {"itens": 0, "valor": 0.0})
            agg["itens"] += 1
            agg["valor"] += float(r.valor_produto or 0)

            # Ranking de emitentes: sempre e somente pendências reais.
            if status in _COM_PROBLEMA:
                chave_emit = r.cnpj_emit or "sem-cnpj"
                e = emitentes.setdefault(chave_emit, {
                    "cnpj": r.cnpj_emit, "nome": r.nome_emit,
                    "itens": 0, "valor": 0.0, "status": {},
                })
                e["itens"] += 1
                e["valor"] += float(r.valor_produto or 0)
                e["status"][status] = e["status"].get(status, 0) + 1

            # Lista de itens: por padrão só as pendências (é o que alimenta a
            # carta); com apenas_status, a situação pedida — inclusive OK e
            # dispensados, para a tela não ficar cega sobre o que passou.
            incluir = (status == apenas_status) if apenas_status \
                else status in _COM_PROBLEMA
            if incluir:
                if len(problemas) < limite_itens:
                    regua = regua_do_item(r.cst_ibs_cbs, r.c_class_trib)
                    if status == DISPENSADO:
                        regua = {
                            "desc": (f"Emitente do Simples Nacional/MEI (CRT "
                                     f"{r.crt_emit}) — dispensado do destaque de "
                                     "IBS/CBS no ano-teste de 2026."),
                            "p_ibs": None, "p_cbs": None,
                        }
                    v_bc = _d(r.v_bc_ibs_cbs)
                    base_esp = v_bc if v_bc > 0 else _d(r.valor_produto)
                    problemas.append({
                        "status": status,
                        "chave_acesso": r.chave_acesso,
                        "numero_nota": r.numero,
                        "fluxo": r.fluxo,
                        "data_emissao": r.data_emissao,
                        "emitente": r.nome_emit,
                        "cnpj_emit": r.cnpj_emit,
                        "numero_item": r.numero_item,
                        "codigo": r.codigo,
                        "descricao": r.descricao,
                        "valor_produto": float(r.valor_produto or 0),
                        "v_bc_ibs_cbs": float(r.v_bc_ibs_cbs or 0),
                        "p_ibs": float(_d(r.p_ibs_uf) + _d(r.p_ibs_mun)),
                        "v_ibs": float(_d(r.v_ibs_uf) + _d(r.v_ibs_mun)),
                        "p_cbs": float(r.p_cbs or 0),
                        "v_cbs": float(r.v_cbs or 0),
                        # "veio ▸ esperado": régua devida ao CST/cClassTrib do item
                        "cst": r.cst_ibs_cbs,
                        "c_class_trib": r.c_class_trib,
                        "regua_desc": regua["desc"],
                        "p_ibs_esperado": None if regua["p_ibs"] is None else float(regua["p_ibs"]),
                        "p_cbs_esperado": None if regua["p_cbs"] is None else float(regua["p_cbs"]),
                        "v_ibs_esperado": None if regua["p_ibs"] is None
                            else float(base_esp * regua["p_ibs"] / 100),
                        "v_cbs_esperado": None if regua["p_cbs"] is None
                            else float(base_esp * regua["p_cbs"] / 100),
                    })

        ranking = sorted(emitentes.values(), key=lambda e: e["valor"], reverse=True)
        total_itens = sum(a["itens"] for a in resumo.values())
        conformes = (
            resumo.get(OK, {}).get("itens", 0)
            + resumo.get(DISPENSADO, {}).get("itens", 0)
            + resumo.get(TRATAMENTO_DIFERENCIADO, {}).get("itens", 0)
        )
        return {
            "aliquotas_teste": {"ibs": float(ALIQ_IBS_TESTE), "cbs": float(ALIQ_CBS_TESTE)},
            "total_itens": total_itens,
            "pct_conforme": round(conformes / total_itens * 100, 1) if total_itens else 100.0,
            "resumo": resumo,
            "ranking_emitentes": ranking[:50],
            "itens": problemas,
        }

    async def reprocessar(
        self,
        storage: Storage,
        *,
        empresa_id: UUID | None = None,
        ano: str | None = None,
        mes: str | None = None,
    ) -> dict:
        """Backfill: re-lê os XMLs armazenados de notas importadas ANTES desta
        versão (colunas IBS/CBS vazias) e preenche os campos dos itens.
        Idempotente — rodar de novo apenas reescreve os mesmos valores."""
        n = Nota
        stmt = select(n).where(
            n.modelo.in_(_MODELOS),
            n.data_emissao >= _INICIO_TESTE,
            n.storage_key.isnot(None),
        )
        if empresa_id:
            stmt = stmt.where(n.empresa_id == empresa_id)
        if ano:
            stmt = stmt.where(n.ano == ano)
        if mes:
            stmt = stmt.where(n.mes == mes)
        notas = (await self.session.execute(stmt)).scalars().all()

        atualizadas = falhas = 0
        for nota in notas:
            try:
                parsed = xmlparser.parse_xml(storage.get(nota.storage_key))
            except Exception:  # noqa: BLE001 — XML sumido/ilegível não derruba o lote
                falhas += 1
                continue
            por_numero = {i["numero_item"]: i for i in parsed.get("itens", [])}
            itens_db = (await self.session.execute(
                select(NotaItem).where(NotaItem.nota_id == nota.id)
            )).scalars().all()
            for item in itens_db:
                p = por_numero.get(item.numero_item)
                if p is None:
                    continue
                item.cst_ibs_cbs = p.get("cst_ibs_cbs")
                item.c_class_trib = p.get("c_class_trib")
                item.v_bc_ibs_cbs = _d(p.get("v_bc_ibs_cbs"))
                item.p_ibs_uf = _d(p.get("p_ibs_uf"))
                item.v_ibs_uf = _d(p.get("v_ibs_uf"))
                item.p_ibs_mun = _d(p.get("p_ibs_mun"))
                item.v_ibs_mun = _d(p.get("v_ibs_mun"))
                item.p_cbs = _d(p.get("p_cbs"))
                item.v_cbs = _d(p.get("v_cbs"))
            atualizadas += 1
        await self.session.flush()
        return {"notas_reprocessadas": atualizadas, "falhas_leitura": falhas}
