"""Enumerações do domínio fiscal de ST (sem dependências externas)."""
from __future__ import annotations

from enum import Enum


class Crt(int, Enum):
    """Código de Regime Tributário do emitente (tag <CRT>)."""

    SIMPLES = 1            # Simples Nacional
    SIMPLES_EXCESSO = 2    # Simples — excesso de sublimite (apura ICMS como normal)
    NORMAL = 3             # Regime Normal
    MEI = 4                # Simples Nacional — MEI (NT 2023.001)

    @property
    def is_simples(self) -> bool:
        """CRT 1 e 4 são optantes do Simples para fins de MVA/dedução.

        CRT 2 (excesso de sublimite) recolhe ICMS FORA do Simples → tratado
        como normal: ajusta MVA e deduz ICMS real. Inverter isso geraria
        retenção a menor (CRT 2) ou retenção indevida sobre MEI (CRT 4).
        """
        return self in (Crt.SIMPLES, Crt.MEI)


class Regime(str, Enum):
    """Regime de tributação do item, decidido pelo enquadramento (a montante)."""

    ST = "ST"                  # Substituição tributária — este motor audita
    TN = "TN"                  # Tributação normal — fora do escopo do motor de ST
    ST_ENTRADA = "ST_ENTRADA"  # Antecipação na entrada (v2)
    DIFAL = "DIFAL"            # Diferencial de alíquota (outro motor)


class ModBcSt(int, Enum):
    """Modalidade de determinação da BC do ICMS ST (tag <modBCST>)."""

    PRECO_TABELADO = 0
    LISTA_NEGATIVA = 1
    LISTA_POSITIVA = 2
    LISTA_NEUTRA = 3
    MVA = 4               # Margem de Valor Agregado (núcleo v1)
    PAUTA = 5
    VALOR_OPERACAO = 6    # NT 2020.005 — base = valor da operação, sem MVA (v1)


class MetodoReducao(str, Enum):
    """Como a redução de base interage com a ST (parametrizado por UF destino)."""

    # A: redução estende-se integralmente à base do ST (vBCST × (1 − pRedBCST)).
    CADEIA = "A"
    # B: MVA sobre valor cheio; redução só no débito final (carga meta).
    CARGA_META = "B"
