"""Vigência temporal (valid-time) das matrizes fiscais — ADR-0002.

A lei muda: o motor precisa da regra vigente na DATA DE EMISSÃO da nota, não da
regra "atual". Toda matriz herda este mixin e filtra a busca por `filtrar_vigencia`.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.domain.vigencia import intervalos_conflitam

__all__ = [
    "VigenciaTemporal",
    "filtrar_vigencia",
    "intervalos_conflitam",
    "sobreposicao_existente",
]


class VigenciaTemporal:
    """Colunas de vigência: início obrigatório, fim NULL = vigente em aberto."""

    data_inicio_vigencia: Mapped[date] = mapped_column(Date, nullable=False)
    data_fim_vigencia: Mapped[date | None] = mapped_column(Date, nullable=True)


def filtrar_vigencia(stmt, modelo, data_op: date):
    """Aplica o filtro de vigência a um SELECT: linha válida em `data_op`.

    Implementação única da regra (DRY) — toda busca de matriz passa por aqui.
    """
    return stmt.where(
        modelo.data_inicio_vigencia <= data_op,
        or_(modelo.data_fim_vigencia.is_(None), modelo.data_fim_vigencia >= data_op),
    )


async def sobreposicao_existente(
    session: AsyncSession, modelo, dados: dict, excluir_id: int | None = None
):
    """Linha da matriz que conflita com a vigência de `dados`, ou None.

    Duas linhas vigentes para a mesma chave na mesma data é erro de carga
    (ADR-0002, regra 4): mudança de taxa = encerrar a antiga e INSERIR a nova.
    A chave de identidade vem de `modelo.CHAVE_VIGENCIA`.
    """
    stmt = select(modelo).where(
        *[getattr(modelo, campo) == dados[campo] for campo in modelo.CHAVE_VIGENCIA],
        modelo.data_inicio_vigencia <= (dados.get("data_fim_vigencia") or date.max),
        or_(
            modelo.data_fim_vigencia.is_(None),
            modelo.data_fim_vigencia >= dados["data_inicio_vigencia"],
        ),
    )
    if excluir_id is not None:
        stmt = stmt.where(modelo.id != excluir_id)
    return (await session.execute(stmt.limit(1))).scalars().first()
