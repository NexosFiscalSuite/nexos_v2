"""Relatório de cobertura das matrizes fiscais — curadoria dirigida pelos dados.

Responde: "dos NCM×CEST×UF que a carteira realmente movimenta, quais o motor
consegue auditar?" Agrupa os itens já importados, avalia cada grupo contra as
matrizes vigentes e ordena pelo VALOR financeiro — é a fila de curadoria: o que
está no topo sem cobertura é o que mais gera NAO_AUDITAVEL (ou TN silencioso).

Status por grupo (do mais grave ao coberto):
  SEM_ENQUADRAMENTO — sem linha na matriz: o motor assume TN em silêncio (gap real).
  SEM_ALIQUOTA      — enquadrado ST, mas a UF não tem alíquota vigente (trava tudo).
  ST_SEM_MVA        — enquadrado ST sem MVA: modBCST=4 vira NAO_AUDITAVEL.
  TN                — enquadrado como Tributação Normal (fora do motor, por decisão).
  OK                — auditável de ponta a ponta.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizMva,
)
from app.modules.fiscal.infrastructure.models import Nota, NotaItem
from app.shared.domain.value_objects import only_digits

_Vigencias = list[tuple[date, date | None, str | None]]


def _candidatos_ncm(ncm: str) -> list[str]:
    n = only_digits(ncm)
    vistos: list[str] = []
    for c in (n, n[:6], n[:4]):
        if c and c not in vistos:
            vistos.append(c)
    return vistos


def _vigente(linhas: _Vigencias | None, data: date) -> tuple[bool, str | None]:
    """(há linha vigente na data?, payload da primeira que casa)."""
    for inicio, fim, payload in linhas or ():
        if inicio <= data and (fim is None or data <= fim):
            return True, payload
    return False, None


def _data_ref(data_emissao: str | None) -> date:
    """Data de referência do grupo (emissão mais recente); ilegível → hoje."""
    try:
        return date.fromisoformat((data_emissao or "")[:10])
    except ValueError:
        return date.today()


class CoberturaService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def cobertura(
        self,
        *,
        empresa_id: UUID | None = None,
        uf: str | None = None,
        ano: str | None = None,
        mes: str | None = None,
        limite: int = 200,
    ) -> dict:
        grupos = await self._agrupar_itens(empresa_id, uf, ano, mes)
        if not grupos:
            return {"resumo": {"grupos": 0, "valor_total": 0.0, "pct_valor_coberto": 100.0,
                               "por_status": {}}, "grupos": []}

        ufs = {g["uf"] for g in grupos}
        enq_map = await self._mapa_enquadramento(ufs)
        mva_map = await self._mapa_mva(ufs)
        aliq_map = await self._mapa_aliquota(ufs)

        for g in grupos:
            g["status"], g["regime"] = self._classificar(g, enq_map, mva_map, aliq_map)

        grupos.sort(key=lambda g: g["valor"], reverse=True)
        return {"resumo": self._resumo(grupos), "grupos": grupos[:limite]}

    # ── agregação da carteira ────────────────────────────────────────────────
    async def _agrupar_itens(self, empresa_id, uf, ano, mes) -> list[dict]:
        n, it = Nota, NotaItem
        stmt = (
            select(
                n.uf_dest, it.ncm, it.cest,
                func.count(it.id),
                func.coalesce(func.sum(it.valor_produto), 0),
                func.max(n.data_emissao),
            )
            .join(n, it.nota_id == n.id)
            .where(
                n.fluxo.in_(("entrada", "saida")), n.status == "ativa",
                it.ncm.isnot(None), it.ncm != "",
                n.uf_dest.isnot(None), n.uf_dest != "",
            )
            .group_by(n.uf_dest, it.ncm, it.cest)
        )
        if empresa_id:
            stmt = stmt.where(n.empresa_id == empresa_id)
        if uf:
            stmt = stmt.where(n.uf_dest == uf.upper())
        if ano:
            stmt = stmt.where(n.ano == ano)
        if mes:
            stmt = stmt.where(n.mes == mes)

        return [
            {
                "uf": (r[0] or "").upper(),
                "ncm": only_digits(r[1]),
                "cest": only_digits(r[2] or ""),
                "itens": int(r[3]),
                "valor": float(r[4] or 0),
                "data_ref": _data_ref(r[5]).isoformat(),
            }
            for r in (await self.session.execute(stmt)).all()
        ]

    # ── snapshots das matrizes (globais, com vigência preservada) ────────────
    async def _mapa_enquadramento(self, ufs) -> dict:
        rows = (await self.session.execute(
            select(MatrizEnquadramentoSt).where(MatrizEnquadramentoSt.uf_destino.in_(ufs))
        )).scalars()
        mapa: dict[tuple[str, str, str], _Vigencias] = {}
        for r in rows:
            mapa.setdefault((r.uf_destino, r.ncm, r.cest), []).append(
                (r.data_inicio_vigencia, r.data_fim_vigencia, r.regime)
            )
        return mapa

    async def _mapa_mva(self, ufs) -> dict:
        rows = (await self.session.execute(
            select(MatrizMva).where(MatrizMva.uf_destino.in_(ufs))
        )).scalars()
        mapa: dict[tuple[str, str, str], _Vigencias] = {}
        for r in rows:
            mapa.setdefault((r.uf_destino, r.ncm, r.cest), []).append(
                (r.data_inicio_vigencia, r.data_fim_vigencia, None)
            )
        return mapa

    async def _mapa_aliquota(self, ufs) -> dict:
        rows = (await self.session.execute(
            select(MatrizAliquota).where(MatrizAliquota.uf_destino.in_(ufs))
        )).scalars()
        mapa: dict[str, _Vigencias] = {}
        for r in rows:
            mapa.setdefault(r.uf_destino, []).append(
                (r.data_inicio_vigencia, r.data_fim_vigencia, None)
            )
        return mapa

    # ── classificação (espelha o portão do motor: fallback NCM 8→6→4) ───────
    def _classificar(self, g: dict, enq_map, mva_map, aliq_map) -> tuple[str, str | None]:
        data = date.fromisoformat(g["data_ref"])
        uf, cest = g["uf"], g["cest"]

        regime = None
        for c in _candidatos_ncm(g["ncm"]):
            achou, payload = _vigente(enq_map.get((uf, c, cest)), data)
            if achou:
                regime = payload
                break
        if regime is None:
            return "SEM_ENQUADRAMENTO", None
        if regime == "TN":
            return "TN", regime

        if not _vigente(aliq_map.get(uf), data)[0]:
            return "SEM_ALIQUOTA", regime

        tem_mva = any(
            _vigente(mva_map.get((uf, c, cest)), data)[0] for c in _candidatos_ncm(g["ncm"])
        )
        if not tem_mva:
            return "ST_SEM_MVA", regime
        return "OK", regime

    @staticmethod
    def _resumo(grupos: list[dict]) -> dict:
        por_status: dict[str, dict] = {}
        total = Decimal("0")
        coberto = Decimal("0")
        for g in grupos:
            s = por_status.setdefault(g["status"], {"grupos": 0, "valor": 0.0})
            s["grupos"] += 1
            s["valor"] += g["valor"]
            valor = Decimal(str(g["valor"]))
            total += valor
            if g["status"] in ("OK", "TN"):
                coberto += valor
        pct = float(coberto / total * 100) if total else 100.0
        return {
            "grupos": len(grupos),
            "valor_total": float(total),
            "pct_valor_coberto": round(pct, 1),
            "por_status": por_status,
        }
