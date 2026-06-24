"""Cálculo da MVA aplicável: Original vs. Ajustada (Seção 3 do CALC_ICMS_ST).

O erro mais comum de mercado é ajustar a MVA quando o ajuste é proibido. Aqui
as 4 travas de exclusão são guard clauses de early-return — se qualquer uma
dispara, vale a MVA Original; só no fim, sobrando todas, calcula-se o ajuste.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .enums import Crt
from .money import D, fator_percentual, fator_reducao


@dataclass(frozen=True, slots=True)
class ResultadoMva:
    mva_aplicada: Decimal
    ajustada: bool
    motivo_nao_ajuste: str | None


def calcular_mva(
    *,
    mva_original: Decimal,
    alq_inter: Decimal,
    alq_intra: Decimal,
    crt: Crt,
    interestadual: bool,
) -> ResultadoMva:
    """Decide e calcula a MVA. `alq_intra` deve ser a CARGA EFETIVA (R-07)."""
    mva_original = D(mva_original)

    # Trava 1 — emitente do Simples (CRT 1/4) não ajusta (Conv. 142/2018).
    if crt.is_simples:
        return ResultadoMva(mva_original, False, "emitente Simples Nacional (CRT 1/4)")

    # Trava 4 — operação interna: ajuste é conceitualmente impossível.
    if not interestadual:
        return ResultadoMva(mva_original, False, "operação interna (UF emit == UF dest)")

    # Trava 2 — Alq_Inter >= Alq_Intra: ajuste seria nulo/negativo.
    if D(alq_inter) >= D(alq_intra):
        return ResultadoMva(mva_original, False, "alíquota interestadual >= interna")

    # (Trava 3 — informática/automação com incentivo — depende de tabela de
    #  exceções por NCM; entra junto da matriz no v2.)

    # Fórmula geral do ajuste.
    mva_ajustada = (
        fator_percentual(mva_original) * (fator_reducao(alq_inter) / fator_reducao(alq_intra))
        - Decimal("1")
    ) * Decimal("100")
    return ResultadoMva(mva_ajustada, True, None)
