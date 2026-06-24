"""Agregação e rateio do frete dos CT-e vinculados (prova do ADR-0001).

O frete vem em um ou mais CT-e separados (cardinalidade N:N). Agrega-se o
vTPrest de todos os CT-e que compõem frete e rateia-se proporcionalmente ao
vProd de cada item, com compensação de centavos no item de maior valor
(evita dízima e fecha o somatório — Seção 3 do CALC_ICMS_Proprio).
"""
from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from app.modules.fiscal.domain.st.money import ZERO, centavos

# tpCTe que SOMA como frete: 0=normal, 1=complementar (e ausente). 2=anulação e
# 3=substituto não entram (anulam/substituem — tratados à parte no futuro).
_TP_CTE_SOMA = {None, "", "0", "1"}


def agregar_frete(vinculos: Iterable) -> Decimal:
    """Soma o vTPrest dos CT-e vinculados que compõem frete (normal/complementar)."""
    total = ZERO
    for v in vinculos:
        if (v.tp_cte or "") in _TP_CTE_SOMA:
            total += v.vtprest or ZERO
    return centavos(total)


def ratear_frete(itens: list, frete_total: Decimal) -> dict[int, Decimal]:
    """Rateia `frete_total` proporcional ao vProd. Retorna {numero_item: frete}.

    A diferença de centavos do arredondamento vai no item de MAIOR vProd, para
    o somatório dos rateios bater exatamente com o frete agregado.
    """
    frete_total = centavos(frete_total)
    rateio: dict[int, Decimal] = {it.numero_item: ZERO for it in itens}
    if frete_total <= ZERO or not itens:
        return rateio

    soma_vprod = sum((it.valor_produto or ZERO) for it in itens)
    if soma_vprod <= ZERO:
        return rateio

    acumulado = ZERO
    for it in itens:
        fracao = centavos(frete_total * (it.valor_produto or ZERO) / soma_vprod)
        rateio[it.numero_item] = fracao
        acumulado += fracao

    sobra = frete_total - acumulado          # ± uns centavos
    if sobra != ZERO:
        maior = max(itens, key=lambda it: it.valor_produto or ZERO)
        rateio[maior.numero_item] += sobra
    return rateio
