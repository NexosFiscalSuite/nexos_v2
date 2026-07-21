"""Loaders assíncronos das matrizes (padrão "carrega-então-calcula", ADR/Fase 1).

A camada async vai ao banco UMA vez por matriz (sem N+1), filtra pela vigência
(ADR-0002) e hidrata repositórios SÍNCRONOS que implementam os ports do motor.
O domínio (`StAuditEngine`) permanece puro, síncrono e cego ao banco.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.domain.st.enums import Regime
from app.modules.fiscal.domain.st.model import ItemFiscal, Operacao
from app.modules.fiscal.domain.st.ports import AliquotaUf, MvaInfo
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)
from app.modules.fiscal.infrastructure.vigencia import filtrar_vigencia
from app.shared.domain.value_objects import only_digits


def _candidatos_ncm(ncm: str) -> list[str]:
    """NCM do mais específico ao mais geral (8→6→4), sem duplicar."""
    n = only_digits(ncm)
    vistos: list[str] = []
    for c in (n, n[:6], n[:4]):
        if c and c not in vistos:
            vistos.append(c)
    return vistos


# --------------------------------------------------------------------------- #
# Repositórios SÍNCRONOS hidratados (implementam os Protocols do domínio)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class _MvaSnapshot:
    dados: dict[tuple[str, str, str], tuple[Decimal, int]]   # (ncm, cest, uf) -> (MVA, id)

    def buscar(self, ncm: str, cest: str, uf_dest: str, data: date) -> MvaInfo | None:
        cest_l, uf = only_digits(cest), uf_dest.upper()
        for c in _candidatos_ncm(ncm):
            par = self.dados.get((c, cest_l, uf))
            if par is not None:
                mva, linha_id = par
                return MvaInfo(mva_original=mva, ncm_casado=c, matriz_id=linha_id)
        if not cest_l:
            # XML sem a tag CEST (típico de emitente que nem tratou o item como
            # ST): casa pelo NCM. MVA única no NCM → usa; MVAs distintas por
            # CEST → ambíguo, fail-closed (None trava com o erro de MVA).
            for c in _candidatos_ncm(ncm):
                pares = [v for (n, _ce, u), v in self.dados.items() if n == c and u == uf]
                if pares:
                    mvas = {p[0] for p in pares}
                    if len(mvas) == 1:
                        mva, linha_id = pares[0]
                        return MvaInfo(mva_original=mva, ncm_casado=c, matriz_id=linha_id)
                    return None
        return None


@dataclass(frozen=True, slots=True)
class _EnquadramentoSnapshot:
    dados: dict[tuple[str, str, str], Regime]    # (ncm, cest, uf) -> regime

    def regime(self, ncm: str, cest: str, uf_orig: str, uf_dest: str, data: date) -> Regime:
        cest_l, uf = only_digits(cest), uf_dest.upper()
        for c in _candidatos_ncm(ncm):
            reg = self.dados.get((c, cest_l, uf))
            if reg is not None:
                return reg
        if not cest_l:
            # XML sem CEST: o cadastro NCM×CEST ainda vale — casa pelo NCM.
            # Regime único entre os CEST do NCM → esse regime; conflito → abre o
            # portão (ST) e a checagem de MVA a jusante decide com transparência.
            for c in _candidatos_ncm(ncm):
                regimes = {r for (n, _ce, u), r in self.dados.items() if n == c and u == uf}
                if regimes:
                    return regimes.pop() if len(regimes) == 1 else Regime.ST
        return Regime.TN   # não enquadrado = tributação normal

    def explicar_tn(self, ncm: str, cest: str, uf_dest: str) -> str | None:
        """Por que o item caiu em TN? None = TN explícito por cadastro (legítimo,
        fora do motor por decisão). String = falta/conflito de cadastro — vira
        NAO_AUDITAVEL acionável (com código de erro, reprocessável)."""
        cest_l, uf = only_digits(cest), uf_dest.upper()
        candidatos = _candidatos_ncm(ncm)
        for c in candidatos:
            if (c, cest_l, uf) in self.dados:
                return None
        cests_ncm = sorted({ce for (n, ce, u) in self.dados if u == uf and n in candidatos})
        if not cests_ncm:
            alvo = f"NCM {only_digits(ncm) or '—'}" + (f" · CEST {cest_l}" if cest_l else "")
            return (f"{alvo} sem enquadramento cadastrado para {uf} — cadastre ST ou TN "
                    "nas Matrizes Fiscais (Enquadramento) para o motor auditar.")
        if cest_l:
            return (f"CEST {cest_l} do XML não casa com o cadastro do NCM em {uf} "
                    f"(CEST cadastrado: {', '.join(cests_ncm)}) — confira o item ou "
                    "complete o cadastro para auditar.")
        return None   # sem CEST no XML e NCM cadastrado: o fallback já respondeu


@dataclass(frozen=True, slots=True)
class _FcpSnapshot:
    dados: dict[tuple[str, str], Decimal]        # (uf, ncm|'GERAL') -> FCP-ST

    def aliquota_st(self, ncm: str, uf_dest: str, data: date) -> Decimal:
        uf, n = uf_dest.upper(), only_digits(ncm)
        for chave in (n, n[:4], "GERAL"):
            aliq = self.dados.get((uf, chave))
            if aliq is not None:
                return aliq
        return Decimal("0")


@dataclass(frozen=True, slots=True)
class _ProtocoloSnapshot:
    pares: frozenset[tuple[str, str]]            # (uf_orig, uf_dest) com acordo vigente
    fonte: ClassVar[str] = "matriz"              # resposta consultada (vai à memória)

    def tem_protocolo(self, uf_orig: str, uf_dest: str, data: date) -> bool:
        return (uf_orig.upper(), uf_dest.upper()) in self.pares


@dataclass(frozen=True, slots=True)
class _AliquotaSnapshot:
    dados: dict[str, AliquotaUf]                 # UF -> alíquota vigente na data

    def buscar(self, uf_dest: str, data: date) -> AliquotaUf | None:
        return self.dados.get(uf_dest.upper())


@dataclass(frozen=True, slots=True)
class MatrizesHidratadas:
    """O que o orquestrador injeta no StAuditEngine."""

    mva: _MvaSnapshot
    enquadramento: _EnquadramentoSnapshot
    fcp: _FcpSnapshot
    protocolo: _ProtocoloSnapshot
    aliquota: _AliquotaSnapshot


# --------------------------------------------------------------------------- #
# Loader async
# --------------------------------------------------------------------------- #
class MatrizesLoader:
    """Carrega em lote as matrizes vigentes para os itens de uma nota."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def hidratar(self, itens: list[ItemFiscal], operacao: Operacao) -> MatrizesHidratadas:
        uf, data = operacao.uf_dest.upper(), operacao.data
        ncms: set[str] = set()
        cests: set[str] = set()
        for it in itens:
            ncms.update(_candidatos_ncm(it.ncm))
            cests.add(only_digits(it.cest))

        return MatrizesHidratadas(
            mva=await self._mva(uf, ncms, cests, data),
            enquadramento=await self._enquadramento(uf, ncms, cests, data),
            fcp=await self._fcp(uf, ncms, data),
            protocolo=await self._protocolo(operacao.uf_emit.upper(), uf, data),
            aliquota=await self._aliquota(uf, data),
        )

    async def _mva(self, uf, ncms, cests, data) -> _MvaSnapshot:
        # Sem filtro por CEST: o XML pode vir sem a tag (o snapshot resolve o
        # fallback por NCM) — poucas linhas por NCM, custo irrelevante.
        stmt = filtrar_vigencia(
            select(MatrizMva).where(
                MatrizMva.uf_destino == uf,
                MatrizMva.ncm.in_(ncms),
            ),
            MatrizMva,
            data,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return _MvaSnapshot(
            {(r.ncm, r.cest, r.uf_destino): (r.mva_original, r.id) for r in rows}
        )

    async def _enquadramento(self, uf, ncms, cests, data) -> _EnquadramentoSnapshot:
        # Sem filtro por CEST (mesma razão do _mva): o cadastro NCM×CEST precisa
        # ser visível mesmo quando a nota veio sem a tag CEST.
        stmt = filtrar_vigencia(
            select(MatrizEnquadramentoSt).where(
                MatrizEnquadramentoSt.uf_destino == uf,
                MatrizEnquadramentoSt.ncm.in_(ncms),
            ),
            MatrizEnquadramentoSt,
            data,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return _EnquadramentoSnapshot(
            {(r.ncm, r.cest, r.uf_destino): Regime(r.regime) for r in rows}
        )

    async def _fcp(self, uf, ncms, data) -> _FcpSnapshot:
        stmt = filtrar_vigencia(
            select(MatrizFcp).where(
                MatrizFcp.uf_destino == uf,
                MatrizFcp.ncm.in_(set(ncms) | {"GERAL"}),
            ),
            MatrizFcp,
            data,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return _FcpSnapshot({(r.uf_destino, r.ncm): r.aliq_fcp_st for r in rows})

    async def _protocolo(self, uf_orig: str, uf_dest: str, data) -> _ProtocoloSnapshot:
        # Operação interna (mesma UF) não tem protocolo a checar — evita ida ao banco.
        if uf_orig == uf_dest:
            return _ProtocoloSnapshot(frozenset())
        stmt = filtrar_vigencia(
            select(MatrizProtocoloSt).where(
                MatrizProtocoloSt.uf_origem == uf_orig,
                MatrizProtocoloSt.uf_destino == uf_dest,
            ),
            MatrizProtocoloSt,
            data,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return _ProtocoloSnapshot(frozenset((r.uf_origem, r.uf_destino) for r in rows))

    async def _aliquota(self, uf: str, data) -> _AliquotaSnapshot:
        stmt = (
            filtrar_vigencia(
                select(MatrizAliquota).where(MatrizAliquota.uf_destino == uf),
                MatrizAliquota,
                data,
            )
            # Desempate (ADR-0002): se houver sobreposição indevida, vence a
            # vigência mais recente — a validação de carga é quem impede o caso.
            .order_by(MatrizAliquota.data_inicio_vigencia.desc())
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            return _AliquotaSnapshot({})
        return _AliquotaSnapshot({row.uf_destino: AliquotaUf(
            modal=row.aliq_modal, fcp_integrado=row.aliq_fcp_integrado, matriz_id=row.id,
        )})
