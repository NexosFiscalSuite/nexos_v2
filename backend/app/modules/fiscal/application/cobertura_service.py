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

`lacunas_mva` é a versão acionável disso para UMA matriz: os pares
NCM×CEST×origem→destino que a carteira movimenta e a matriz de MVA não cobre,
ordenados por dinheiro. A mesma lista sai em CSV JÁ no layout do importador de
matrizes, com a coluna `mva_original` VAZIA — o sistema diz onde falta, quem
diz quanto é a fonte oficial (nunca o robô, nunca uma estimativa).
"""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from math import ceil
from uuid import UUID

from sqlalchemy import func, null, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizMva,
)
from app.modules.fiscal.infrastructure.models import Nota, NotaItem
from app.shared.domain.uf import CURINGA_UF
from app.shared.domain.value_objects import only_digits

_Vigencias = list[tuple[date, date | None, str | None]]

#: Cabeçalho do CSV de carga da matriz de MVA (mesma ordem de MatrizMvaCreate).
#: O relatório de lacunas devolve exatamente estas colunas para que o arquivo
#: baixado suba de volta pelo "Importar planilha" sem edição de layout.
COLUNAS_CSV_MVA = (
    "ncm", "cest", "uf_origem", "uf_destino", "mva_original",
    "base_legal", "data_inicio_vigencia", "data_fim_vigencia",
)

#: Regimes em que a MVA é insumo do cálculo (TN não consome MVA).
_REGIMES_COM_MVA = ("ST", "ST_ENTRADA")


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


def _vigente_origem(linhas: _Vigencias | None, data: date, origem: str) -> bool:
    """Há MVA vigente na data para essa UF de origem?

    Casa a origem EXATA ou o curinga (`*`, a regra que vale para qualquer
    origem). Nota sem UF de emitente entra como curinga e só é coberta por uma
    regra geral — o par específico continua sendo lacuna, que é o correto:
    ninguém sabe de onde a mercadoria veio."""
    for inicio, fim, uf_origem in linhas or ():
        if inicio <= data and (fim is None or data <= fim) and (
            uf_origem in (origem, CURINGA_UF)
        ):
            return True
    return False


def _primeiro_do_mes(iso: str) -> str:
    """'2026-06-17' → '2026-06-01'. Só recorta a data que JÁ está nas notas —
    é sugestão de início de vigência para a planilha, não afirmação de norma."""
    return f"{iso[:7]}-01"


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
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        grupos = await self._agrupar_itens(empresa_id, uf, ano, mes)
        if not grupos:
            return {"resumo": {"grupos": 0, "valor_total": 0.0, "pct_valor_coberto": 100.0,
                               "por_status": {}}, "grupos": [], "total": 0,
                    "page": page, "page_size": page_size, "total_pages": 0}

        ufs = {g["uf"] for g in grupos}
        enq_map = await self._mapa_enquadramento(ufs)
        mva_map = await self._mapa_mva(ufs)
        aliq_map = await self._mapa_aliquota(ufs)

        for g in grupos:
            g["status"], g["regime"] = self._classificar(g, enq_map, mva_map, aliq_map)

        grupos.sort(key=lambda g: g["valor"], reverse=True)
        total = len(grupos)
        inicio = (page - 1) * page_size
        return {
            "resumo": self._resumo(grupos),
            "grupos": grupos[inicio:inicio + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": ceil(total / page_size),
        }

    # ── agregação da carteira ────────────────────────────────────────────────
    async def _agrupar_itens(
        self, empresa_id, uf, ano, mes, *, por_origem: bool = False
    ) -> list[dict]:
        """Itens importados agrupados por NCM×CEST×UF de destino — e também por
        UF de ORIGEM quando `por_origem` (a MVA depende do par, o enquadramento
        não). Uma única consulta serve os dois relatórios."""
        n, it = Nota, NotaItem
        chaves = [n.uf_dest, it.ncm, it.cest] + ([n.uf_emit] if por_origem else [])
        stmt = (
            select(
                n.uf_dest.label("uf"), it.ncm.label("ncm"), it.cest.label("cest"),
                (n.uf_emit if por_origem else null()).label("uf_origem"),
                func.count(it.id).label("itens"),
                func.count(func.distinct(it.nota_id)).label("notas"),
                func.coalesce(func.sum(it.valor_produto), 0).label("valor"),
                func.max(n.data_emissao).label("emissao_max"),
                func.min(n.data_emissao).label("emissao_min"),
                func.min(it.descricao).label("descricao"),
            )
            .join(n, it.nota_id == n.id)
            .where(
                n.fluxo.in_(("entrada", "saida")), n.status == "ativa",
                it.ncm.isnot(None), it.ncm != "",
                n.uf_dest.isnot(None), n.uf_dest != "",
            )
            .group_by(*chaves)
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
                "uf": (r["uf"] or "").upper(),
                "ncm": only_digits(r["ncm"]),
                "cest": only_digits(r["cest"] or ""),
                # Nota sem UF de emitente não permite escopar a origem: entra
                # como curinga (a regra que vale para qualquer origem).
                "uf_origem": (r["uf_origem"] or CURINGA_UF).upper(),
                "itens": int(r["itens"]),
                "notas": int(r["notas"]),
                "valor": float(r["valor"] or 0),
                "data_ref": _data_ref(r["emissao_max"]).isoformat(),
                "data_primeira": _data_ref(r["emissao_min"]).isoformat(),
                "descricao": (r["descricao"] or "")[:120],
            }
            for r in (await self.session.execute(stmt)).mappings().all()
        ]

    # ── lacunas da matriz de MVA (fila de carga, exportável) ─────────────────
    async def lacunas_mva(
        self,
        *,
        empresa_id: UUID | None = None,
        uf: str | None = None,
        ano: str | None = None,
        mes: str | None = None,
        incluir_sem_enquadramento: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """Pares NCM×CEST×(origem→destino) das notas importadas SEM MVA vigente.

        É o antídoto do cadastro item a item: em vez de descobrir a falta uma
        nota por vez, o escritório vê a lista inteira ordenada por dinheiro e
        baixa o CSV já no layout do importador (`lacunas_mva_csv`).

        `incluir_sem_enquadramento` traz também os pares que nem têm regime
        definido — eles PODEM ser ST, mas o sistema não sabe; por padrão ficam
        de fora da fila e só aparecem contados no resumo.
        """
        page = max(1, page)
        page_size = max(1, min(200, page_size))
        lacunas, resumo = await self._levantar_lacunas_mva(
            empresa_id, uf, ano, mes, incluir_sem_enquadramento
        )
        total = len(lacunas)
        inicio = (page - 1) * page_size
        return {
            "resumo": resumo,
            "lacunas": lacunas[inicio:inicio + page_size],
            "colunas_csv": list(COLUNAS_CSV_MVA),
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": ceil(total / page_size),
        }

    async def lacunas_mva_csv(
        self,
        *,
        empresa_id: UUID | None = None,
        uf: str | None = None,
        ano: str | None = None,
        mes: str | None = None,
        incluir_sem_enquadramento: bool = False,
    ) -> str:
        """A MESMA lista, no layout do "Importar planilha" da matriz de MVA.

        `mva_original` e `base_legal` saem VAZIOS de propósito: o valor é dado
        normativo e vem da fonte oficial (RICMS/portaria da UF) — o sistema
        aponta a lacuna, jamais preenche o número. `data_inicio_vigencia` vem
        pré-preenchida com o 1º dia do mês da nota mais antiga do grupo (é o
        início da competência auditada, ajustável antes de subir).
        """
        lacunas, _ = await self._levantar_lacunas_mva(
            empresa_id, uf, ano, mes, incluir_sem_enquadramento
        )
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";", lineterminator="\n")
        w.writerow(COLUNAS_CSV_MVA)
        for g in lacunas:
            w.writerow([
                g["ncm"], g["cest"], g["uf_origem"], g["uf_destino"],
                "",                                   # mva_original — só a fonte oficial preenche
                "",                                   # base_legal — norma que publicou a margem
                g["data_inicio_vigencia"], "",
            ])
        return buf.getvalue()

    async def _levantar_lacunas_mva(
        self, empresa_id, uf, ano, mes, incluir_sem_enquadramento: bool
    ) -> tuple[list[dict], dict]:
        grupos = await self._agrupar_itens(empresa_id, uf, ano, mes, por_origem=True)
        resumo: dict = {
            "lacunas": 0, "itens": 0, "valor": 0.0, "valor_avaliado": 0.0,
            "pct_valor_sem_mva": 0.0, "por_uf": {},
            "sem_enquadramento": {"grupos": 0, "valor": 0.0},
            "cobertos": {"grupos": 0, "valor": 0.0},
        }
        if not grupos:
            return [], resumo

        ufs = {g["uf"] for g in grupos}
        enq_map = await self._mapa_enquadramento(ufs)
        mva_map = await self._mapa_mva(ufs)

        lacunas: list[dict] = []
        avaliado = 0.0
        for g in grupos:
            data = date.fromisoformat(g["data_ref"])
            candidatos = _candidatos_ncm(g["ncm"])

            regime = None
            for c in candidatos:
                achou, payload = _vigente(enq_map.get((g["uf"], c, g["cest"])), data)
                if achou:
                    regime = payload
                    break

            if regime is None:
                resumo["sem_enquadramento"]["grupos"] += 1
                resumo["sem_enquadramento"]["valor"] += g["valor"]
                if not incluir_sem_enquadramento:
                    continue
            elif regime not in _REGIMES_COM_MVA:
                continue                              # TN não consome MVA

            avaliado += g["valor"]
            if any(
                _vigente_origem(mva_map.get((g["uf"], c, g["cest"])), data, g["uf_origem"])
                for c in candidatos
            ):
                resumo["cobertos"]["grupos"] += 1
                resumo["cobertos"]["valor"] += g["valor"]
                continue

            lacunas.append({
                "ncm": g["ncm"],
                "cest": g["cest"],
                "uf_origem": g["uf_origem"],
                "uf_destino": g["uf"],
                "regime": regime,
                "motivo": "SEM_MVA" if regime else "SEM_ENQUADRAMENTO",
                "itens": g["itens"],
                "notas": g["notas"],
                "valor": g["valor"],
                "descricao": g["descricao"],
                "data_ref": g["data_ref"],
                "data_inicio_vigencia": _primeiro_do_mes(g["data_primeira"]),
            })

        # Fila de trabalho: primeiro o que mais pesa em dinheiro, depois em itens.
        lacunas.sort(key=lambda g: (g["valor"], g["itens"]), reverse=True)
        for g in lacunas:
            porta = resumo["por_uf"].setdefault(
                g["uf_destino"], {"lacunas": 0, "itens": 0, "valor": 0.0}
            )
            porta["lacunas"] += 1
            porta["itens"] += g["itens"]
            porta["valor"] += g["valor"]
        resumo["lacunas"] = len(lacunas)
        resumo["itens"] = sum(g["itens"] for g in lacunas)
        resumo["valor"] = sum(g["valor"] for g in lacunas)
        resumo["valor_avaliado"] = avaliado
        resumo["pct_valor_sem_mva"] = (
            round(resumo["valor"] / avaliado * 100, 1) if avaliado else 0.0
        )
        return lacunas, resumo

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
        """(UF destino, NCM, CEST) → vigências, com a UF de ORIGEM no payload —
        o mesmo mapa serve a cobertura (que ignora a origem) e às lacunas
        (que exigem origem exata ou curinga)."""
        rows = (await self.session.execute(
            select(MatrizMva).where(MatrizMva.uf_destino.in_(ufs))
        )).scalars()
        mapa: dict[tuple[str, str, str], _Vigencias] = {}
        for r in rows:
            mapa.setdefault((r.uf_destino, r.ncm, r.cest), []).append(
                (r.data_inicio_vigencia, r.data_fim_vigencia, r.uf_origem)
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
