"""Estratégias de composição da base do ST (por modBCST) e de dedução do ICMS
próprio (por CRT). Mantém o engine livre de cadeias de if/elif por código.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .enums import ModBcSt
from .errors import ErroST
from .model import ItemFiscal, Operacao
from .money import ZERO, aplicar_percentual, fator_percentual, fator_reducao


# --------------------------------------------------------------------------- #
# Base de cálculo do ST — Factory por modBCST
# --------------------------------------------------------------------------- #
def _montante_custo(item: ItemFiscal) -> Decimal:
    """vProd + frete + seguro + outras − desconto + IPI (Seção 4.1).

    Para ST o IPI entra sempre (a ST presume a venda final), diferente da base
    do ICMS próprio, onde a inclusão depende da destinação.
    """
    return (
        item.v_prod + item.v_frete + item.v_seg + item.v_outro - item.v_desc + item.v_ipi
    )


class BaseStrategy(Protocol):
    espera_mva: bool
    def base_integral(self, item: ItemFiscal, mva_aplicada: Decimal) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class BaseMva:
    """modBCST=4: custo × (1 + MVA/100)."""

    espera_mva: bool = True

    def base_integral(self, item: ItemFiscal, mva_aplicada: Decimal) -> Decimal:
        return _montante_custo(item) * fator_percentual(mva_aplicada)


@dataclass(frozen=True, slots=True)
class BaseValorOperacao:
    """modBCST=6: base = valor da operação, sem MVA (NT 2020.005)."""

    espera_mva: bool = False

    def base_integral(self, item: ItemFiscal, mva_aplicada: Decimal) -> Decimal:
        return _montante_custo(item)


def base_strategy_for(mod_bc_st: int | None) -> BaseStrategy | None:
    """Factory. Retorna None para modalidades fora do núcleo v1 (pauta/PMC)."""
    if mod_bc_st == ModBcSt.MVA:
        return BaseMva()
    if mod_bc_st == ModBcSt.VALOR_OPERACAO:
        return BaseValorOperacao()
    return None


def aplicar_reducao_base(base_integral: Decimal, p_red_bc_st: Decimal) -> Decimal:
    """Método A (redução estende-se à base do ST). Método B fica para o v2."""
    if p_red_bc_st and p_red_bc_st > ZERO:
        return base_integral * fator_reducao(p_red_bc_st)
    return base_integral


# --------------------------------------------------------------------------- #
# Dedução do ICMS próprio — Strategy por CRT / CST
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ResultadoDeducao:
    valor: Decimal
    tipo: str                  # real | teorica | zero | contaminada
    erro: ErroST | None = None


def _base_proprio(item: ItemFiscal) -> Decimal:
    """Base da operação própria/dedução teórica: subtotal comercial, sem IPI."""
    return item.v_prod + item.v_frete + item.v_seg + item.v_outro - item.v_desc


def calcular_deducao(
    item: ItemFiscal, operacao: Operacao, alq_operacao: Decimal
) -> ResultadoDeducao:
    """Dedução do imposto próprio (Seção 6 do CALC_ICMS_ST).

    - CST 30: própria isenta → dedução zero (legítima).
    - Simples (CRT 1/4): dedução TEÓRICA = base × alíquota da operação.
    - Normal (CRT 2/3): deduz o vICMS REAL do XML; mas se CST 10/70 vier com
      vICMS/vBC zerados (erro do emissor), não deduz o zero — recalcula o
      próprio esperado e marca ERRO_107 (trava de causa-raiz da Seção 6.1).
    """
    if item.cst == "30":
        return ResultadoDeducao(ZERO, "zero")

    if operacao.crt.is_simples:
        teorica = aplicar_percentual(_base_proprio(item), alq_operacao)
        return ResultadoDeducao(teorica, "teorica")

    # Regime normal — trava do próprio zerado por erro de emissão.
    if item.cst in ("10", "70") and (item.v_icms == ZERO or item.v_bc == ZERO):
        base = _base_proprio(item) * fator_reducao(item.p_red_bc) if item.cst == "70" \
            else _base_proprio(item)
        proprio_esperado = aplicar_percentual(base, alq_operacao)
        return ResultadoDeducao(proprio_esperado, "contaminada", ErroST.ICMS_PROPRIO_ZERADO_COM_ST)

    return ResultadoDeducao(item.v_icms, "real")
