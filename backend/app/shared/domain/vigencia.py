"""Regra pura de sobreposição de vigência (valid-time) — ADR-0002.

Compartilhada entre a validação SQL das matrizes (fiscal) e o import em lote
genérico (bulk_csv): uma única definição de "períodos conflitam".
"""
from __future__ import annotations

from datetime import date


def intervalos_conflitam(
    a_inicio: date, a_fim: date | None, b_inicio: date, b_fim: date | None
) -> bool:
    """Dois períodos de vigência se sobrepõem? (fim None = aberto, sem término.)"""
    return a_inicio <= (b_fim or date.max) and b_inicio <= (a_fim or date.max)
