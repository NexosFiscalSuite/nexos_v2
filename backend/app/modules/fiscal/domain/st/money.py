"""Aritmética monetária e de percentuais em Decimal.

Dinheiro e alíquotas NUNCA usam float: erro de ponto flutuante em base de
cálculo fiscal vira divergência de centavos que mascara (ou inventa) erro de
imposto. Tudo entra e circula como Decimal; o arredondamento para centavos só
acontece na fronteira de comparação/saída, com ROUND_HALF_UP (regra SEFAZ).
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

ZERO = Decimal("0")
CEM = Decimal("100")
CENTAVO = Decimal("0.01")


def D(valor: object) -> Decimal:
    """Coage qualquer entrada (str, int, float, None) para Decimal seguro.

    float é convertido via str para não arrastar o ruído binário (Decimal(0.1)
    != Decimal('0.1')). Entrada inválida/vazia vira ZERO — o motor é tolerante
    a XML sujo por princípio.
    """
    if isinstance(valor, Decimal):
        return valor
    if valor is None or valor == "":
        return ZERO
    try:
        return Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return ZERO


def centavos(valor: Decimal) -> Decimal:
    """Arredonda para 2 casas (ROUND_HALF_UP). Use só na saída/comparação."""
    return D(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def aplicar_percentual(base: Decimal, percentual: Decimal) -> Decimal:
    """base × (percentual/100). `percentual` é o número cheio (40 == 40%)."""
    return D(base) * D(percentual) / CEM


def fator_percentual(percentual: Decimal) -> Decimal:
    """(1 + percentual/100) — fator de acréscimo (ex.: MVA sobre o custo)."""
    return Decimal("1") + D(percentual) / CEM


def fator_reducao(percentual: Decimal) -> Decimal:
    """(1 − percentual/100) — fator de redução de base."""
    return Decimal("1") - D(percentual) / CEM
