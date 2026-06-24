"""Vigência temporal (valid-time) das matrizes fiscais — ADR-0002.

A lei muda: o motor precisa da regra vigente na DATA DE EMISSÃO da nota, não da
regra "atual". Toda matriz herda este mixin e filtra a busca por `filtrar_vigencia`.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, or_
from sqlalchemy.orm import Mapped, mapped_column


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
