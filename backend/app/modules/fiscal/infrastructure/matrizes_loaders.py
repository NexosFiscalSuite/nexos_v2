"""Loaders assíncronos das matrizes (padrão "carrega-então-calcula", ADR/Fase 1).

A camada async vai ao banco UMA vez por matriz (sem N+1), filtra pela vigência
(ADR-0002) e hidrata repositórios SÍNCRONOS que implementam os ports do motor.
O domínio (`StAuditEngine`) permanece puro, síncrono e cego ao banco.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.domain.st.enums import Regime
from app.modules.fiscal.domain.st.model import ItemFiscal, Operacao
from app.modules.fiscal.domain.st.ports import MvaInfo
from app.modules.fiscal.infrastructure.matrizes_models import (
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
    dados: dict[tuple[str, str, str], Decimal]   # (ncm, cest, uf) -> MVA

    def buscar(self, ncm: str, cest: str, uf_dest: str, data: date) -> MvaInfo | None:
        cest_l, uf = only_digits(cest), uf_dest.upper()
        for c in _candidatos_ncm(ncm):
            mva = self.dados.get((c, cest_l, uf))
            if mva is not None:
                return MvaInfo(mva_original=mva, ncm_casado=c)
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
        return Regime.TN   # não enquadrado = tributação normal


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

    def tem_protocolo(self, uf_orig: str, uf_dest: str, data: date) -> bool:
        return (uf_orig.upper(), uf_dest.upper()) in self.pares


@dataclass(frozen=True, slots=True)
class MatrizesHidratadas:
    """O que o orquestrador injeta no StAuditEngine."""

    mva: _MvaSnapshot
    enquadramento: _EnquadramentoSnapshot
    fcp: _FcpSnapshot
    protocolo: _ProtocoloSnapshot


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
        )

    async def _mva(self, uf, ncms, cests, data) -> _MvaSnapshot:
        stmt = filtrar_vigencia(
            select(MatrizMva).where(
                MatrizMva.uf_destino == uf,
                MatrizMva.ncm.in_(ncms),
                MatrizMva.cest.in_(cests),
            ),
            MatrizMva,
            data,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return _MvaSnapshot({(r.ncm, r.cest, r.uf_destino): r.mva_original for r in rows})

    async def _enquadramento(self, uf, ncms, cests, data) -> _EnquadramentoSnapshot:
        stmt = filtrar_vigencia(
            select(MatrizEnquadramentoSt).where(
                MatrizEnquadramentoSt.uf_destino == uf,
                MatrizEnquadramentoSt.ncm.in_(ncms),
                MatrizEnquadramentoSt.cest.in_(cests),
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
