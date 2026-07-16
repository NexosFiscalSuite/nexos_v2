"""Verificação do destaque de IBS/CBS — Reforma Tributária, ano-teste 2026.

ADCT art. 125 (EC 132/2023) + LC 214/2025: em 2026 as NF-e/NFC-e de emitentes
do regime normal devem DESTACAR IBS 0,1% e CBS 0,9% (fase de teste, sem
recolhimento). Optantes do Simples/MEI (CRT 1/4) estão dispensados.

Este módulo confronta o que veio nos XMLs importados:
  SEM_DESTAQUE         — nota de regime normal sem o grupo IBS/CBS (risco: o
                         emitente ainda não se adequou à NT 2025.002).
  ALIQUOTA_DIVERGENTE  — destacou, mas fora dos percentuais de teste.
  VALOR_DIVERGENTE     — alíquotas certas, mas a conta (base × alíquota) não fecha.
  DISPENSADO           — emitente do Simples/MEI: destaque não exigido em 2026.
  OK                   — destaque presente e correto.

A classificação é query-time (nada persistido): mudou o XML/regra, muda o
resultado — e o backfill repara notas importadas antes desta versão.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import Storage
from app.modules.fiscal.domain import parser as xmlparser
from app.modules.fiscal.infrastructure.models import Nota, NotaItem

# Alíquotas do ano-teste (ADCT art. 125): IBS 0,1% (UF+Mun) e CBS 0,9%.
ALIQ_IBS_TESTE = Decimal("0.10")
ALIQ_CBS_TESTE = Decimal("0.90")
# Tolerâncias: percentual (arredondamento de 2 casas) e centavos por item.
TOL_PCT = Decimal("0.011")
TOL_VALOR = Decimal("0.02")

_CRT_SIMPLES = ("1", "4")          # Simples Nacional / MEI — dispensados em 2026
_MODELOS = ("55", "65")            # NF-e / NFC-e (o grupo IBSCBS é delas)
_INICIO_TESTE = "2026-01-01"

OK = "OK"
SEM_DESTAQUE = "SEM_DESTAQUE"
ALIQUOTA_DIVERGENTE = "ALIQUOTA_DIVERGENTE"
VALOR_DIVERGENTE = "VALOR_DIVERGENTE"
DISPENSADO = "DISPENSADO"


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


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
) -> str:
    """Classificação pura de um item (testável sem banco)."""
    if (crt_emit or "").strip() in _CRT_SIMPLES:
        return DISPENSADO

    p_ibs = p_ibs_uf + p_ibs_mun
    v_ibs = v_ibs_uf + v_ibs_mun
    if p_ibs == 0 and p_cbs == 0 and v_ibs == 0 and v_cbs == 0:
        return SEM_DESTAQUE

    if abs(p_ibs - ALIQ_IBS_TESTE) > TOL_PCT or abs(p_cbs - ALIQ_CBS_TESTE) > TOL_PCT:
        return ALIQUOTA_DIVERGENTE

    # Matemática do destaque (só quando a base veio no XML).
    if v_bc > 0:
        esperado_ibs = v_bc * ALIQ_IBS_TESTE / 100
        esperado_cbs = v_bc * ALIQ_CBS_TESTE / 100
        if abs(v_ibs - esperado_ibs) > TOL_VALOR or abs(v_cbs - esperado_cbs) > TOL_VALOR:
            return VALOR_DIVERGENTE
    return OK


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
        limite_itens: int = 500,
    ) -> dict:
        n, it = Nota, NotaItem
        stmt = (
            select(
                it.id, n.empresa_id, n.chave_acesso, n.numero, n.nome_emit,
                n.cnpj_emit, n.crt_emit, n.fluxo, n.data_emissao,
                it.numero_item, it.descricao, it.valor_produto,
                it.v_bc_ibs_cbs, it.p_ibs_uf, it.v_ibs_uf, it.p_ibs_mun,
                it.v_ibs_mun, it.p_cbs, it.v_cbs,
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
            )
            agg = resumo.setdefault(status, {"itens": 0, "valor": 0.0})
            agg["itens"] += 1
            agg["valor"] += float(r.valor_produto or 0)

            if status in (SEM_DESTAQUE, ALIQUOTA_DIVERGENTE, VALOR_DIVERGENTE):
                chave_emit = r.cnpj_emit or "sem-cnpj"
                e = emitentes.setdefault(chave_emit, {
                    "cnpj": r.cnpj_emit, "nome": r.nome_emit,
                    "itens": 0, "valor": 0.0, "status": {},
                })
                e["itens"] += 1
                e["valor"] += float(r.valor_produto or 0)
                e["status"][status] = e["status"].get(status, 0) + 1

                if len(problemas) < limite_itens:
                    problemas.append({
                        "status": status,
                        "chave_acesso": r.chave_acesso,
                        "numero_nota": r.numero,
                        "fluxo": r.fluxo,
                        "data_emissao": r.data_emissao,
                        "emitente": r.nome_emit,
                        "cnpj_emit": r.cnpj_emit,
                        "numero_item": r.numero_item,
                        "descricao": r.descricao,
                        "valor_produto": float(r.valor_produto or 0),
                        "v_bc_ibs_cbs": float(r.v_bc_ibs_cbs or 0),
                        "p_ibs": float(_d(r.p_ibs_uf) + _d(r.p_ibs_mun)),
                        "v_ibs": float(_d(r.v_ibs_uf) + _d(r.v_ibs_mun)),
                        "p_cbs": float(r.p_cbs or 0),
                        "v_cbs": float(r.v_cbs or 0),
                    })

        ranking = sorted(emitentes.values(), key=lambda e: e["valor"], reverse=True)
        total_itens = sum(a["itens"] for a in resumo.values())
        conformes = resumo.get(OK, {}).get("itens", 0) + resumo.get(DISPENSADO, {}).get("itens", 0)
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
