"""Ports (interfaces) para os dados que vivem no banco com vigência temporal.

O domínio define O QUE precisa; a infraestrutura (Postgres, seed em memória)
decide COMO entrega. Isto mantém o motor puro e testável — inversão de
dependência da Clean Architecture.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from .enums import Regime


@dataclass(frozen=True, slots=True)
class MvaInfo:
    mva_original: Decimal
    ncm_casado: str          # qual nível do NCM bateu (diagnóstico do fallback)


class MvaRepository(Protocol):
    """MATRIZ_MVA_Por_Segmento — chave NCM+CEST+UF, com fallback 8→6→4 dígitos."""

    def buscar(self, ncm: str, cest: str, uf_dest: str, data: date) -> MvaInfo | None: ...


class EnquadramentoRepository(Protocol):
    """MATRIZ_NCM_Enquadramento_ST — portão ST / TN / ST_ENTRADA / DIFAL."""

    def regime(
        self, ncm: str, cest: str, uf_orig: str, uf_dest: str, data: date
    ) -> Regime: ...


class FcpRepository(Protocol):
    """MATRIZ_FCP_Por_UF — alíquota de FCP-ST por UF+NCM+vigência (fallback 8→4→GERAL).

    Retorna a alíquota (0 se o NCM não está sujeito ao fundo na UF de destino).
    """

    def aliquota_st(self, ncm: str, uf_dest: str, data: date) -> Decimal: ...
